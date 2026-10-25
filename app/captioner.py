import io
import os
import threading
import time
import zipfile
from dataclasses import dataclass

import torch
from PIL import Image, UnidentifiedImageError

import metrics as m

MODEL_NAME = os.environ.get("CAPTION_MODEL", "Salesforce/blip-image-captioning-base")
MAX_SIDE = 1024
MAX_ZIP_IMAGES = 200
MAX_ZIP_UNCOMPRESSED = 500 * 1024**2
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff")

Image.MAX_IMAGE_PIXELS = 100_000_000


@dataclass
class Client:
    ip: str = "unknown"
    session_id: str = "unknown"
    browser: str = "unknown"


class Captioner:
    def __init__(self, model_name=MODEL_NAME):
        from transformers import BlipForConditionalGeneration, BlipProcessor

        m.app_state.state("loading_model")
        start = time.time()
        torch.set_grad_enabled(False)
        self.processor = BlipProcessor.from_pretrained(model_name)
        self.model = BlipForConditionalGeneration.from_pretrained(model_name).eval()
        m.model_load_seconds.set(time.time() - start)
        m.model_parameters_bytes.set(sum(p.numel() * p.element_size() for p in self.model.parameters()))
        m.model_loaded.set(1)
        m.app_state.state("idle")

    def caption_bytes(self, data, mode, client):
        m.image_size_bytes.labels(mode=mode).observe(len(data))

        with m.preprocess_latency.labels(mode=mode).time():
            img = Image.open(io.BytesIO(data))
            img.load()
            m.image_megapixels.labels(mode=mode).observe(img.width * img.height / 1e6)
            img = img.convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            inputs = self.processor(images=img, return_tensors="pt")

        t0 = time.time()
        out = self.model.generate(**inputs, max_new_tokens=30)
        infer_s = time.time() - t0
        caption = self.processor.decode(out[0], skip_special_tokens=True).strip()

        n_words = len(caption.split())
        m.inference_latency.labels(mode=mode).observe(infer_s)
        m.last_inference_seconds.labels(mode=mode, client_ip=client.ip).set(infer_s)
        m.caption_length_words.labels(mode=mode).observe(n_words)
        m.words_generated.labels(mode=mode).inc(n_words)
        m.images_processed.labels(mode=mode, client_ip=client.ip, session_id=client.session_id, browser=client.browser).inc()
        return {"caption": caption, "inference_s": round(infer_s, 3), "width": img.width, "height": img.height}

    def caption_single(self, data, client):
        mode = "single"
        m.bytes_received.labels(mode=mode, client_ip=client.ip).inc(len(data))
        m.input_bytes.labels(mode=mode).observe(len(data))
        m.app_state.state("processing_single")
        try:
            with m.active_requests.labels(mode=mode).track_inprogress(), m.request_duration.labels(mode=mode).time():
                result = self.caption_bytes(data, mode, client)
            m.requests_total.labels(mode=mode, status="success", client_ip=client.ip, session_id=client.session_id).inc()
            return result
        except Exception as e:
            m.errors_total.labels(mode=mode, error_type=type(e).__name__).inc()
            m.requests_total.labels(mode=mode, status="error", client_ip=client.ip, session_id=client.session_id).inc()
            raise
        finally:
            m.app_state.state("idle")

    def caption_zip(self, data, client):
        # yields (index, total, filename, result) for every image, bad files are skipped
        mode = "bulk"
        m.bytes_received.labels(mode=mode, client_ip=client.ip).inc(len(data))
        m.input_bytes.labels(mode=mode).observe(len(data))
        m.zip_uploads.labels(client_ip=client.ip, session_id=client.session_id).inc()
        m.app_state.state("processing_bulk")
        queue = m.bulk_queue_remaining.labels(session_id=client.session_id)
        status = "success"
        start = time.time()
        m.active_requests.labels(mode=mode).inc()
        try:
            try:
                zf = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                m.errors_total.labels(mode=mode, error_type="BadZipFile").inc()
                status = "error"
                raise

            members = []
            total_size = 0
            for info in zf.infolist():
                name = info.filename
                base = os.path.basename(name)
                if info.is_dir():
                    continue
                if name.startswith("__MACOSX/") or base.startswith("."):
                    m.images_skipped.labels(reason="hidden_file").inc()
                    continue
                if not base.lower().endswith(IMAGE_EXT):
                    m.images_skipped.labels(reason="not_an_image").inc()
                    continue
                if len(members) >= MAX_ZIP_IMAGES:
                    m.images_skipped.labels(reason="over_limit").inc()
                    continue
                total_size += info.file_size
                if total_size > MAX_ZIP_UNCOMPRESSED:
                    m.images_skipped.labels(reason="zip_too_large").inc()
                    continue
                members.append(info)

            total = len(members)
            m.bulk_batch_size.observe(total)
            m.bulk_job_images.observe(total)
            queue.set(total)

            n_ok = 0
            for i, info in enumerate(members, start=1):
                try:
                    result = self.caption_bytes(zf.read(info), mode, client)
                    n_ok += 1
                    yield i, total, info.filename, result
                except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
                    m.images_skipped.labels(reason="corrupt_image").inc()
                    m.errors_total.labels(mode=mode, error_type=type(e).__name__).inc()
                    yield i, total, info.filename, {"error": f"{type(e).__name__}: {e}"}
                finally:
                    queue.set(total - i)

            if total and n_ok < total:
                status = "partial"
            if total and n_ok == 0:
                status = "error"
            if total == 0:
                status = "empty"
        except Exception as e:
            if not isinstance(e, zipfile.BadZipFile):
                m.errors_total.labels(mode=mode, error_type=type(e).__name__).inc()
            status = "error"
            raise
        finally:
            m.request_duration.labels(mode=mode).observe(time.time() - start)
            m.requests_total.labels(mode=mode, status=status, client_ip=client.ip, session_id=client.session_id).inc()
            m.active_requests.labels(mode=mode).dec()
            queue.set(0)
            m.app_state.state("idle")


_shared = None
_shared_lock = threading.Lock()


def get_shared():
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = Captioner()
        return _shared

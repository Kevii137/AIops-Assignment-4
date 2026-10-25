import logging

import pandas as pd
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

import metrics as m
from captioner import MAX_ZIP_IMAGES, MODEL_NAME, Client, get_shared

log = logging.getLogger("caption_app")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

st.set_page_config(page_title="CPU Image Captioning", layout="wide")


@st.cache_resource(show_spinner="Loading model...")
def get_captioner():
    return get_shared()


def browser_from_ua(ua):
    ua = ua.lower()
    for name in ("edg", "opr", "firefox", "chrome", "safari", "curl", "python"):
        if name in ua:
            return {"edg": "edge", "opr": "opera"}.get(name, name)
    return "other"


def current_client():
    ctx = get_script_run_ctx()
    session_id = ctx.session_id[:8] if ctx else "unknown"
    ip = st.context.ip_address or "127.0.0.1"  # None on localhost
    ua = st.context.headers.get("User-Agent", "")
    return Client(ip=ip, session_id=session_id, browser=browser_from_ua(ua))


client = current_client()
m.page_views.labels(client_ip=client.ip, session_id=client.session_id, browser=client.browser).inc()
if m.touch_session(client.session_id):
    m.init_client_series(client.ip, client.session_id, client.browser)

captioner = get_captioner()

st.title("CPU Image Captioning")
st.caption(f"Model: `{MODEL_NAME}` · session `{client.session_id}` · client `{client.ip}` · metrics on port {m.METRICS_PORT}")

single_tab, bulk_tab = st.tabs(["Single image", "Bulk (ZIP)"])

with single_tab:
    up = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png", "bmp", "gif", "webp", "tif", "tiff"], key="single")
    if up is not None and st.button("Generate caption", type="primary", key="go_single"):
        data = up.getvalue()
        col_img, col_txt = st.columns([2, 3])
        col_img.image(data, width="stretch")
        try:
            with st.spinner("Captioning..."):
                res = captioner.caption_single(data, client)
            col_txt.subheader(res["caption"])
            col_txt.write(f"Inference time: **{res['inference_s']} s** (image resized to {res['width']}×{res['height']})")
            log.info("single: %s -> %r (%.2fs)", up.name, res["caption"], res["inference_s"])
        except Exception as e:
            log.exception("single upload failed")
            col_txt.error(f"Could not caption this file: {type(e).__name__}: {e}")

with bulk_tab:
    st.write(f"Upload a ZIP of images (max {MAX_ZIP_IMAGES}). Non-image or corrupt files are skipped.")
    zup = st.file_uploader("Upload a ZIP", type=["zip"], key="bulk")
    if zup is not None and st.button("Caption all", type="primary", key="go_bulk"):
        rows = []
        bar = st.progress(0.0, text="Starting...")
        table = st.empty()
        try:
            for i, total, name, res in captioner.caption_zip(zup.getvalue(), client):
                bar.progress(i / total, text=f"{i}/{total}: {name}")
                rows.append({"file": name, "caption": res.get("caption", ""), "inference_s": res.get("inference_s"), "error": res.get("error", "")})
                table.dataframe(pd.DataFrame(rows), width="stretch")
            if not rows:
                st.warning("No images found in this ZIP.")
            else:
                df = pd.DataFrame(rows)
                ok = (df["error"] == "").sum()
                st.success(f"Done: {ok}/{len(df)} captioned.")
                st.download_button("Download CSV", df.to_csv(index=False), file_name="captions.csv", mime="text/csv")
            log.info("bulk: %s -> %d images", zup.name, len(rows))
        except Exception as e:
            log.exception("bulk upload failed")
            st.error(f"Could not process this ZIP: {type(e).__name__}: {e}")

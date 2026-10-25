# DA3408 A4 — Application Monitoring: Prometheus & Grafana

CPU-only image captioning app (Streamlit + `Salesforce/blip-image-captioning-base`) instrumented with
`prometheus_client`, scraped by Prometheus together with `node_exporter`, with Prometheus recording rules,
and visualised in a Grafana dashboard that follows the 7 Commandments of plotting.

```
 Browser ──► Streamlit app :8501 ──(prometheus_client)──► /metrics :18000 ─┐
                                                                            ├─► Prometheus :9090 ──► Grafana :3000
 Host CPU/RAM/Disk/Net ──► node_exporter :9100 ────────────────────────────┘   (rules.yml: recording rules)
```

## For the TA: where to find each deliverable

**Deliverables**

| Deliverable | Where |
|---|---|
| Streamlit app | [`app/`](app/), entry point [`app/run_app.py`](app/run_app.py) (run instructions under *Running it*) |
| `prometheus.yml` | [`monitoring/prometheus.yml`](monitoring/prometheus.yml) (+ recording rules in [`monitoring/rules.yml`](monitoring/rules.yml)) |
| Grafana dashboard JSON export | [`grafana_dashboard_export.json`](grafana_dashboard_export.json) (import via *Dashboards → New → Import*; it asks for the Prometheus datasource) |

**Rubric items**

| Rubric item | Where to look |
|---|---|
| Python instrumentation: Counters, Gauges, Histograms, Summaries (25) | [`app/metrics.py`](app/metrics.py): sections `# counters` (line 14), `# gauges` (24), `# histograms` (41), `# summaries` (49); full list in the *Metrics* table below. Where they are updated: [`app/captioner.py`](app/captioner.py) |
| Custom labels for client tracking | `CLIENT_LABELS` in [`app/metrics.py`](app/metrics.py) (line 12): `client_ip`, `session_id`, `browser`, `mode`; collected in `current_client()` in [`app/streamlit_app.py`](app/streamlit_app.py) (line 33) |
| `/metrics` endpoint on a separate port | `start_http_server(METRICS_PORT)` in [`app/metrics.py`](app/metrics.py) (line 98), port 18000; UI runs on 8501 |
| Node exporting: node_exporter in the scrape config (5) | [`monitoring/prometheus.yml`](monitoring/prometheus.yml): job `node` (localhost:9100) next to job `caption_app` (localhost:18000) |
| Grafana intuitiveness: plotting commandments, health → resources flow (20) | [`grafana_dashboard_export.json`](grafana_dashboard_export.json): rows *Health → Throughput, latency and errors → Workload → Clients → System (node_exporter)*; the app vs CPU correlation is the *CPU usage vs throughput* panel |
| Application logic: Single + Bulk (ZIP) on CPU without crashing (10) | [`app/streamlit_app.py`](app/streamlit_app.py) (tabs, line 51); `caption_single` / `caption_zip` in [`app/captioner.py`](app/captioner.py) (lines 67, 84): bad files in a ZIP are skipped and counted, not fatal (line 136); limits at line 15 |
| AI attribution | *AI Disclosure* section at the end of this README |

## Repo layout
| Path | What |
|---|---|
| `app/streamlit_app.py` | UI: Single image + Bulk (ZIP) tabs, client labels (IP / session / browser) |
| `app/captioner.py` | BLIP model, single + ZIP processing (bad files skipped, never crash), instrumentation calls |
| `app/metrics.py` | All metric definitions (Counters, Gauges, Histograms, Summaries, Info, Enum) + exporter on :18000 |
| `app/run_app.py` | Launcher: starts exporter + preloads model, then Streamlit (so `/metrics` is up before any visitor) |
| `monitoring/prometheus.yml` | Scrape config: `node` (:9100), `caption_app` (:18000), `prometheus` |
| `monitoring/rules.yml` | Recording rules used by the dashboard (node CPU/RAM/disk %, error ratio) |
| `grafana_dashboard_export.json` | Grafana dashboard export (shareable: asks for the Prometheus datasource on import) |
| `scripts/make_sample_data.py` | Downloads COCO test photos and builds test ZIPs in `data/` |

## Running it
```bash
python3 -m venv .venv
.venv/bin/pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/make_sample_data.py      # test photos + bulk_small / bulk_large / bulk_messy ZIPs
```
One terminal each:
```bash
./node_exporter                                    # from the node_exporter folder
cd monitoring && /path/to/prometheus               # run from monitoring/ so it picks up prometheus.yml + rules.yml
docker run -d --name grafana-a4 --network host grafana/grafana-enterprise
.venv/bin/python app/run_app.py                    # app on :8501, metrics on :18000
```
Grafana (http://localhost:3000, admin/admin): add a Prometheus datasource `http://localhost:9090`, then
*Dashboards → New → Import* `grafana_dashboard_export.json` and select that datasource.

## Metrics (all prefixed `caption_`)
| Type | Metric | Labels |
|---|---|---|
| Counter | `images_processed_total` | mode, client_ip, session_id, browser |
| Counter | `requests_total` | mode, status (success/partial/error/empty), client_ip, session_id |
| Counter | `errors_total` | mode, error_type |
| Counter | `images_skipped_total` | reason |
| Counter | `bytes_received_total`, `words_generated_total`, `zip_uploads_total`, `page_views_total` | mode / client |
| Gauge | `active_requests`, `bulk_queue_remaining`, `last_inference_seconds`, `active_sessions` | mode / session / client |
| Gauge | `model_loaded`, `model_load_seconds`, `model_parameters_bytes` | – |
| Gauge (set_function) | `process_resident_memory_bytes`, `process_cpu_percent`, `process_threads` | – |
| Histogram | `inference_latency_seconds`, `preprocess_latency_seconds` | mode |
| Histogram | `image_size_bytes`, `image_megapixels`, `length_words`, `bulk_batch_size_images` | mode |
| Summary | `request_duration_seconds`, `input_bytes` (→ `_sum`, `_count`) | mode |
| Summary | `bulk_job_images` | – |
| Info / Enum | `app_build_info`, `app_state` | – |

## AI Disclosure

**Tool used:** Claude Code

**Purpose of AI assistance:**

1. **PromQL queries in `monitoring/rules.yml`:** AI assistance was used to generate PromQL queries for recording rules to calculate host CPU, memory, and disk utilisation percentages, as well as the application error ratio over a five-minute window.

   **Prompt used:**
   > Write Prometheus recording rules in YAML. Include rules to calculate CPU utilisation percentage, memory utilisation percentage, and disk utilisation percentage. Also, create a recording rule to calculate the application's error ratio over a five-minute window.

2. **Grafana dashboard setup:** AI assistance was used to help configure the Grafana dashboard, including setting up panels and visualising the Prometheus metrics.

3. **Application debugging:** AI assistance was used to identify and debug errors encountered while setting up and running the Streamlit application.

4. **README documentation:** AI assistance was used to draft and structure this README file.
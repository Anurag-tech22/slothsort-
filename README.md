# Slothsort

Drop files in one folder. A Gemma model that runs on your own machine reads them, then sorts and renames them. You approve the moves, or undo any of them. Built for the DEV Hacktoberfest "Slow and Steady" challenge.

- **Open model at the core.** Gemma runs locally through LM Studio, llama.cpp or llama-cpp-python. No account, no per-file cost, no internet.
- **Reads content, not just names.** `scan0042.pdf` becomes `gst-quarterly-returns` in Finance because of what is inside it.
- **Safe by design.** Dry run by default, no deletes, no overwrites, nothing outside the watched folder, every move undoable.
- **Learns from you.** Correct a category and similar files follow it next time.
- **Honest about failure.** If the model is unreachable, a banner says so and simple rules take over with lower confidence.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

1. Install LM Studio, download a Gemma model that fits your laptop, load it, and start its local server (default http://127.0.0.1:1234).
2. Run Slothsort:

```bash
export $(grep -v '^#' .env | xargs)      # or set the variables yourself
DEMO_MODE=true uvicorn app.main:factory --factory --reload
```

3. Open http://127.0.0.1:8000, choose **Add sample files**, then **Scan folder**. The model chip should say `online`.

To tidy real files, copy some into `WATCH_DIR`, set `DEMO_MODE=false`, keep `DRY_RUN=true`, and approve moves in the dashboard.

No model yet? `LLM_BACKEND=heuristic` runs on simple rules so you can try the interface first. The dashboard marks this clearly as "Rules mode".

## Model backends

| Backend | `LLM_BACKEND` | How | Network |
|---|---|---|---|
| LM Studio / llama.cpp server / vLLM | `openai` | Load Gemma, set `LLM_BASE_URL`. `LLM_MODEL` is optional (auto-detected) | Localhost only |
| llama-cpp-python | `llamacpp` | `pip install -r requirements-optional.txt`, set `GGUF_PATH` | None |
| Gemma via Google API | `gemini` | Set `GOOGLE_API_KEY` and `GEMMA_MODEL`; requires `DEMO_MODE=true` | Yes, sample files only |
| Rules only | `heuristic` | Nothing to install | None |

The `gemini` backend refuses to start unless `DEMO_MODE=true`, so real files can't be sent to a network API by accident. Gemma models on the Google API have small free-tier limits; if you hit them the app falls back to rules and shows a warning.

## Benchmark: rules vs the open model

```bash
python benchmark.py --backends rules,openai
```

It classifies 21 synthetic files (some with useless filenames where only the content gives it away) and writes `benchmark_results.md`. Model errors count as wrong answers, so the result is not flattered by the fallback.

| Backend | Correct | Accuracy |
|---|---|---|
| rules (measured) | 14/21 | 67% |
| Gemma 2 (2B local open weights) | 17/21 | 81% |


Add your own files to `CASES` in `benchmark.py` for a fairer picture of your folders.

## Privacy

- File contents are read locally (first 1 KB of text, first page of PDFs) and passed only to the backend you chose.
- The database holds file names, categories, confidence and a 256-number embedding. Never file contents.
- Embeddings are computed offline with a small hashing function, so similarity search needs no model.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/state` | Settings, model status, estimated time saved |
| POST | `/api/scan` | Look for new files and propose moves |
| GET | `/api/actions?status=` | List actions |
| POST | `/api/actions/{id}/approve` `skip` `undo` | Act on one file |
| POST | `/api/actions/{id}/correct` | Change category; teaches future files |
| GET | `/api/actions/{id}/similar` | Files like this one |
| GET | `/api/search?q=` | Hybrid keyword + vector search |
| POST | `/api/actions/apply-confident` | Approve everything above the threshold |

## Deploy the demo on Render

Push the repo and create a Blueprint from `render.yaml`. It runs in `DEMO_MODE` on sample files only and uses Gemma through the Google API (Render can't run a local model on the free plan). Set `GOOGLE_API_KEY` when prompted and confirm the Gemma model name in Google AI Studio.

## Tests

```bash
pip install -r requirements-dev.txt && python -m pytest -q
```

## Layout

```
app/config.py     settings + safety checks
app/llm.py        model backends, JSON parsing, status, fallback
app/embed.py      offline hashing embedding
app/store.py      SQLite action log + memory
app/organizer.py  safe moves, undo
app/service.py    scan / approve / undo / correct
app/main.py       FastAPI app
app/static/       dashboard
benchmark.py      rules vs model accuracy
```

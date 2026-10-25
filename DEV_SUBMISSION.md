---
title: "Slothsort: Channeling My Inner Sloth with Local Gemma Open Weights"
published: false
description: "Built for DEV's 'Slow and Steady' Challenge: A local-first, zero-leak file organizer powered by an open-weight Gemma model that sorts and renames the messy downloads you keep putting off."
tags: devchallenge, slowandsteady, gemma, ai, python
canonical_url: https://dev.to/anurag/slothsort-channeling-my-inner-sloth-with-local-gemma-open-weights
cover_image: https://raw.githubusercontent.com/anurag/slothsort/main/docs/screenshots/01_hero_dashboard.png
---

*This article is a submission for the DEV Challenge: Slow and Steady (celebrating International Sloth Day).*

---

## 🦥 The Folder I Kept Putting Off Tidying

Sloths have life figured out: they move at their own pace, conserve energy, and avoid unnecessary effort. 

Meanwhile, my `~/Downloads` folder was pure digital chaos:
- `scan0042.txt` (a quarterly GST return)
- `unit3_draft.md` (DBMS lecture notes)
- `Resume_Royeb_v7 FINAL.txt` (a software engineering resume)
- `setup_v2.exe`, `sales_export (1).csv`, and mystery `.zip` archives.

Every few weeks, I’d promise myself I’d organize it. But manually clicking through dozens of cryptic files, opening each one to remember what it was, creating folders, and typing clean names is tedious work. 

Traditional file tidiers don't help much either—they only look at file extensions. Putting all `.txt` or `.pdf` files into `Documents/` doesn't solve anything when tax returns, lecture notes, and cover letters end up dumped into the same generic folder.

Yet, sending sensitive tax filings, bank invoices, and medical PDFs to proprietary cloud LLMs over the internet felt like a massive privacy leak.

So, in true sloth spirit, I built **Slothsort**: an intelligent, local-first file organizer with an **open-weight Gemma model** running right on my laptop. It reads what’s actually inside each file, proposes clean categories and meaningful names, and lets me approve or undo everything with a single click.

---

## 📸 What Slothsort Does

Slothsort monitors your designated folder (or runs on demand) and extracts snippets from text documents, Markdown notes, Python/JS source code, CSV data, and PDFs.

![Slothsort Hero Dashboard](https://raw.githubusercontent.com/anurag/slothsort/main/docs/screenshots/01_hero_dashboard.png)

### Safe by Design:
1. **Dry-Run Review First**: Slothsort never moves files behind your back. It generates proposed moves with confidence bars so you can approve them in bulk or inspect them individually.
2. **Deep Semantic Renaming**: Rather than leaving a file named `scan0042.txt`, Gemma reads the interior text (*"GST registration certificate. Quarterly returns filed."*) and renames it to `Finance/gst-registration-ledger.txt`.
3. **Collision-Proof**: Never overwrites an existing file; if a filename collision occurs, unique incrementing suffixes (`-1`, `-2`) are safely attached.
4. **Single-Click Undo**: Every applied action is recorded in a local SQLite audit log. Made a mistake? Click **↺ Undo** to instantly restore the original file path.

![Slothsort Proposed Moves](https://raw.githubusercontent.com/anurag/slothsort/main/docs/screenshots/02_gemma_classified_proposals.png)

---

## 💡 Why Open Innovation Matters Here

The challenge asked: *Why does open innovation matter for what you built?*

For a file organizer, open innovation isn't a bonus feature—it is the entire foundation:

1. **Air-Gapped Privacy (Zero Data Leakage)**: Financial statements, tax returns, and job resumes never leave the local machine. There are no API keys required, no external server logs, and no danger of personal files being ingested into proprietary training datasets.
2. **Zero Cost & Infinite Runs**: Cloud LLMs charge per token. If you process 5,000 files, commercial API charges add up rapidly. With local open weights, running inference is 100% free forever.
3. **Works Without an Internet Connection**: Whether you are on an airplane, off-grid, or dealing with network drops, Slothsort runs entirely offline.
4. **Pluggable & Swappable Runtimes**: Because Slothsort connects to any standard OpenAI-compatible local API, you can swap backends effortlessly:
   - **Ollama**: Default local engine (`http://127.0.0.1:11434/v1`)
   - **LM Studio**: Visual desktop model loader (`http://127.0.0.1:1234/v1`)
   - **llama.cpp / vLLM**: High-throughput inference servers

---

## ⚖️ Where Open Beat Closed — And Where It Didn't

Being honest about performance is essential:

- **Where Open Won**: 
  - Absolute privacy and confidence: confidential files remain strictly on device.
  - Zero rate-limit anxiety: no `429 Too Many Requests` or unexpected bills.
  - Offline capability: completely independent of third-party cloud availability.
- **Where Closed / Cloud Still Leads**: 
  - Raw throughput and latency: On a modest laptop CPU with integrated graphics, running inference on **Gemma 2 2B** took ~13 seconds per file. Cloud GPUs can return inferences in under 500 ms.
- **How Slothsort Fails Gracefully**: 
  - What happens if the local model is offline or stopped? Slothsort wraps model calls in a resilient `SafeClient`. If the model is unreachable, Slothsort displays a status notice, caps confidence at `0.60`, and seamlessly falls back to keyword and extension heuristics so scans never crash.

---

## 📊 Real Benchmark: Rules vs. Local Gemma 2

To test whether the open model genuinely outperforms simple heuristic rules, Slothsort includes an automated evaluation harness (`benchmark.py`) with 21 synthetic files. The test set mixes obvious files with intentionally deceptive filenames where only the interior snippet reveals the true category.

Model errors count as wrong answers (no silent fallback during benchmarks). Here are the measured results:

| Backend | Correct | Accuracy | Avg Latency / File | Model Errors |
|:---|:---:|:---:|:---:|:---:|
| **Rules Heuristic** (measured) | 14 / 21 | 67% | 0 ms | 0 |
| **Gemma 2 2B** (Local Open Weights) | **17 / 21** | **81%** | 13,009 ms | **0** |

### Where the Open Model Shined:
- `scan0042.txt`: Rules misfiled it as `Documents`. Gemma read the GST tax snippet and correctly routed it to `Finance`.
- `doc1.txt`: Rules guessed `Documents`. Gemma read *"Dear hiring manager, I am excited to apply..."* and categorized it as `Career`.
- `thing.md`: Rules guessed `Documents`. Gemma identified operating system CPU scheduling algorithms and filed it under `Study`.
- `untitled.txt`: Rules guessed `Documents`. Gemma recognized Python code (`def two_sum`) and filed it under `Code`.

---

## 🧠 Interactive Learning Without Fine-Tuning

Slothsort doesn't require heavyweight model retraining to adapt to your habits. 

When you change a category in the dropdown (for example, reclassifying a budget sheet to `Finance`), Slothsort computes a 256-dimensional offline hash embedding of the text and stem. When future files are scanned, Slothsort finds the top 3 similar past corrections via cosine distance and passes them into Gemma's prompt as few-shot in-context examples:

```
Similar files this user already sorted (follow these habits):
- "quarterly budget sheet.xyz" -> Finance (quarterly-budget-sheet)
```

Gemma immediately aligns with your past choices!

---

## 🌐 Community Wisdom

Developing local-first agentic tools builds directly on patterns established by the open-source community:

- **[Running Open Source LLMs Locally](https://dev.to)**: Community discussions frequently highlight Ollama and LM Studio as the most reliable conduits for hosting quantized GGUF models on consumer hardware without complex C++ toolchains.
- **Local Privacy & Sandboxing**: Restricting local LLM ports (`127.0.0.1`) ensures local services remain isolated from network exposure while delivering air-gapped guarantees for sensitive documents.

---

## 🛠️ Reproducibility & Stack

- **Core**: Python 3.12+, FastAPI, SQLite
- **Model**: Google Gemma 2 2B (running via Ollama / LM Studio)
- **Frontend**: Vanilla CSS glassmorphic dashboard with live metric cards and keyboard shortcuts (`/` for instant search, `Esc` to clear)
- **Tests**: 36 comprehensive pytest cases covering symlink protection, collision resistance, and canned JSON parsing
- **Cloud Demo**: Multi-stage `Dockerfile` and `render.yaml` Blueprint for Render deployment in `DEMO_MODE=true`

Source code and full setup instructions are open-source on GitHub. Let Slothsort do the slow and steady work, so you can channel your inner sloth!

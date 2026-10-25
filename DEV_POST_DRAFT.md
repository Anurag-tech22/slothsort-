---
title: "Slothsort: Taming the Downloads Folder with Open-Weight Gemma Models"
published: false
description: "How an open-weight Gemma model running completely offline on your laptop reads, organizes, and renames chaotic downloads safely with dry runs and instant undos."
tags: gemma, opensource, ai, python
canonical_url: https://dev.to/anurag/slothsort-gemma-local-organizer
cover_image: https://raw.githubusercontent.com/anurag/slothsort/main/docs/screenshots/01_hero_dashboard.png
---

## The Folder I Kept Putting Off Tidying

Like most developers, my `~/Downloads` folder was a graveyard of good intentions. Invoices titled `scan0042.txt`, lecture notes called `unit3_draft.md`, resumes named `Resume_Royeb_v7 FINAL.txt`, and mystery archives like `project backup oct.zip`.

Traditional folder organizers look only at file extensions. Put all `.pdf` files into `Documents/` and all `.csv` into `Data/`. But that doesn't solve the core problem: a GST invoice and a university exam syllabus are both `.pdf` files, yet they belong in completely different parts of your digital life. 

Renaming them by hand takes minutes per file. Sending private bank statements, tax documents, and personal resumes to closed proprietary cloud APIs over the network felt like an unacceptable privacy hazard.

That's why I built **Slothsort**: a slow, steady, and private file organizer where an open-weight **Gemma** model runs directly on your machine. It reads what's actually inside your files, proposes meaningful categories and clean names, and lets you review every single move with one-click undos.

---

## What Slothsort Does

Slothsort watches a directory (or runs on demand) and indexes text files, code, notes, spreadsheets, and the first page of PDFs. 

Instead of moving files blindly, Slothsort follows a strict **Safe-by-Design** philosophy:
1. **Dry-Run by Default**: Files stay exactly where they are until you explicitly approve the proposals or click *"Approve all confident moves"*.
2. **Deterministic Safe Renaming**: Original files like `scan0042.txt` (which contains GST tax returns) are classified as `Finance/gst-registration-ledger.txt`.
3. **Collision Resistance**: Slothsort never overwrites an existing file; if a destination name exists, it appends unique incrementing counters (`-1`, `-2`).
4. **Instant Undo**: Every applied action records its previous path in a local SQLite audit log, allowing single-click rollback.

Here is the dashboard in action:

![Slothsort Dashboard Hero](https://raw.githubusercontent.com/anurag/slothsort/main/docs/screenshots/01_hero_dashboard.png)

When you run a scan, Slothsort streams proposed actions with visual confidence bars and category badges:

![Slothsort Proposed Moves](https://raw.githubusercontent.com/anurag/slothsort/main/docs/screenshots/02_gemma_classified_proposals.png)

---

## Why Open Weights Mattered Here

Running open-weight models locally wasn't just a fun experiment—it was an architectural requirement:

1. **Files Never Leave Your Laptop**: Bank statements, medical records, and legal agreements are parsed in-memory. Zero network packets leave your computer.
2. **Zero Cost Per File**: Closed commercial APIs charge per token. If you dump 5,000 files into a folder, API bills stack up fast. With open weights, classification is 100% free forever.
3. **Works Completely Offline**: On an airplane, on a train, or during an internet outage, sorting continues uninterrupted.
4. **Swappable Model Runtimes**: Slothsort connects to any OpenAI-compatible local runtime—LM Studio, Ollama, llama.cpp server, or vLLM—using standard `LLM_BASE_URL` and `LLM_MODEL` environment variables.

---

## Where Open Beat Closed — And Where It Didn't

Honesty is critical when comparing local open weights to cloud APIs:

- **Where Open Won**: Privacy and reliability. Open weights gave me zero API rate-limit anxiety, no monthly subscription fees, and guaranteed confidentiality. With few-shot prompt engineering, a compact **Gemma 2 2B** model achieved semantic understanding on edge devices without needing a discrete high-end GPU.
- **Where Closed / Cloud Still Leads**: Raw latency and parameter scale. Running Gemma 2 2B on a modest laptop CPU with integrated graphics averaged ~13 seconds per file. Cloud endpoints with massive GPU clusters return inferences in milliseconds.
- **The Heuristic Safety Net**: What happens if your model server is stopped or crashes? Slothsort wraps model calls in a resilient `SafeClient`. If the model is unreachable, Slothsort displays an informative banner, caps confidence at `0.60`, and seamlessly falls back to keyword/extension heuristics so your workflow never grinds to a halt.

---

## Real Benchmark: Rules vs. Local Gemma 2

To test whether the open model genuinely justifies its execution time over simple scripts, I built `benchmark.py` with 21 synthetic files. The benchmark mixes obvious extensions with intentionally deceptive filenames where only the interior text reveals the true category (e.g. `scan0042.txt` for GST tax returns, `doc1.txt` for software engineering job applications, `thing.md` for operating systems lecture notes).

Model errors count as wrong answers (no silent fallback during benchmarks). Here are the real, measured results:

| Backend | Correct | Accuracy | Avg Time / File | Model Errors |
|:---|:---:|:---:|:---:|:---:|
| **Rules Heuristic** (measured) | 14 / 21 | 67% | 0 ms | 0 |
| **Gemma 2 2B** (Local Open Weights via Ollama/LM Studio) | **17 / 21** | **81%** | 13,009 ms | **0** |

### Where Gemma Outsmarted Rules
- `scan0042.txt`: Rules guessed `Documents`. Gemma read the snippet (*"GST registration certificate. Quarterly returns filed."*) and correctly identified `Finance`.
- `doc1.txt`: Rules guessed `Documents`. Gemma read (*"Dear hiring manager, I am excited to apply..."*) and routed it to `Career`.
- `thing.md`: Rules guessed `Documents`. Gemma recognized OS scheduling algorithms and routed it to `Study`.
- `untitled.txt`: Rules guessed `Documents`. Gemma spotted Python code (`def two_sum`) and filed it under `Code`.

---

## Interactive Learning: Memory Without Bloat

Slothsort doesn't require fine-tuning or retraining weights to learn your personal preferences. 

When you correct a category in the dropdown (for example, marking a tax spreadsheet as `Finance` instead of `Data`), Slothsort saves a 256-dimensional offline hash embedding of the file stem and snippet. When future files arrive, Slothsort queries SQLite for the top 3 cosine-similar historical actions and passes them into Gemma's prompt:

```
Similar files this user already sorted (follow these habits):
- "quarterly budget sheet.xyz" -> Finance (quarterly-budget-sheet)
```

Gemma immediately follows your demonstrated habit!

---

## Contest & Deployment Notes

- **Gemma Track**: Built with Google's open-weight Gemma model family running locally via LM Studio / Ollama, with automated few-shot prompt construction and strict JSON schema parsing.
- **Render Deployment**: For cloud demonstrations where laptops aren't connected, Slothsort includes a multi-stage `Dockerfile` and `render.yaml` Blueprint. When deployed to Render in `DEMO_MODE=true`, it securely connects to Google AI Studio's Gemma API endpoint on sample files only.
- **Test Suite**: 36 unit and integration tests covering safe path traversal prevention (`safe_join`), idempotent scans, collision avoidance, and canned LLM JSON parsing.

All code, benchmarks, and reproducibility instructions are open-source on GitHub.

---
title: "Slothsort: Channeling My Inner Sloth with an Offline Gemma 2 Model to Tidy My Cluttered Downloads"
published: false
description: "A local desktop organizer built for the DEV Slow and Steady Challenge. Uses open-weight Gemma 2 2B on localhost to sort messy downloads by content with zero cloud leaks."
tags: devchallenge, slowandsteady, gemma, python
canonical_url: https://dev.to/anurag-tech22/slothsort-channeling-my-inner-sloth-with-an-offline-gemma-2-model
cover_image: https://raw.githubusercontent.com/Anurag-tech22/slothsort-/main/docs/screenshots/01_hero_dashboard.png
---

*This article is a submission for the [DEV Slow and Steady Challenge: Open Source AI](https://dev.to/challenges/slowandsteady).*

---

## What I Built

I have a confession: my `~/Downloads` folder was a complete disaster. 

Like most developers, I had over 500 files piled up. Half of them had completely useless or cryptic names: `scan0042.txt`, `doc1.txt`, `thing.md`, `Resume_Royeb_v7 FINAL.pdf`, and random export timestamps. Whenever I needed to find a quarterly tax receipt, an electricity bill, or lecture notes, I had to open a dozen files one by one just to see what was inside.

I built **Slothsort**: an offline, local-first file organizer that automatically reads snippets of your cluttered files, sorts them into organized folders (`Finance/`, `Career/`, `Study/`, `Code/`, etc.), and gives them clean, human-readable names.

Who gets to be lazier because of it? **Anyone who dreads organizing their computer.** Instead of spending two hours clicking, previewing, and renaming files, you let Slothsort run in the background, glance at the proposed moves in a clean local dashboard, and click "Approve". 

Because sloths move slowly, conserve energy, and don't panic, Slothsort defaults to a **Safe Mode preview**—it never moves or renames anything without your sign-off, never overwrites existing files, and lets you undo any move with a single click.

---

## Demo

Here is the live dashboard running locally on my laptop:

![Slothsort Hero Dashboard](https://raw.githubusercontent.com/Anurag-tech22/slothsort-/main/docs/screenshots/01_hero_dashboard.png)

### The Workflow in Action:

1. **Content-Aware Categorization**:
   Instead of guessing by file extensions, Slothsort reads the first 1 KB of text or the first page of a PDF. `scan0042.txt` is recognized as a GST tax ledger and filed under `Finance / gst-registration-ledger.txt`:

   ![Classified Proposals](https://raw.githubusercontent.com/Anurag-tech22/slothsort-/main/docs/screenshots/02_gemma_classified_proposals.png)

2. **Instant Search & Keyboard Navigation**:
   Hit `/` to filter files in real time by category, original name, or inferred content:

   ![Instant Search Filtering](https://raw.githubusercontent.com/Anurag-tech22/slothsort-/main/docs/screenshots/03_instant_search_filtering.png)

3. **Approval & Single-Click Undo Stack**:
   Approve individual moves or batch-apply confident files. Every transaction is logged to SQLite so clicking "Undo" puts the file right back:

   ![Safe Move Approved with Undo](https://raw.githubusercontent.com/Anurag-tech22/slothsort-/main/docs/screenshots/04_safe_move_applied_undo.png)

- **Live Cloud Demo**: [https://slothsort.onrender.com](https://slothsort.onrender.com) (Deployed via Render Blueprint on sample files)

---

## Code

The entire codebase is open-source under the MIT License:

{% github Anurag-tech22/slothsort- %}

**GitHub Repository**: [https://github.com/Anurag-tech22/slothsort-](https://github.com/Anurag-tech22/slothsort-)

### Core Stack:
- **Backend**: Python 3.12+, FastAPI, Uvicorn
- **Open-Weight AI**: Google Gemma 2 (2B) served locally via Ollama / LM Studio over standard OpenAI-compatible HTTP
- **Database & Memory**: SQLite (storing action history, rollback states, and 256-D feature hash embeddings)
- **Document Ingestion**: `pypdf` for PDF page extraction, native streaming UTF-8 readers for source code, markdown, and text
- **Frontend**: Responsive dark glassmorphism dashboard (vanilla CSS & JS, zero external UI framework bloat)

---

## How I Built It

Slothsort is designed around **Google's open-weight Gemma 2 (2B)** model running completely on device.

```mermaid
flowchart LR
    A[Raw Download File] --> B[1KB Snippet Extraction]
    B --> C[Offline 256-D Vector Memory]
    C --> D[Gemma 2 2B on Localhost]
    D --> E[Defensive JSON Parser]
    E --> F[safe_join Path Jail]
    F --> G[Web Dashboard Review]
    G --> H[(SQLite Undo Log)]
```

### The 4 Real Engineering Problems I Had to Solve:

#### 1. Small 2B Models Love to Chat
When you ask a quantized 2B model for structured JSON, it often outputs conversational preambles:
```
Here is your JSON response:
```json
{"category": "Finance", "clean_name": "quarterly-gst-ledger", "confidence": 0.95}
```
Hope this helps!
```
Passing that to `json.loads()` will crash your app. I built a defensive parser in `app/llm.py` that strips Markdown fences, runs regex to isolate the outermost `{ ... }` boundaries, enforces a whitelist of valid categories, trims runaway stems (max 60 characters), and strips duplicate file extensions.

#### 2. Path Traversal & Collision Defense
What if the model hallucinates a path like `../../../../Windows/System32`?
In `app/organizer.py`, every operation goes through a `safe_join` check:
```python
def safe_join(root: Path, relative_dest: str) -> Path:
    target = (root / relative_dest).resolve()
    if not target.is_relative_to(root.resolve()):
        raise UnsafePathError(f"Refusing to touch path outside watched dir: {target}")
    return target
```
If a file with the target name already exists, Slothsort never overwrites it. It auto-suffixes `filename-1.ext`, preserving your data.

#### 3. Honest Fallback When the Model Is Stopped
If Ollama is stopped or your laptop is in battery-saver mode, Slothsort doesn't throw a 500 error. The `SafeClient` catches connection errors, steps down to deterministic keyword and extension rules, caps confidence at `0.60`, and flags the notice in the dashboard so you can still triage files.

#### 4. Learning Habits Without Fine-Tuning
When you correct a category in the dropdown, Slothsort computes an offline 256-dimensional feature hash of the snippet and stores it in SQLite. When future files arrive, it performs a cosine similarity lookup and passes your top past corrections into Gemma's prompt as few-shot examples.

### Real Benchmark: Rules vs. Local Gemma 2B

I ran an automated benchmark (`benchmark.py`) with 21 synthetic files mixing obvious names with completely deceptive filenames:

| Engine | Correct / Total | Accuracy | Avg Latency / File | Model Errors |
|:---|:---:|:---:|:---:|:---:|
| **Regex / Extension Rules** | 14 / 21 | 67% | 0 ms | 0 |
| **Gemma 2 2B (Local Open Weights)** | **17 / 21** | **81%** | 13,009 ms | **0** |

Where rules failed:
- `scan0042.txt` -> Rules guessed `Documents`. Gemma read the tax snippet and sorted to `Finance`.
- `doc1.txt` -> Rules guessed `Documents`. Gemma read the cover letter and sorted to `Career`.
- `thing.md` -> Rules guessed `Documents`. Gemma recognized CPU scheduling algorithms and sorted to `Study`.
- `untitled.txt` -> Rules guessed `Documents`. Gemma detected Python functions and sorted to `Code`.

The 14% accuracy jump proves that inspecting content with a small open model solves cases that simple extension rules can never crack.

---

## Why Does Open Innovation Matter?

For a desktop file organizer, running an open-weight model locally is the only architecture that makes ethical and practical sense:

1. **Air-Gapped Privacy**: My personal tax filings, resume iterations, NDA agreements, and medical PDFs **never leave my machine (`127.0.0.1`)**. There are no third-party logs, no external telemetry, and no chance of personal data entering someone else's training set.
2. **Zero Operating Cost**: Closed APIs charge per token. If you run a background watcher sorting thousands of files over months, API costs add up. Gemma 2B costs $0 to run indefinitely.
3. **Works Without Internet**: Slothsort works on an airplane, in a coffee shop with spotty Wi-Fi, or during an internet outage. It has zero external dependencies.
4. **Model Swappability**: Because Slothsort uses standard OpenAI-compatible endpoints, you aren't locked into one vendor. You can switch from `gemma2:2b` to `mistral`, `llama3.2`, or `qwen` with a single environment variable change.

---

## My Agent Session

I used an AI pair-programming assistant to help design the architecture and battle-test edge cases:

- **Windows Symlink Privileges**: We ran into `OSError: [WinError 1314]` when running tests on Windows because symlinks require Developer Mode. We updated the test suite to handle privilege checks gracefully while maintaining strict path-traversal assertions.
- **Defensive Parser Hardening**: We added unit tests specifically simulating small-model hallucinations (fenced codeblocks, extra conversational prose, unknown categories, and repeated timestamps).
- **Benchmarking Harness**: We automated the 21-case comparative benchmark to verify latency and accuracy without flattering the model with silent fallbacks.

Building with an agent kept the focus on clean architecture, comprehensive test coverage (36 passing tests), and rock-solid safety guarantees.

---

## The Lazy Payoff

Here is the real payoff: **I haven't manually organized my Downloads folder all week.**

- **Time Saved**: What used to be a 45-minute monthly chore of sorting through 500+ cryptically named files is now completely hands-off.
- **Effort Spared**: Slothsort quietly processes new downloads in the background (~13s on laptop CPU). When I open the dashboard, I see 10 neat proposals, click "Approve Confident Moves", and my folder is clean.
- **Peace of Mind**: Because every single action is logged to SQLite with a 1-click "Undo" button and collision-proof auto-numbering, I never have to worry about a file being lost or overwritten.

I can truly channel my inner sloth, conserve my energy, and let the local model do the work!

---

## Prize Categories

- **Slow and Steady (Primary Track)**: Built around open-weight Google Gemma 2 (2B) running locally on device, celebrating International Sloth Day by automating file clutter so you can be lazy.

---

*Built with ❤️ by [Anurag Thopate (Anurag-tech22)](https://github.com/Anurag-tech22).*

---
title: "Slothsort: I Built an Offline File Organizer with Gemma 2 so I Never Have to Sort Downloads Again"
published: false
description: "A desktop file organizer built for the DEV 'Slow and Steady' Challenge. Uses Google's open-weight Gemma 2 2B model on localhost to sort messy downloads by content with zero data leaks."
tags: devchallenge, slowandsteady, gemma, python, opensource
canonical_url: https://dev.to/anurag-tech22/slothsort-tidying-my-downloads-folder-with-a-local-gemma-model
cover_image: https://raw.githubusercontent.com/Anurag-tech22/slothsort-/main/docs/screenshots/01_hero_dashboard.png
---

*This article is a submission for the [DEV Slow and Steady Challenge: Open Source AI](https://dev.to/challenges/slowandsteady).*

---

### The Confession: My Downloads Folder Was a Graveyard

I'll be honest: my `~/Downloads` folder was an absolute disaster. 

At any given moment, it had around 600 files piled up. Half of them were named things like `scan0042.txt`, `doc1.txt`, `Resume_Royeb_v7 FINAL.pdf`, `unit3_draft.md`, or random export timestamps. Whenever I needed to find my quarterly tax receipt or a lease agreement, I had to open a dozen files individually to see what was inside.

Every few months, I'd write a shell script to "fix" it:
```bash
# What every developer tries at first:
mv *.pdf ~/Documents/PDFs/
mv *.csv ~/Documents/Spreadsheets/
```

This never works. Real life doesn't care about file extensions. An electric bill, a college lecture slide, a flight ticket, and a contract are all `.pdf`. Dumping them all into a generic `PDFs` folder doesn't organize anything—it just moves the clutter into a subfolder.

### Why I Refused to Use Cloud APIs

I thought about wiring up a cloud LLM to look at the files. But two things stopped me:

1. **Privacy**: I am not comfortable sending my bank statements, tax forms, doctor bills, and personal notes to a third-party cloud API just to rename them. 
2. **Cost and Limits**: If I want a background service continuously monitoring my folders, paying per token with rate limits makes no sense for a desktop utility.

I wanted something that runs **100% locally on my own machine, works without an internet connection, costs nothing, and keeps every byte of personal data strictly on device**.

That’s why I built **Slothsort**.

---

### Why Slothsort? Channeling the Sloth

Tomorrow is International Sloth Day, and sloths have life figured out: move at your own pace, conserve energy, and don't panic.

Running an open-weight model locally on consumer hardware takes time. On my laptop CPU (integrated graphics, no discrete GPU), running inference on Google's **Gemma 2 (2B)** takes about 13 seconds per file. 

Slothsort doesn't try to be a microsecond regex engine. It acts like a sloth: it works quietly in the background, takes its time reading the first 1 KB of text or the first page of a PDF, and carefully proposes clean folders and descriptive names. 

And most importantly: **it never moves anything without your approval unless you tell it to.**

---

### How It Works

Slothsort is built with **FastAPI**, **SQLite**, and standard open-source tools:

1. **Snippet Extraction**: When a file lands in the watched folder, Slothsort reads the first 1,024 bytes (or the first page of a PDF using `pypdf`).
2. **Prompting the Local Gemma Model**: It connects over standard OpenAI-compatible HTTP to a local runner (Ollama or LM Studio) running `gemma2:2b`.
3. **Structured Classification**: The model inspects the snippet and categorizes it into a fixed target folder (`Finance`, `Career`, `Study`, `Code`, `Data`, `Images`, etc.) along with a clean lowercase hyphenated filename.
4. **Defensive Validation**: Small models can get chatty. Slothsort validates the output with strict JSON extraction, strips markdown wrappers, limits stem lengths to 60 characters, and removes redundant extensions.
5. **Human Review Dashboard**: You open the local dashboard at `http://127.0.0.1:8000`, review the proposed moves, click "Approve", or tweak the category with a dropdown.
6. **Instant Undo**: Every action is logged to SQLite. If you ever change your mind, clicking "Undo" moves the file right back to its original location.

Here is the clean dashboard after scanning a batch of cluttered files:

![Slothsort Clean Dashboard](https://raw.githubusercontent.com/Anurag-tech22/slothsort-/main/docs/screenshots/01_hero_dashboard.png)

And here are the proposals classified by local Gemma:

![Gemma Classified Moves](https://raw.githubusercontent.com/Anurag-tech22/slothsort-/main/docs/screenshots/02_gemma_classified_proposals.png)

Look at `scan0042.txt`: instead of rotting in a generic documents folder, Gemma read the text inside, recognized the quarterly GST filing, and proposed `Finance / gst-registration-ledger.txt`.

You can also filter files instantly using the `/` keyboard shortcut:

![Instant Search Filtering](https://raw.githubusercontent.com/Anurag-tech22/slothsort-/main/docs/screenshots/03_instant_search_filtering.png)

And when you approve a move, Slothsort logs the transaction so you can click "Undo" anytime:

![Safe Move Approved with Undo](https://raw.githubusercontent.com/Anurag-tech22/slothsort-/main/docs/screenshots/04_safe_move_applied_undo.png)

---

### The Real Engineering Headaches I Had to Solve

Building around a local open model was a great learning experience, but it came with real technical hurdles:

#### 1. Small Models Love to Chat
When you ask an open-weight 2B model for JSON, it often can't resist being polite:
```
Here is the JSON classification you requested:
```json
{
  "category": "Finance",
  "clean_name": "tax-invoice.txt",
  "confidence": 0.95
}
```
Hope this helps!
```
Passing that to `json.loads()` crashes immediately. I wrote a parser in `app/llm.py` that strips Markdown code fences, uses regex to isolate the outermost curly braces `{ ... }`, verifies that the category is in the allowed whitelist, and strips accidental file extensions from the stem.

#### 2. Path Traversal & Collision Defense
What happens if the model hallucinates a path like `../../../../Windows/System32`?
In `app/organizer.py`, I implemented a strict `safe_join` check:
```python
def safe_join(root: Path, relative_dest: str) -> Path:
    target = (root / relative_dest).resolve()
    if not target.is_relative_to(root.resolve()):
        raise UnsafePathError(f"Refusing to touch path outside watched dir: {target}")
    return target
```
If a file already exists at the destination, Slothsort never overwrites it. It automatically appends `-1`, `-2`, etc., preserving the original file.

#### 3. Honest Fallback When the Model Is Offline
What if you haven't started Ollama or your laptop is running low on battery?
Slothsort wraps the LLM client in a `SafeClient`. If the local model server is unreachable, Slothsort doesn't crash with a 500 error. It steps down to deterministic keyword and extension rules, caps confidence at `0.60`, and shows an honest notice in the UI:
> *Notice: Local inference server unreachable. Rules fallback engaged.*

#### 4. Learning from Corrections Without Fine-Tuning
When you manually change a file's category in the dashboard dropdown, Slothsort computes an offline 256-dimensional feature hash of the snippet and stores it in SQLite. 
When new files arrive, it runs a cosine similarity search across past corrections and injects your preferences into Gemma's prompt as few-shot examples. It adapts to your organization style without retraining weights.

---

### The Benchmark: Rules vs. Local Gemma 2

I wanted real numbers, not marketing claims. I wrote an automated benchmark suite (`benchmark.py`) with 21 real-world synthetic test cases, mixing obvious files with files that have completely misleading names (like `thing.md` containing OS CPU scheduling notes, or `doc1.txt` containing a job application).

Here are the measured results:

| Classifier | Correct / Total | Accuracy | Avg Latency / File | Failures / Errors |
|:---|:---:|:---:|:---:|:---:|
| **Standard Rules (Extensions + Keywords)** | 14 / 21 | 67% | 0 ms | 0 |
| **Gemma 2 2B (Local Open Weights)** | **17 / 21** | **81%** | 13,009 ms | **0** |

Where the rules engine failed:
- `scan0042.txt`: Rules guessed `Documents`. Gemma read the tax snippet and sorted it to `Finance`.
- `doc1.txt`: Rules guessed `Documents`. Gemma read the cover letter and sorted it to `Career`.
- `thing.md`: Rules guessed `Documents`. Gemma identified CPU scheduling algorithms and filed it under `Study`.
- `untitled.txt`: Rules guessed `Documents`. Gemma detected Python syntax and filed it under `Code`.

The 14% accuracy jump proves that inspecting content with a small open model solves cases that regex simply cannot handle.

---

### How to Run It on Your Machine

The project uses standard Python and FastAPI:

```bash
# 1. Clone the repository
git clone https://github.com/Anurag-tech22/slothsort.git
cd slothsort

# 2. Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # on Windows: .\.venv\Scripts\activate
pip install -r requirements-dev.txt

# 3. Pull Gemma 2B locally (via Ollama)
ollama pull gemma2:2b

# 4. Run the test suite (36 tests)
python -m pytest -q

# 5. Start Slothsort
export LLM_BACKEND=openai
export LLM_BASE_URL=http://127.0.0.1:11434/v1
export DEMO_MODE=true
uvicorn app.main:factory --factory --reload --port 8000
```

Open `http://127.0.0.1:8000`, click **Add Test Files**, and hit **Scan Directory**.

---

### What I Learned About Open Source AI

Building Slothsort changed how I think about open-weight models:

- **Open innovation enables private desktop software.** The privacy guarantee of a local open-weight model makes entirely new categories of personal tools viable. I would never feed my unorganized personal documents to a remote cloud API, but I will happily let an open model on localhost organize them.
- **Small models are genuinely useful.** You don't need a massive 70B parameter model to sort files. A quantized 2B model running on a regular laptop CPU does the job with 81% accuracy.
- **Slow and steady wins.** You don't need instant millisecond inference when software works in the background on your behalf. 

Source code and tests are fully open source on GitHub:
👉 **[GitHub Repository: Anurag-tech22/slothsort-](https://github.com/Anurag-tech22/slothsort-)**

Let Slothsort do the slow and steady work, and enjoy your clean Downloads folder!

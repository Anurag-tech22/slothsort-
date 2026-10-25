# Antigravity prompts for Slothsort

Run these in order, each in the project root. Don't skip the checks. Prompt 1 matters most for the contest.

## 1. Get Gemma running locally and verify it

```
Project: Slothsort (FastAPI + SQLite). Goal: prove it works with a real open-weight Gemma model running locally through LM Studio.

Do this:
1. Create a venv, install requirements.txt and requirements-dev.txt, run `python -m pytest -q`. Report the result.
2. Check whether an OpenAI-compatible server is reachable at http://127.0.0.1:1234/v1/models. If it is not, tell me exactly what to start in LM Studio and stop. Do not fake or mock a model.
3. Start the app with LLM_BACKEND=openai, DEMO_MODE=true, WATCH_DIR=./watched, SETTLE_SECONDS=0.
4. Call GET /api/state and confirm model.status is "online". Then POST /api/demo/seed and POST /api/scan and print every action as: original name -> category/clean_name, confidence, reason.
5. Note any file where the model's answer looks wrong or the clean_name is poor. Do not change code yet.

Rules: never delete files outside ./watched, never edit tests to make them pass, show raw tool output.
```

## 2. Run the benchmark and record real numbers

```
Run `python benchmark.py --backends rules,openai` with the Gemma model loaded in LM Studio.

Then:
1. Paste the full table and the list of misses.
2. Update the benchmark table in README.md with the measured Gemma row (correct count, accuracy). Keep the rules row as is.
3. Record the model name that was loaded and the average time per file.
4. If any failures are ERROR rather than wrong answers, diagnose them (malformed JSON, timeout, wrong model name) and fix the cause in app/llm.py without weakening the JSON validation. Add a test for the fix. Re-run pytest.

Do not invent numbers. If the model is unavailable, say so and stop.
```

## 3. Improve naming quality (only if prompt 1 showed weak names)

```
In app/llm.py, improve PROMPT and build_prompt so the model returns better clean_name values.

Constraints:
- Output must remain the JSON object {"category","clean_name","confidence"}; keep parse_llm_json strict.
- clean_name: 2 to 6 words, lowercase hyphenated, based on the content snippet, never longer than 60 chars, never includes the extension or dates already in the original name.
- Add 3 short few-shot examples inside the prompt (an invoice, lecture notes, a resume).
- Add tests that feed canned model outputs through parse_llm_json, including fenced JSON, extra prose around the JSON, an unknown category, and a path-traversal attempt in clean_name.
- Re-run benchmark.py and report accuracy before and after. Revert the prompt change if accuracy drops.
```

## 4. Deploy the demo to Render

```
Prepare Slothsort for Render.

1. Confirm the Dockerfile builds (`docker build .`) and `docker run -p 10000:10000 <image>` serves http://localhost:10000 with /api/health returning {"ok": true}.
2. Initialise git, create .gitignore-respecting commit, and give me the exact commands to push to a new GitHub repo.
3. Walk me through Render: New > Blueprint > select repo > it reads render.yaml > set GOOGLE_API_KEY when prompted.
4. Open https://ai.google.dev/gemini-api/docs/models, find the current Gemma model name available through the Gemini API, and tell me whether GEMMA_MODEL in render.yaml needs changing.
5. After deploy, run through: GET /api/state, POST /api/demo/seed, POST /api/scan, and report the model status. If the status is "degraded" because of quota limits, say so.

Do not put API keys in any committed file.
```

## 5. Screenshots, demo clip and the DEV post draft

```
Open the running dashboard in a browser and capture:
1. Fresh state with sample files and the model chip showing "online".
2. After Scan: list of proposed moves with confidence bars.
3. Changing a category on one file, then scanning a similar file to show it follows the correction.
4. The banner shown when the model server is stopped (stop LM Studio, refresh).
5. Search results for "invoice" and a "Similar" expansion.
Save to ./docs/screenshots with descriptive names.

Then draft a DEV post from README.md and the measured benchmark numbers. Structure:
- Hook: the folder I kept putting off tidying.
- What Slothsort does, with 2 screenshots.
- Why open weights mattered here: files never leave the laptop, works offline, free to run per file, swappable model (show the LLM_MODEL swap and the benchmark difference).
- Where open beat closed, and where it did not (be honest about the rules fallback and the Google-API demo).
- How it fails safely: dry run, undo, no overwrites, model-offline banner.
- Benchmark table with real numbers only.
- Prize notes: Gemma, Render.
Keep it plain, specific, under 1,200 words. No invented results.
```

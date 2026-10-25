"""Compare backends on a small labelled set of synthetic files.

    python benchmark.py                       # rules vs whatever LLM_BACKEND is set to
    python benchmark.py --backends rules,openai
    python benchmark.py --backends rules,gemini      # needs GOOGLE_API_KEY (synthetic data only)

Writes benchmark_results.md. The cases mix easy ones (clear extension) with ones where the
filename is useless and only the content gives it away; add your own to CASES.
Model errors count as wrong answers here (no silent fallback), so the numbers are honest.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from app.config import Settings
from app.llm import HeuristicClient, SafeClient, build_client

# (filename, text snippet, expected category)
CASES = [
    ("invoice_oct.pdf", "", "Finance"),
    ("holiday.jpg", "", "Images"),
    ("setup.exe", "", "Installers"),
    ("backup.zip", "", "Archives"),
    ("main.py", "def main():\n    pass", "Code"),
    ("data.csv", "a,b,c\n1,2,3", "Data"),
    ("song.mp3", "", "Media"),
    ("payslip.txt", "Basic pay, HRA, deductions, net salary credited", "Finance"),
    ("scan0042.txt", "GST registration certificate. Quarterly returns filed. Ledger balance carried forward.", "Finance"),
    ("ledger_q3.txt", "Debit and credit entries for September: cash 4500, purchases 12000, closing balance", "Finance"),
    ("doc1.txt", "Dear hiring manager, I am excited to apply for the software engineer role at your company.", "Career"),
    ("cv_new.txt", "Skills: Python, React. Education: B.E. Computer Engineering. Projects and experience.", "Career"),
    ("offer.txt", "We are pleased to offer you the position of Web Developer Intern. Your stipend will be", "Career"),
    ("notes_final.txt", "Newton's laws of motion. Derivation of F=ma. Practice problems for the midterm.", "Study"),
    ("lab_manual.txt", "Experiment 5: titration of an acid against a base. Apparatus, procedure, observations.", "Study"),
    ("thing.md", "Operating systems: round robin and SJF scheduling. Previous year questions with answers.", "Study"),
    ("untitled.txt", "def two_sum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):", "Code"),
    ("export.txt", "date,amount,category\n2026-01-03,450,food\n2026-01-04,120,travel", "Data"),
    ("x.txt", "Boarding pass. Flight 6E 213 Pune to Delhi. Seat 14C. Gate closes 40 minutes before departure.", "Documents"),
    ("ideas.txt", "Pitch outline for a startup: market size, competitors, go-to-market plan.", "Documents"),
    ("random.bin", "", "Misc"),
]


def run(name: str, client) -> dict:
    inner = client.inner if isinstance(client, SafeClient) else client  # expose errors, no fallback
    right, errors, latencies, misses = 0, 0, [], []
    for fname, snippet, expected in CASES:
        p = Path(fname)
        meta = {"name": fname, "stem": p.stem, "ext": p.suffix.lower(), "size": len(snippet)}
        t0 = time.perf_counter()
        try:
            got = inner.classify(meta, snippet, [])["category"]
        except Exception as e:
            got, errors = f"ERROR({type(e).__name__})", errors + 1
        latencies.append((time.perf_counter() - t0) * 1000)
        if got == expected:
            right += 1
        else:
            misses.append((fname, expected, got))
    return {"name": name, "right": right, "total": len(CASES), "errors": errors,
            "ms": sum(latencies) / len(latencies), "misses": misses}


def make_client(name: str):
    if name == "rules":
        return HeuristicClient()
    s = Settings.from_env()
    s.llm_backend = name
    if name == "gemini":
        s.demo_mode = True  # synthetic benchmark data only
    return build_client(s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backends", default=f"rules,{os.getenv('LLM_BACKEND', 'openai')}")
    args = ap.parse_args()
    names = list(dict.fromkeys(b.strip() for b in args.backends.split(",") if b.strip()))
    results = []
    for n in names:
        try:
            results.append(run(n, make_client(n)))
        except Exception as e:
            print(f"Skipping {n}: {e}")

    lines = ["| Backend | Correct | Accuracy | Avg time per file | Errors |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['name']} | {r['right']}/{r['total']} | {r['right'] / r['total']:.0%} | {r['ms']:.0f} ms | {r['errors']} |")
    out = "\n".join(lines)
    print(out)
    for r in results:
        if r["misses"]:
            print(f"\nMissed by {r['name']}:")
            for f, exp, got in r["misses"]:
                print(f"  {f}: expected {exp}, got {got}")
    Path("benchmark_results.md").write_text(out + "\n")
    print("\nSaved benchmark_results.md")


if __name__ == "__main__":
    main()

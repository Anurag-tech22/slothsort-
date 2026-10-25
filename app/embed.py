"""Tiny deterministic, dependency-free text embedding (hashing trick).

Runs offline and never sends anything anywhere. Good enough to find "files like
this one" from names and snippets; swap for a real embedding model if you like.
"""
from __future__ import annotations

import hashlib
import math
import re

DIM = 256
_TOKEN = re.compile(r"[a-z0-9]{2,}")


def embed(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    tokens = _TOKEN.findall(text.lower())
    grams = tokens + [a + "_" + b for a, b in zip(tokens, tokens[1:])]
    for tok in grams:
        h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
        vec[h % dim] += 1.0 if (h >> 40) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))

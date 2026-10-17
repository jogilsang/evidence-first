"""Deterministic perturbations of an incident log, used to ask: does the verdict survive reasonable noise?

  typos     swap adjacent letters inside some longer words (seeded by case id)
  reorder   shuffle the order of sentences/lines
  noise     add unrelated healthy-looking log lines before and after the incident text
  korean    translate the log into Korean with a Bedrock model (cached), numbers and names kept

The label never changes: every perturbation is meant to leave the correct verdict untouched.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
TRANSLATOR_ID = "us.amazon.nova-pro-v1:0"

NOISE_LINES = [
    "10:02:11 health-check /ping 200 OK (3 ms)",
    "10:02:14 cert-renewal job finished, next run in 29 days",
    "10:02:20 gc pause 12 ms (young generation)",
    "10:02:31 metrics exporter flushed 214 series",
    "10:02:40 cron nightly-report skipped (no new data)",
    "10:02:55 config reload: no changes detected",
    "10:03:02 disk usage /var/log 41%",
    "10:03:09 ntp offset 0.4 ms",
]


def _rng(case_id: str, kind: str) -> random.Random:
    return random.Random(int(hashlib.sha1(f"{case_id}:{kind}".encode()).hexdigest()[:8], 16))


def typos(text: str, case_id: str, rate: float = 0.06) -> str:
    rng = _rng(case_id, "typos")
    out = []
    for tok in re.split(r"(\s+)", text):
        if len(tok) > 5 and tok.isalpha() and rng.random() < rate * 3:
            i = rng.randrange(1, len(tok) - 2)
            tok = tok[:i] + tok[i + 1] + tok[i] + tok[i + 2:]
        out.append(tok)
    return "".join(out)


def reorder(text: str, case_id: str) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n", text) if p.strip()]
    if len(parts) < 2:
        return text
    _rng(case_id, "reorder").shuffle(parts)
    return " ".join(parts)


def noise(text: str, case_id: str) -> str:
    rng = _rng(case_id, "noise")
    pick = rng.sample(NOISE_LINES, 5)
    return "\n".join(pick[:3] + [text] + pick[3:])


def korean(text: str, case_id: str, client=None, cache_path: Path | None = None) -> str:
    cache_path = cache_path or DATA / "korean_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    if case_id in cache:
        return cache[case_id]
    if client is None:
        import boto3
        from botocore.config import Config
        client = boto3.client("bedrock-runtime", region_name="us-east-1", config=Config(region_name="us-east-1"))
    out = client.converse(
        modelId=TRANSLATOR_ID,
        system=[{"text": "Translate the production incident log into natural Korean as an on-call engineer would write it. "
                         "Keep numbers, timestamps, units and service names exactly as they are. Output only the translation."}],
        messages=[{"role": "user", "content": [{"text": text}]}],
        inferenceConfig={"temperature": 0.0, "maxTokens": 600})
    ko = out["output"]["message"]["content"][0]["text"].strip()
    cache[case_id] = ko
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return ko


PERTURBATIONS = {"typos": typos, "reorder": reorder, "noise": noise, "korean": korean}

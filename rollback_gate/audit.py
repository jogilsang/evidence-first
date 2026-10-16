"""Audit trail and an idempotency cache for gate decisions.

Two small, opt-in building blocks the DeciderGate can be handed:

- `AuditLog` writes one JSON line per decision -- time, a hash of the input, the question
  scores, the verdict and reason, the policy version, and how it was reached (model /
  cache / temporal). Months later you can reconstruct *why* the gate said what it said.
  Nothing identifying is stored: the incident text is hashed, not kept.

- `DecisionCache` dedupes identical reviews within a time window. The same (log, action,
  args) seen again returns the prior verdict without a model call -- cheaper, and it stops
  an agent re-asking (and re-executing) the same thing in a tight loop.

Both are additive: a gate built without them behaves exactly as before.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, is_dataclass


def _fingerprint(log: str, action: str, args: dict | None) -> str:
    """Stable short hash of a review's inputs. Used as a cache key and an audit id, so the
    raw incident text never has to be stored to correlate decisions."""
    blob = json.dumps({"log": log, "action": action, "args": args or {}}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _policy_version(policy) -> str:
    """A short hash of the policy's thresholds, so a decision can be tied to the exact
    policy that produced it (and replayed against it later)."""
    data = asdict(policy) if is_dataclass(policy) else dict(policy or {})
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:8]


class AuditLog:
    """Append-only JSONL of decisions. Give it a path, or nothing to keep them in memory."""

    def __init__(self, path: str | None = None, now=time.time):
        self.path = path
        self._now = now
        self.records: list[dict] = []

    def record(self, log, action, args, verdict, policy=None, source="model") -> dict:
        entry = {
            "ts": round(self._now(), 3),
            "id": _fingerprint(log, action, args),
            "action": action,
            "decision": getattr(verdict, "decision", "allow" if getattr(verdict, "allow", True) else "block"),
            "reason": verdict.reason,
            "scores": verdict.scores,
            "policy_version": _policy_version(policy),
            "source": source,
        }
        self.records.append(entry)
        if self.path:
            with open(self.path, "a") as fh:
                fh.write(json.dumps(entry) + "\n")
        return entry


class DecisionCache:
    """In-memory idempotency cache keyed by the input fingerprint, with a TTL window."""

    def __init__(self, ttl_seconds: float = 120.0, now=time.time):
        self.ttl = ttl_seconds
        self._now = now
        self._store: dict[str, tuple[float, object]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, log, action, args):
        key = _fingerprint(log, action, args)
        hit = self._store.get(key)
        if hit and (self.ttl <= 0 or self._now() - hit[0] <= self.ttl):
            self.hits += 1
            return hit[1]
        self.misses += 1
        return None

    def put(self, log, action, args, verdict) -> None:
        self._store[_fingerprint(log, action, args)] = (self._now(), verdict)

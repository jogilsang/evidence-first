"""Audit log and idempotency cache. The gate is driven with a fake decider; no model."""
import json
from rollback_gate.audit import AuditLog, DecisionCache, _fingerprint
from rollback_gate.gate import DeciderGate, Verdict, Policy


def ans(cause="bad_deploy", p=0.8):
    rest = (1 - p) / 3
    probs = {k: rest for k in ("bad_deploy", "traffic_surge", "dependency_failure", "unknown")}
    probs[cause] = p
    return {"cause": {"probabilities": probs}, "already_tried": {"noul": 0.1},
            "dep_saturated": {"noul": 0.1}}


class CountingDecider:
    def __init__(self, answers):
        self.answers, self.calls = answers, 0
    def ask(self, state, questions):
        self.calls += 1
        return self.answers


class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t
    def tick(self, dt): self.t += dt


# --- fingerprint -----------------------------------------------------------

def test_same_inputs_same_fingerprint_different_inputs_differ():
    a = _fingerprint("log A", "rollback", {"to": "v1"})
    assert a == _fingerprint("log A", "rollback", {"to": "v1"})
    assert a != _fingerprint("log B", "rollback", {"to": "v1"})
    assert a != _fingerprint("log A", "scale_out", {"to": "v1"})


# --- audit log -------------------------------------------------------------

def test_audit_records_decision_without_storing_raw_log():
    audit = AuditLog()
    gate = DeciderGate(CountingDecider(ans("bad_deploy")), audit=audit)
    gate.review("sensitive incident text", "rollback", {"to": "v41"})
    assert len(audit.records) == 1
    e = audit.records[0]
    assert e["decision"] == "allow" and e["action"] == "rollback" and e["source"] == "model"
    # the raw log must not be stored anywhere in the entry
    assert "sensitive incident text" not in json.dumps(e)
    assert e["policy_version"]  # a policy fingerprint is attached


def test_audit_writes_jsonl_to_file(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path=str(path))
    gate = DeciderGate(CountingDecider(ans("traffic_surge")), audit=audit)  # blocked
    gate.review("x", "rollback")
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["decision"] == "block"


# --- idempotency cache -----------------------------------------------------

def test_cache_reuses_verdict_and_skips_the_model():
    clk = Clock()
    dec = CountingDecider(ans("bad_deploy"))
    gate = DeciderGate(dec, cache=DecisionCache(ttl_seconds=120, now=clk))
    v1 = gate.review("same log", "rollback", {"to": "v41"})
    v2 = gate.review("same log", "rollback", {"to": "v41"})
    assert v1 is v2 and dec.calls == 1  # second review served from cache, model called once


def test_cache_expires_after_ttl():
    clk = Clock()
    dec = CountingDecider(ans("bad_deploy"))
    gate = DeciderGate(dec, cache=DecisionCache(ttl_seconds=60, now=clk))
    gate.review("same log", "rollback")
    clk.tick(90)  # past ttl
    gate.review("same log", "rollback")
    assert dec.calls == 2  # cache entry expired, model consulted again


def test_cache_hit_is_still_audited_with_source_cache():
    clk = Clock()
    audit = AuditLog()
    gate = DeciderGate(CountingDecider(ans("bad_deploy")),
                       cache=DecisionCache(now=clk), audit=audit)
    gate.review("same log", "rollback")
    gate.review("same log", "rollback")
    sources = [e["source"] for e in audit.records]
    assert sources == ["model", "cache"]

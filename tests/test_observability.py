"""OTel span emission for decisions. Uses an in-memory span exporter so no backend is
needed; falls back gracefully when OpenTelemetry is absent."""
import pytest
from rollback_gate.observability import SpanAudit, MultiSink, otel_available
from rollback_gate.audit import AuditLog
from rollback_gate.gate import DeciderGate, Verdict


def ans(cause="bad_deploy", p=0.8):
    rest = (1 - p) / 3
    probs = {k: rest for k in ("bad_deploy", "traffic_surge", "dependency_failure", "unknown")}
    probs[cause] = p
    return {"cause": {"probabilities": probs}, "already_tried": {"noul": 0.1},
            "dep_saturated": {"noul": 0.1}}


class FakeDecider:
    def __init__(self, answers): self.answers = answers
    def ask(self, state, questions): return self.answers


def _in_memory_tracer():
    """A tracer wired to an in-memory exporter; returns (tracer, finished_spans_getter)."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter.get_finished_spans


@pytest.mark.skipif(not otel_available(), reason="OpenTelemetry not installed")
def test_decision_emits_a_span_with_attributes():
    tracer, spans = _in_memory_tracer()
    gate = DeciderGate(FakeDecider(ans("bad_deploy")), audit=SpanAudit(tracer))
    gate.review("deploy then 5xx", "rollback", {"to": "v41"})
    finished = spans()
    assert len(finished) == 1
    s = finished[0]
    assert s.name == "decider.gate.review"
    assert s.attributes["decider.action"] == "rollback"
    assert s.attributes["decider.decision"] == "allow"
    assert s.attributes["decider.cause_top"] == "bad_deploy"


@pytest.mark.skipif(not otel_available(), reason="OpenTelemetry not installed")
def test_multisink_emits_span_and_keeps_jsonl():
    tracer, spans = _in_memory_tracer()
    log = AuditLog()
    gate = DeciderGate(FakeDecider(ans("traffic_surge")),  # blocked for rollback
                       audit=MultiSink([log, SpanAudit(tracer)]))
    gate.review("x", "rollback")
    assert len(spans()) == 1               # OTel got it
    assert len(log.records) == 1           # and the JSONL audit kept it
    assert log.records[0]["decision"] == "block"


def test_span_audit_is_noop_without_a_tracer():
    # no tracer -> record() must not raise and must not emit
    sa = SpanAudit(tracer=None)
    sa.record(log="x", action="rollback", args=None, verdict=Verdict(True, "ok"))
    assert sa.spans == 0

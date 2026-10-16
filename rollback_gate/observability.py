"""OpenTelemetry span emission for gate decisions (CNCF-standard observability).

Each decision becomes one OTel span -- `decider.gate.review` -- carrying the action, the
verdict, the reason, the key scores, and how it was reached. Point an OTLP exporter at
CloudWatch (or any OTel backend) and every decision the gate makes is a span you can query
and correlate with the rest of a trace. OpenTelemetry is a CNCF project and the wire format
CloudWatch's agent observability speaks natively, so this is the standard seam, not a
bespoke one.

`SpanAudit` deliberately mirrors `AuditLog`'s `record(...)` signature, so it drops into the
DeciderGate's `audit` slot. Use `MultiSink([...])` to emit spans *and* keep the JSONL log.
Opt-in and safe: if OpenTelemetry isn't installed, importing still works and `SpanAudit`
becomes a no-op rather than raising.
"""
from __future__ import annotations

try:
    from opentelemetry import trace
    _OTEL = True
except ImportError:  # otel optional: no-op if absent
    trace = None
    _OTEL = False


def otel_available() -> bool:
    return _OTEL


class SpanAudit:
    """Emits one OTel span per decision. Same interface as AuditLog so it fits the gate's
    `audit` slot. With no OTel installed (or tracer), it quietly does nothing."""

    _DEFAULT = object()  # sentinel: distinguish "give me the default tracer" from "disabled"

    def __init__(self, tracer=_DEFAULT):
        if tracer is None:
            self.tracer = None                       # explicitly disabled -> no-op
        elif tracer is SpanAudit._DEFAULT:
            self.tracer = trace.get_tracer("decider-gate") if _OTEL else None
        else:
            self.tracer = tracer
        self.spans = 0

    def record(self, log, action, args, verdict, policy=None, source="model") -> None:
        if self.tracer is None:
            return
        decision = getattr(verdict, "decision",
                           "allow" if getattr(verdict, "allow", True) else "block")
        with self.tracer.start_as_current_span("decider.gate.review") as span:
            span.set_attribute("decider.action", action)
            span.set_attribute("decider.decision", decision)
            span.set_attribute("decider.reason", verdict.reason)
            span.set_attribute("decider.source", source)
            probs = (verdict.scores or {}).get("cause_probs") or {}
            if probs:
                top = max(probs, key=probs.get)
                span.set_attribute("decider.cause_top", top)
                span.set_attribute("decider.cause_prob", float(probs[top]))
            for k in ("already_tried", "dep_saturated", "blast_radius"):
                if k in (verdict.scores or {}):
                    span.set_attribute(f"decider.{k}", float(verdict.scores[k]))
        self.spans += 1


class MultiSink:
    """Fan a decision out to several audit sinks (e.g. JSONL + OTel spans)."""

    def __init__(self, sinks):
        self.sinks = list(sinks)

    def record(self, **kwargs) -> None:
        for s in self.sinks:
            s.record(**kwargs)

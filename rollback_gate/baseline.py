"""Baseline judge: a general Bedrock LLM decides allow/block directly, in one free call.

This is the "LLM decides" approach the DeciderGate pattern is contrasted against. The
model is handed the same incident log and proposed action and asked to return a verdict as
JSON. There is no separate policy layer -- the thresholds, the reasoning and the final
allow/block all live inside one opaque model call.

It exists so the gate can be measured against a credible alternative on the same golden
set: accuracy, latency and dollar cost, side by side. Nothing here is used by the gate at
runtime; it is a measurement baseline only.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

# Cross-region inference profile (on-demand Haiku 4.5 requires a profile ID, not the bare
# model ID). Region and profile are overridable so a reader can point at their own.
DEFAULT_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_REGION = "us-east-1"

# Published Haiku 4.5 on-demand pricing, USD per 1M tokens (us-east-1, 2026-10).
# Overridable; verify before quoting in anything public.
PRICE_IN_PER_M = 1.00
PRICE_OUT_PER_M = 5.00

SYSTEM = (
    "You are an SRE change-approval reviewer. You are given an incident log and a proposed "
    "remediation action. Decide whether the action is justified by the evidence in the log. "
    "Allow the action only if the log's root cause is the one that action fixes: 'rollback' "
    "fixes a bad deploy or config change; 'scale_out' fixes a traffic surge that saturates "
    "resources. Block it if the cause is something else (a failing dependency, an unknown "
    "cause), or if that same fix was already applied in this incident and the problem "
    "persists. Reply with ONLY a JSON object: "
    '{"allow": true|false, "reason": "<one short sentence>"}.'
)


@dataclass
class BaselineVerdict:
    allow: bool
    reason: str
    raw: str = ""
    scores: dict = field(default_factory=dict)


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of the model's reply, tolerating prose/fences."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON object in model reply: {text!r}")
    return json.loads(m.group(0))


class BaselineJudge:
    """One Bedrock Converse call per decision. Tracks tokens, cost and latency."""

    def __init__(self, model_id: str = DEFAULT_MODEL_ID, region: str = DEFAULT_REGION,
                 client: Any | None = None, max_tokens: int = 200):
        if client is None:
            import boto3  # imported lazily so unit tests can inject a fake client
            from botocore.config import Config
            # region pinned on both the client and the Config: with awscrt installed,
            # endpoint resolution otherwise wants AWS_DEFAULT_REGION in the environment.
            client = boto3.client("bedrock-runtime", region_name=region,
                                  config=Config(region_name=region))
        self.client = client
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.last_latency_ms: float | None = None

    def cost_usd(self) -> float:
        return (self.input_tokens / 1e6) * PRICE_IN_PER_M + (self.output_tokens / 1e6) * PRICE_OUT_PER_M

    def review(self, log: str, action: str, args: dict | None = None) -> BaselineVerdict:
        prompt = f"--- INCIDENT LOG ---\n{log}\n\n--- PROPOSED ACTION ---\n{action} {args or ''}".rstrip()
        t0 = time.perf_counter()
        resp = self.client.converse(
            modelId=self.model_id,
            system=[{"text": SYSTEM}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": self.max_tokens, "temperature": 0.0},
        )
        self.last_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        self.calls += 1
        usage = resp.get("usage", {})
        self.input_tokens += usage.get("inputTokens", 0)
        self.output_tokens += usage.get("outputTokens", 0)
        text = resp["output"]["message"]["content"][0]["text"]
        obj = _extract_json(text)
        return BaselineVerdict(
            allow=bool(obj["allow"]),
            reason=str(obj.get("reason", "")).strip(),
            raw=text,
            scores={"input_tokens": usage.get("inputTokens", 0),
                    "output_tokens": usage.get("outputTokens", 0)},
        )

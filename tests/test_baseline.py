"""BaselineJudge is the Bedrock comparison baseline. Bedrock is mocked: these test the
JSON parsing, token/cost accounting and error handling, not the live model."""
import pytest
from rollback_gate.baseline import BaselineJudge, _extract_json, PRICE_IN_PER_M, PRICE_OUT_PER_M


class FakeBedrock:
    """Stands in for a boto3 bedrock-runtime client's .converse()."""
    def __init__(self, text, in_tok=100, out_tok=20):
        self.text, self.in_tok, self.out_tok = text, in_tok, out_tok
        self.seen = None

    def converse(self, **kwargs):
        self.seen = kwargs
        return {
            "output": {"message": {"content": [{"text": self.text}]}},
            "usage": {"inputTokens": self.in_tok, "outputTokens": self.out_tok},
        }


# --- happy path -----------------------------------------------------------

def test_allow_verdict_parsed_from_clean_json():
    j = BaselineJudge(client=FakeBedrock('{"allow": true, "reason": "deploy caused it"}'))
    v = j.review("deploy then 5xx", "rollback")
    assert v.allow and "deploy" in v.reason


def test_block_verdict_parsed_and_log_action_sent_to_model():
    fake = FakeBedrock('{"allow": false, "reason": "traffic surge, not a deploy"}')
    j = BaselineJudge(client=fake)
    v = j.review("cpu 92% traffic 4x", "rollback", {"to": "v41"})
    assert v.allow is False and "traffic" in v.reason
    sent = fake.seen["messages"][0]["content"][0]["text"]
    assert "cpu 92%" in sent and "rollback" in sent  # both log and action reach the model


# --- edge cases -----------------------------------------------------------

def test_json_extracted_even_with_surrounding_prose_and_fences():
    msg = 'Sure, here is my verdict:\n```json\n{"allow": false, "reason": "dependency failure"}\n```\nHope that helps.'
    assert _extract_json(msg) == {"allow": False, "reason": "dependency failure"}


def test_cost_accumulates_across_calls_using_published_rates():
    j = BaselineJudge(client=FakeBedrock('{"allow": true, "reason": "ok"}', in_tok=1000, out_tok=200))
    j.review("x", "rollback")
    j.review("y", "scale_out")
    assert j.input_tokens == 2000 and j.output_tokens == 400
    expected = (2000 / 1e6) * PRICE_IN_PER_M + (400 / 1e6) * PRICE_OUT_PER_M
    assert j.cost_usd() == pytest.approx(expected)


# --- error handling -------------------------------------------------------

def test_reply_without_json_raises_valueerror():
    j = BaselineJudge(client=FakeBedrock("I cannot decide this."))
    with pytest.raises(ValueError):
        j.review("x", "rollback")

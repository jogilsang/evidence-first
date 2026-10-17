import json

import pytest

from evalkit import generate, perturb, score
from evalkit.families import Family


class FakeBedrock:
    """Generator returns fixed logs; verifier answers from a per-log table."""

    def __init__(self, verifier_says, fail_on=None):
        self.verifier_says, self.fail_on = verifier_says, fail_on or set()

    def converse(self, modelId, system, messages, inferenceConfig):
        text = messages[0]["content"][0]["text"]
        if modelId == generate.GENERATOR_ID:
            body = json.dumps([f"incident number {i} with enough words to pass the length filter ok" for i in range(4)])
        else:
            log = text.split("\n")[1]
            if log in self.fail_on:
                raise RuntimeError("throttled")
            body = json.dumps({"allow": self.verifier_says.get(log, True), "reason": "r"})
        return {"output": {"message": {"content": [{"text": body}]}}}


FAM = [Family("t-fam", "rollback", True, "a deploy happened")]


def test_build_keeps_cases_when_verifier_agrees():
    cases, removed = generate.build(FakeBedrock({}), families=FAM)
    assert len(cases) == 8 and not removed
    assert cases[0]["allow"] is True and cases[0]["generator"] == generate.GENERATOR_ID and "label_rationale" in cases[0]


def test_build_quarantines_disagreements_instead_of_dropping_them():
    log = "incident number 0 with enough words to pass the length filter ok"
    cases, removed = generate.build(FakeBedrock({log: False}), families=FAM)
    assert len(removed) == 2 and all(r["removed_reason"] == "generator label and verifier disagree" for r in removed)
    assert len(cases) == 6 and len(cases) + len(removed) == 8


def test_build_quarantines_cases_the_verifier_could_not_check():
    log = "incident number 1 with enough words to pass the length filter ok"
    _, removed = generate.build(FakeBedrock({}, fail_on={log}), families=FAM)
    assert removed and removed[0]["removed_reason"].startswith("verifier failed")


def test_parse_json_rejects_garbage():
    with pytest.raises(ValueError):
        generate.parse_json("no json here")


@pytest.mark.parametrize("fn", [perturb.typos, perturb.reorder, perturb.noise])
def test_perturbations_are_deterministic_and_keep_the_facts(fn):
    text = "At 14:02 deploy v42 finished. Errors began at 14:04 on checkout-svc. Traffic is normal."
    assert fn(text, "case-1") == fn(text, "case-1")
    out = fn(text, "case-1")
    assert "14:02" in out and "v42" in out and "checkout-svc" in out


def test_noise_adds_unrelated_lines_around_the_text():
    out = perturb.noise("the incident", "c")
    assert "the incident" in out and out.count("\n") >= 4


def test_korean_uses_cache_and_skips_the_model(tmp_path):
    cache = tmp_path / "ko.json"
    cache.write_text(json.dumps({"c9": "캐시된 번역"}, ensure_ascii=False), encoding="utf-8")
    assert perturb.korean("anything", "c9", client=object(), cache_path=cache) == "캐시된 번역"


def test_score_counts_false_allows_and_escalate_as_not_allowed():
    class V:
        def __init__(self, allow): self.allow, self.reason = allow, "r"
    cases = [{"id": "a", "family": "f", "action": "rollback", "allow": False, "log": "x"},
             {"id": "b", "family": "f", "action": "rollback", "allow": True, "log": "y"},
             {"id": "c", "family": "f", "action": "rollback", "allow": True, "log": "z"}]
    verdicts = {"x": True, "y": True, "z": False}
    out = score.score_cases(cases, lambda log, action: V(verdicts[log]))
    assert out["false_allow"] == ["a"] and out["false_block"] == ["c"] and out["accuracy"] == round(1 / 3, 3)
    assert out["per_family"] == {"f": "1/3"}

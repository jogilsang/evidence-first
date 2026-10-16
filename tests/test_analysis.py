"""The analysis scripts (confusion / counterfactual / cost) over mocked bench rows, so the
reporting math is tested without a model or AWS. sweep is excluded (needs the live model)."""
import analysis


ROWS = [
    # id, expected(allow), got(allow), ok
    {"id": "rb-ok-1", "expected": True, "got": True, "ok": True, "reason": "ok"},
    {"id": "rb-no-1", "expected": False, "got": False, "ok": True, "reason": "blocked"},
    {"id": "rb-no-2", "expected": False, "got": True, "ok": False, "reason": "slipped"},  # false allow
    {"id": "so-no-1", "expected": False, "got": False, "ok": True, "reason": "blocked"},
    {"id": "so-ok-1", "expected": True, "got": False, "ok": False, "reason": "over-cautious"},  # false block
]


def test_confusion_counts_and_misses(monkeypatch, capsys):
    monkeypatch.setattr(analysis, "_rows", lambda bench_key="gate": ROWS)
    analysis.confusion()
    out = capsys.readouterr().out
    assert "n=5" in out
    assert "false-allow 1" in out and "false-block 1" in out
    # both misses listed
    assert "rb-no-2" in out and "so-ok-1" in out


def test_counterfactual_counts_correct_blocks(monkeypatch, capsys):
    monkeypatch.setattr(analysis, "_rows", lambda bench_key="gate": ROWS)
    analysis.counterfactual()
    out = capsys.readouterr().out
    # correctly blocked = rb-no-1, so-no-1 (got False and should block); rb-no-2 was allowed
    assert "2 of 5" in out
    assert "rollback" in out and "scale-out" in out


def test_cost_uses_baseline_per_case_when_present(monkeypatch, capsys):
    monkeypatch.setattr(analysis, "_load",
                        lambda p: {"baseline": {"api_cost_usd": 0.010, "n": 20}}
                        if p == "bench_compare.json" else None)
    analysis.cost()
    out = capsys.readouterr().out
    assert "1,000,000" in out and "$0" in out  # extrapolation table printed, Decider column $0


def test_cost_falls_back_to_published_rates_without_bench(monkeypatch, capsys):
    monkeypatch.setattr(analysis, "_load", lambda p: None)  # no bench files
    analysis.cost()
    out = capsys.readouterr().out
    assert "per decision" in out  # still prints using fallback Haiku rates


def test_confusion_handles_no_bench_rows(monkeypatch, capsys):
    monkeypatch.setattr(analysis, "_rows", lambda bench_key="gate": [])
    analysis.confusion()
    assert "no bench rows" in capsys.readouterr().out

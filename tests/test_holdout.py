"""The held-out set must be a genuine validation set, not a paraphrase of the golden set:
distinct ids, both labels per action, and no case id overlap with golden."""
from rollback_gate.golden import cases as golden_cases
from rollback_gate.holdout import cases as holdout_cases


def test_holdout_ids_are_unique():
    cs = holdout_cases()
    assert len({c["id"] for c in cs}) == len(cs)


def test_holdout_has_both_labels_per_action():
    cs = holdout_cases()
    for action in ("rollback", "scale_out"):
        labels = {c["allow"] for c in cs if c["action"] == action}
        assert labels == {True, False}, f"{action} missing a label in holdout"


def test_holdout_does_not_reuse_golden_ids_or_logs():
    g = golden_cases()
    h = holdout_cases()
    gids, hids = {c["id"] for c in g}, {c["id"] for c in h}
    assert gids.isdisjoint(hids)  # no shared ids
    glogs = {c["log"] for c in g}
    assert all(c["log"] not in glogs for c in h)  # not literal copies of golden logs

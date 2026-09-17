"""
Structural tests for the golden set itself.

These run in milliseconds with no API key and no Phoenix, which is the point:
a malformed golden set should fail in the fast lane, not halfway through a
paid experiment. In CI, run this file before test_quality_gate.py.
"""

from collections import Counter

import pytest

from pydata_evals.evals import parse_arrive_before, parse_max_transfers
from pydata_evals.golden_set import (
    BUCKETS,
    CONSTRAINTS,
    GOLDEN_EXAMPLES,
    PERSONAS,
    THRESHOLDS,
    by_bucket,
    by_constraint,
    by_persona,
    needs_a_judge,
)


def test_set_is_big_enough_to_mean_something():
    assert len(GOLDEN_EXAMPLES) >= 100


def test_ids_are_unique():
    duplicates = [i for i, n in Counter(e["id"] for e in GOLDEN_EXAMPLES).items() if n > 1]
    assert not duplicates, f"duplicate example ids: {duplicates}"


def test_inputs_are_unique():
    """Duplicated inputs silently double-weight one behaviour in the score."""
    duplicates = [
        text for text, n in Counter(e["input"].strip().lower() for e in GOLDEN_EXAMPLES).items()
        if n > 1
    ]
    assert not duplicates, f"duplicate inputs: {duplicates}"


@pytest.mark.parametrize("example", GOLDEN_EXAMPLES, ids=lambda e: e["id"])
def test_example_is_well_formed(example):
    assert example["bucket"] in BUCKETS
    assert example["persona"] in PERSONAS
    assert example["constraint"] in CONSTRAINTS
    assert example["input"].strip(), "empty input"
    assert example["expected"].strip(), "an example with no expected behaviour cannot be graded"


@pytest.mark.parametrize("bucket", BUCKETS)
def test_every_bucket_is_populated_and_has_a_floor(bucket):
    """A bucket with no examples passes its threshold vacuously - that is the
    green-CI failure this whole suite exists to prevent."""
    assert by_bucket(bucket), f"bucket {bucket} is empty"
    assert bucket in THRESHOLDS, f"bucket {bucket} has no threshold"


@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_every_persona_has_enough_examples_to_read(persona):
    assert len(by_persona(persona)) >= 3, "fewer than 3 examples is not a signal"


def test_adversarial_bucket_is_not_a_token_gesture():
    """It is gated at 100%, so it needs enough rows that 100% is a real claim."""
    assert len(by_bucket("adversarial")) >= 10


def test_failure_replays_all_name_their_failure_mode():
    """A replay whose failure mode is unrecorded cannot tell you what regressed."""
    unlabelled = [e["id"] for e in by_bucket("failure_replay") if not e["failure_mode"]]
    assert not unlabelled, f"failure_replay examples missing failure_mode: {unlabelled}"


# --------------------------------------------------------------------------
# The constraint axis. These are the tests that stop `constraint_adherence`
# from quietly grading an empty room.
# --------------------------------------------------------------------------
def test_most_rows_actually_constrain_something():
    """
    A set of bare route lookups scores ~100% on the constraint judge and
    proves nothing, because every row comes back "no_constraint". If this
    ratio slips, the judge's rate stops being a measurement.
    """
    constrained = len(GOLDEN_EXAMPLES) - len(by_constraint("none"))
    assert constrained / len(GOLDEN_EXAMPLES) >= 0.6, (
        f"only {constrained}/{len(GOLDEN_EXAMPLES)} rows carry a constraint"
    )


def test_the_semantic_half_is_the_big_half():
    """
    The reason we pay for an LLM judge at all. If most constraints were
    parseable, `parse_max_transfers` and friends would be the whole story and
    the judge would be an expensive way to agree with a regex.
    """
    assert len(needs_a_judge()) >= 2 * len(by_constraint("hard"))


@pytest.mark.parametrize("kind", CONSTRAINTS)
def test_every_constraint_kind_is_populated(kind):
    assert by_constraint(kind), f"no {kind}-constraint examples"


@pytest.mark.parametrize("example", GOLDEN_EXAMPLES, ids=lambda e: e["id"])
def test_constraint_label_matches_what_the_parser_can_see(example):
    """
    The label is a claim about which side of the deterministic line a row
    falls on, and a wrong claim is worse than no label: it sends you looking
    for a regex bug when the constraint was always semantic, or the reverse.

    Keeping this green is also what catches a parser that quietly starts
    over-matching -- "le plus direct possible" is a preference, not a limit
    of zero, and the day the parser resolves it to 0 this test goes red.
    """
    parseable = (
        parse_max_transfers(example["input"]) is not None
        or parse_arrive_before(example["input"]) is not None
    )
    expected = example["constraint"] in ("hard", "both")
    assert parseable == expected, (
        f"labelled {example['constraint']!r} but the parser "
        f"{'does' if parseable else 'does not'} resolve it: {example['input']!r}"
    )

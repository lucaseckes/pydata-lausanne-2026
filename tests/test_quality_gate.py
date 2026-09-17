"""
Step 3: the gate.

This is the payload of the talk. Everything before it is preparation; this is
the part that changes what ships. Run it with plain pytest, in CI, on every PR.

    pytest tests/test_quality_gate.py

Design notes worth saying out loud on stage:

  * The threshold is per-bucket, not global. A 90% aggregate that hides a 0%
    on the adversarial bucket is exactly the green-CI-burning-production
    failure this whole talk is about.
  * The gate asserts on a REGRESSION, not on perfection. Blocking merges until
    a score is 100% just teaches the team to delete the eval.
  * Failure output names the bucket and the failure mode, because "quality
    dropped" is not an actionable CI message.
"""

import os
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest
from phoenix.client import Client

from pydata_evals.app import answer_question
from pydata_evals.evals import GATED_EVALUATORS, build_evaluators
from pydata_evals.golden_set import THRESHOLDS

DATASET = os.environ.get("EVAL_DATASET", "sbb-journey-golden")


def run_my_app(example):
    """The experiment task: run the current build against one golden input."""
    return answer_question(example.input["input"])


@dataclass(frozen=True)
class ScoredRun:
    """One (task run x evaluator) score, carrying its example's metadata."""

    metadata: Mapping[str, Any]
    evaluator: str
    score: float
    # Carried alongside the score because constraint_adherence puts two
    # different behaviours ("honoured", "flagged") on the same 1.0. The rate
    # alone cannot tell them apart; the label distribution can.
    label: str | None = None


@dataclass(frozen=True)
class ExperimentResults:
    """
    The joined view of the experiment that every assertion below reads.

    `client.experiments.run_experiment` returns a `RanExperiment`, which is a
    TypedDict -- a plain dict, not an object -- holding two flat, independent
    lists and no examples at all:

        {"task_runs": [...], "evaluation_runs": [...], "experiment_id": ...}

    So grouping scores by bucket takes two joins (see `_collect`): an
    evaluation names the task run it graded, and a task run names the dataset
    example it ran on. The metadata we threshold on lives on the example.
    """

    runs: list[ScoredRun]
    errors: list[str]


def _collect(ran_experiment, dataset) -> ExperimentResults:
    metadata_by_example = {
        # Runs record the example's node GlobalID; older servers put that in `id`.
        (example.get("node_id") or example["id"]): example.get("metadata") or {}
        for example in dataset.examples
    }

    errors: list[str] = []
    metadata_by_run_id = {}
    for task_run in ran_experiment["task_runs"]:
        metadata_by_run_id[task_run["id"]] = metadata_by_example.get(
            task_run["dataset_example_id"], {}
        )
        if error := task_run.get("error"):
            errors.append(f"task: {error}")

    runs: list[ScoredRun] = []
    for evaluation in ran_experiment["evaluation_runs"]:
        # An evaluator that blew up is not a score of 0, and silently treating
        # it as one is how a broken judge turns into a fake regression.
        if evaluation.error:
            errors.append(f"{evaluation.name}: {evaluation.error}")
            continue
        # `result` is one evaluation or a sequence of them.
        result = evaluation.result
        results = [result] if isinstance(result, Mapping) else list(result or ())
        for one in results:
            if (score := one.get("score")) is None:
                continue  # label-only evaluation, nothing to average
            runs.append(
                ScoredRun(
                    metadata=metadata_by_run_id.get(evaluation.experiment_run_id, {}),
                    evaluator=evaluation.name,
                    score=float(score),
                    label=one.get("label"),
                )
            )

    return ExperimentResults(runs=runs, errors=errors)


@pytest.fixture(scope="session")
def experiment() -> ExperimentResults:
    client = Client()
    dataset = client.datasets.get_dataset(dataset=DATASET)

    judge_llm = _build_judge()  # your provider wrapper
    ran = client.experiments.run_experiment(
        dataset=dataset,
        task=run_my_app,
        evaluators=build_evaluators(judge_llm),
        experiment_name=os.environ.get("EXPERIMENT_NAME", "local"),
    )
    return _collect(ran, dataset)


def test_the_experiment_actually_scored_something(experiment):
    """
    Runs first, because every threshold below passes vacuously on zero scores.
    A judge that errored on all 107 examples is a red build, not a green one.
    """
    assert experiment.runs, "no scores came back -> " + "; ".join(
        sorted(set(experiment.errors))[:5] or ["no errors reported either"]
    )
    if experiment.errors:
        print(f"  {len(experiment.errors)} run(s) errored:")
        for error in sorted(set(experiment.errors))[:5]:
            print(f"    {error}")


def test_no_bucket_regresses(experiment):
    by_bucket = defaultdict(list)

    for run in experiment.runs:
        # The deterministic check runs and is recorded, but it does not vote
        # here: `within_length_budget` is a style budget, and a long-but-correct
        # answer must not fail the 100% adversarial floor. See
        # GATED_EVALUATORS in evals.py.
        if run.evaluator not in GATED_EVALUATORS:
            continue
        by_bucket[run.metadata.get("bucket") or "production"].append(run.score)

    failures = []
    for bucket, scores in sorted(by_bucket.items()):
        if not scores:
            continue
        rate = sum(scores) / len(scores)
        floor = THRESHOLDS.get(bucket, 0.85)
        status = "PASS" if rate >= floor else "FAIL"
        print(f"  {status}  {bucket:<16} {rate:>6.0%}  (floor {floor:.0%}, n={len(scores)})")
        if rate < floor:
            failures.append(f"{bucket}: {rate:.0%} < {floor:.0%}")

    assert not failures, "quality gate failed -> " + "; ".join(failures)


# The persona axis is a diagnostic, not a gate. Thresholding 14 personas at
# n=5..8 each would fail the build on noise, and a flaky gate gets deleted.
# So this reports every persona and only fails on a total wipe-out, which is
# never noise - it means the whole persona is broken.
MIN_N_FOR_PERSONA_GATE = 5


def test_no_persona_is_completely_broken(experiment):
    by_persona = defaultdict(list)

    for run in experiment.runs:
        if run.evaluator not in GATED_EVALUATORS:
            continue
        by_persona[run.metadata.get("persona") or "unknown"].append(run.score)

    failures = []
    for persona, scores in sorted(by_persona.items(), key=lambda kv: _rate(kv[1])):
        rate = _rate(scores)
        print(f"  {persona:<18} {rate:>6.0%}  (n={len(scores)})")
        if rate == 0.0 and len(scores) >= MIN_N_FOR_PERSONA_GATE:
            failures.append(f"{persona}: 0% over n={len(scores)}")

    assert not failures, "persona wiped out -> " + "; ".join(failures)


def test_report_failure_modes(experiment):
    """
    Not a gate. This is the triage view you actually read when CI is red.

    Gated evaluators only, deliberately: this table is where you go to
    explain a red bucket, and a rate computed over a different set of
    evaluators than the bucket floor cannot explain anything.
    """
    by_mode = defaultdict(list)

    for run in experiment.runs:
        if run.evaluator not in GATED_EVALUATORS:
            continue
        by_mode[run.metadata.get("failure_mode") or "-"].append(run.score)

    for mode, scores in sorted(by_mode.items(), key=lambda kv: _rate(kv[1])):
        print(f"  {mode:<30} {_rate(scores):>6.0%}  (n={len(scores)})")


CONSTRAINT_EVALUATOR = "constraint_adherence"


def test_report_constraint_adherence_by_kind(experiment):
    """
    Not a gate. The single most useful view once the constraint judge is on:
    a healthy `hard` column with a sick `soft` one means the app honours what
    it can pattern-match and drops what it has to read for. That is the
    failure the whole second evaluator exists to surface, and it is invisible
    in the aggregate.
    """
    by_kind = defaultdict(list)

    for run in experiment.runs:
        if run.evaluator == CONSTRAINT_EVALUATOR:
            by_kind[run.metadata.get("constraint") or "none"].append(run.score)

    if not by_kind:
        pytest.skip(f"{CONSTRAINT_EVALUATOR} produced no scores")

    for kind in ("none", "hard", "soft", "both"):
        if scores := by_kind.get(kind):
            print(f"  {kind:<8} {_rate(scores):>6.0%}  (n={len(scores)})")


def test_report_deterministic_checks(experiment):
    """
    Not a gate. The free check, sliced by bucket - because sliced is the only
    way it reads correctly.

    `within_length_budget` at 80% overall means nothing. At 80% on production
    it means the app is chatty where users want a timetable; the same 80% on
    adversarial means the refusals have grown into essays, which is a prompt
    problem, not a length problem. Read the rows, not the total.
    """
    by_check = defaultdict(lambda: defaultdict(list))

    for run in experiment.runs:
        if run.evaluator in GATED_EVALUATORS:
            continue
        bucket = run.metadata.get("bucket") or "production"
        by_check[run.evaluator][bucket].append(run.score)

    if not by_check:
        pytest.skip("no deterministic scores came back")

    for check, by_bucket in sorted(by_check.items()):
        scored = [s for scores in by_bucket.values() for s in scores]
        print(f"  {check:<30} {_rate(scored):>6.0%}  (n={len(scored)})")
        for bucket, scores in sorted(by_bucket.items()):
            print(f"      {bucket:<20} {_rate(scores):>6.0%}  (n={len(scores)})")


def test_report_label_distribution(experiment):
    """
    Not a gate either. Reads the labels behind the rates.

    This is where you find out that constraint_adherence is 96% because the
    golden set barely constrains anything, or that a clean-looking score is
    mostly "flagged" - the app is honest, but it is telling users no all day,
    which is a retrieval problem wearing a quality score.
    """
    by_evaluator = defaultdict(Counter)

    for run in experiment.runs:
        by_evaluator[run.evaluator][run.label or "-"] += 1

    for evaluator, labels in sorted(by_evaluator.items()):
        total = sum(labels.values())
        breakdown = "  ".join(
            f"{label}={n / total:.0%}" for label, n in labels.most_common()
        )
        print(f"  {evaluator:<24} {breakdown}  (n={total})")


def _rate(scores) -> float:
    return sum(scores) / len(scores) if scores else 0.0


def _build_judge():
    """
    Swap in whichever provider you use. Keep the judge model PINNED — an
    unpinned judge means your baseline moves under you and you will spend a
    day debugging a regression that was a silent model upgrade.
    """
    from phoenix.evals.llm import LLM

    return LLM(provider="anthropic", model="claude-haiku-4-5")

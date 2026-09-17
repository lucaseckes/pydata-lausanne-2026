# pydata-evals

A worked example, built for a Visium 2026 PyData Lausanne talk, of putting an LLM app behind a
quality gate that runs in CI.

The app is a Swiss train journey planner: Claude with one tool that queries the
public SBB timetable ([transport.opendata.ch](http://transport.opendata.ch)).
It is deliberately weak — its system prompt literally says *"invent if you don't
find the response"* — so the evals have something real to catch.

Everything is traced to [Arize Phoenix](https://github.com/Arize-ai/phoenix), graded
by two LLM judges plus one deterministic check, and asserted with plain `pytest`.

## The three steps

| Step | File | What it does |
| --- | --- | --- |
| 1. Instrument | `src/pydata_evals/app.py` | The app, traced from the first line. You cannot build a golden set from failures you never recorded. |
| 2. Judge + fixture | `src/pydata_evals/evals.py` + `rubrics/` | Three rubrics written from observed failures — one `.md` file each — one deterministic check for what doesn't need a model, and the dataset seeder. |
| 3. Gate | `tests/test_quality_gate.py` | Runs the experiment and asserts per-bucket floors. Red build names the bucket and the failure mode. |

`src/pydata_evals/golden_set.py` is step 2 grown up: the four slide-sized examples
in `evals.py` become 103 examples organised along three axes.

## Setup

```bash
uv sync
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

If your API key is identity-linked, also set `ANTHROPIC_WORKSPACE_ID` — otherwise
every request 400s.

Start Phoenix in another terminal:

```bash
uv run phoenix serve          # or: docker run -p 6006:6006 arizephoenix/phoenix
```

It listens on `http://localhost:6006`. Override with `PHOENIX_COLLECTOR_ENDPOINT`.

## Run it

```bash
# 1. run the app, then look at the traces
uv run pydata-evals
open http://localhost:6006

# 2. seed the dataset into Phoenix
uv run python -m pydata_evals.evals              # full golden set -> sbb-journey-golden
uv run python -m pydata_evals.evals --demo       # the four slide examples -> sbb-journey-demo

# 3. the gate
uv run pytest tests/test_golden_set.py           # fast, no API key, no Phoenix
uv run pytest tests/test_quality_gate.py -s      # runs the experiment; -s to see the report
```

Run the structural tests first in CI: a malformed golden set should fail in the
fast lane, not halfway through a paid experiment.

Useful env vars for the gate: `EVAL_DATASET` (default `sbb-journey-golden`) and
`EXPERIMENT_NAME` (default `local`).

### Updating an already-seeded dataset

Re-seeding under an existing name *appends* — you get one version with 206 rows,
not 103 revised ones. Use `--sync`, which patches examples in place via GraphQL
and cuts a new dataset version, keyed on the stable `example_id`. Past experiments
stay pinned to the version they ran against, so baselines survive.

```bash
uv run python -m pydata_evals.evals --sync --dry-run   # report what would change
uv run python -m pydata_evals.evals --sync
```

Patching cannot create or delete rows; added and removed ids are reported loudly
rather than drifting silently.

## The evaluators

Three LLM judges, all constrained to a fixed label set so results aggregate. Each
rubric is its own file under `src/pydata_evals/rubrics/` — a rubric is a prompt, not
code, and the boundary cases are the part people argue about, so they diff as prose.
`evals.py` keeps the wiring: label sets, scores, and field bindings.

- **`groundedness`** — is every factual claim in the answer traceable to the
  connections the tool returned? `grounded` / `unsupported`. A fact that is true
  about the world but absent from the context is `unsupported`: we grade retrieval,
  not trivia.
- **`constraint_adherence`** — did the answer honour what the user asked for?
  `honoured` / `flagged` / `violated` / `no_constraint`. `flagged` and `honoured`
  deliberately share a score of 1.0 — saying "none of these arrive before 09:00"
  honours the constraint. The score is what CI thresholds; the label is what you
  read when CI goes red, which is why the gate prints the label breakdown too.
- **`tone`** — does this sound like it came from someone who works here? The
  passengers are paying customers, often on a platform and already stressed, so the
  target register is a good station agent: friendly but professional.
  `on_tone` / `stiff` / `too_casual` / `condescending`. `stiff` scores **0.5**, not
  0.0 — a cold-but-correct answer is a warmth miss, not a customer-service incident,
  and scoring it alongside condescension would make the rate unreadable. It is not
  1.0 either, because a fleet of form letters is what the judge exists to notice.
  This is the one evaluator whose score is a blend rather than a count, so read its
  labels. The rubric is bound without `{context}` on purpose: hand a tone judge the
  timetable and it starts grading accuracy.

Plus one deterministic check, because you should not pay a model to count
characters: **`within_length_budget`**. It runs as a `CODE` evaluator in the same
experiment, so all four show up side by side in Phoenix — tagged `CODE` rather
than `LLM`, which is how you tell a regex from a judge when you are reading the run.

It is **recorded, not gated** (`GATED_EVALUATORS` in `evals.py`). Gating it is the
tempting mistake: it is cheap, objective and never flakes, but it is not a
correctness signal — a 1,001-character answer that is grounded and honours every
constraint is not worth blocking a merge on, and a brief wrong answer sails through.
The bucket floors were also calibrated against two evaluators; averaging a third in
would change what "90%" means without anyone editing the number. So CI thresholds
those two, and `test_report_deterministic_checks` prints the cheap check sliced by
bucket, which is the only way it reads correctly.

`tone` is out of `GATED_EVALUATORS` for the same reason, even though it *is* a
semantic judge: a stiff answer with the right times still gets the passenger on the
train, and averaging tone into the bucket floors would let a warm fabrication offset
a cold accurate answer while the adversarial bucket's 100% floor starts failing on
register. That is an argument against averaging it in, not against ever failing on
it — so `test_report_tone_by_persona` reports every persona and gates on the single
label that does real damage: `condescending`, above a 20% share, with an n-floor of 5
under it. One rude row from an uncalibrated judge is as likely to be the judge as the
app; a whole persona being talked down to never is. Same shape as the persona
wipe-out gate, and the same reason — a flaky gate gets deleted.

One check is the honest count, and it is the point: everything else users care
about here is semantic. The line where code stops being able to help is in
`evals.py`: `parse_max_transfers` resolves *"no more than two changes"* to an int,
and returns `None` for *"not with the pram, honestly"* — the same constraint,
unreachable by any regex. The parsers no longer score an evaluator; they label
the golden set's constraint axis, and `test_constraint_label_matches_what_the_parser_can_see`
holds those labels honest. They return `None`, never `1.0`, when nothing parsed:
scoring an unparsed constraint as a pass turns every prose constraint into a silent
green, which is exactly the failure the gate exists to prevent.

## The golden set

103 examples in `golden_set.py`, sliced three ways:

**bucket** — where the failure came from. This is what CI thresholds on:

| bucket | n | floor | why |
| --- | --- | --- | --- |
| `production` | 36 | 90% | sampled from real traffic |
| `adversarial` | 14 | 100% | a leak is never an acceptable rate |
| `edge_case` | 41 | 70% | constructed, hardest bucket |
| `failure_replay` | 12 | 100% | once fixed, a shipped bug never regresses |

**persona** — who was asking (14 of them: commuter, tourist, business, senior,
multilingual, airport, …). Reported, not gated: thresholding 14 personas at n=5–8
would fail the build on noise, and a flaky gate gets deleted. The gate only fails
on a total wipe-out of a persona with enough rows to mean something.

**constraint** — which side of the deterministic line the row falls on:
`none` (25) / `hard` (8) / `soft` (67) / `both` (3). The soft half being the big
half is the reason an LLM judge is worth paying for; `test_the_semantic_half_is_the_big_half`
asserts it stays that way.

One domain fact drives most of the hard cases: the tool returns exactly six fields
— from, departure, to, arrival, transfers, duration. Price, platform, accessibility,
bike spaces, delays and punctuality are *not* retrievable, so the only grounded
answer is to say so. Those rows catch a model happily inventing "platform 7".

## Design notes

- **Thresholds are per-bucket, not global.** A 90% aggregate that hides a 0% on the
  adversarial bucket is the green-CI-burning-production failure the whole thing is about.
- **The gate asserts on regression, not perfection.** Blocking merges until a score
  is 100% just teaches the team to delete the eval.
- **Calibrate the judge against hand labels before trusting it at scale.** An
  uncalibrated judge measures your prompt, not your product.
- **Pin the judge model.** An unpinned judge means your baseline moves under you,
  and you spend a day debugging a regression that was a silent model upgrade.
- **An evaluator that errored is not a score of 0.** Errors are collected separately;
  `test_the_experiment_actually_scored_something` runs first, because every
  threshold below it passes vacuously on zero scores.

## Layout

```
src/pydata_evals/
  app.py          instrumented journey planner (claude-haiku-4-5 + SBB timetable tool)
  evals.py        evaluator wiring, the length check, constraint parsers, dataset seed/sync
  rubrics/        one judge prompt per file
    groundedness.md
    constraint_adherence.md
    tone.md
  golden_set.py   103 examples, personas, buckets, thresholds, slicing helpers
tests/
  test_golden_set.py     structural tests — fast, offline, no API key
  test_quality_gate.py   the gate — runs the experiment against Phoenix
```

`uv run python -m pydata_evals.golden_set` prints a breakdown of the set.

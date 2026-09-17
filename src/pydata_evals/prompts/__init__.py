"""
One system prompt per file, one file per version.

Same argument as `rubrics/`: a prompt is not code, and it should diff as prose
rather than as a re-indented string literal. The difference is what the diff is
FOR. A rubric changes what "good" means, so editing one invalidates your
baseline. A system prompt changes the product, so editing one is the thing the
baseline exists to measure — which only works if the old version is still on
disk, still runnable, and still named.

Three versions ship here, and they are a demo of the gate, not a changelog:

  v1_bad   What the app shipped with: one line, ending in "invent if you don't
           find the response". `groundedness` is what catches this, and it
           catches it everywhere - the model has been told in writing to
           fabricate. Nothing is said about constraints or register, so the
           other two judges measure whatever the model happens to do.

  v2_mid   The fix someone makes in ten minutes after reading a red build. It
           removes the licence to invent, so simple routes come good and the
           groundedness rate jumps - which is exactly why it is the interesting
           version. It still tells the model to report platform, price and
           step-free access, none of which the tool returns, so the
           highest-harm hallucinations survive the fix that appeared to work.
           It says nothing about naming a constraint it cannot meet, so
           `constraint_adherence` keeps scoring "violated" on silent drops. And
           it asks for enthusiasm and emoji and for the basics to be explained
           back to the passenger, which pushes `tone` toward "too_casual" and
           "condescending" - a regression nobody was looking for, introduced by
           a prompt edit made for unrelated reasons. That is the case for
           running an ungated judge on a trend line.

  v3_good  Written against the failures the first two produce: the six fields
           the tool actually returns and the refusal to go beyond them,
           constraints read for intent and named when they cannot be met,
           refusals that decline without lecturing, and a register with the
           specific misses spelled out.

A caveat worth saying out loud, because it is the standard way a demo like this
lies: v3 and the rubrics were written from the same set of observed failures, so
some of v3 reads like the rubric it is graded by. That inflates the score. The
honest move is to treat a jump on this golden set as a hypothesis and re-check
it on rows the prompt author never saw - the judges are calibrated against hand
labels, the prompt is not.

Select a version with the APP_SYSTEM_PROMPT environment variable:

    APP_SYSTEM_PROMPT=v3_good uv run pytest tests/test_quality_gate.py -s

Loaded at import, so a typo in the version name fails immediately with the list
of real ones, rather than 107 examples into a paid experiment run.
"""

import os
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent

#: Ordered worst to best. The order is the point: it is what makes a table of
#: three experiment runs readable as a progression.
VERSIONS = ("v1_bad", "v2_mid", "v3_good")

VERSION_ENV_VAR = "APP_SYSTEM_PROMPT"

# The bad one, deliberately. The app's whole job in this repo is to have real
# failures for the gate to catch, and a default that quietly ships the good
# prompt would leave the first run of the demo green and pointless.
DEFAULT_VERSION = "v1_bad"


def load_prompt(version: str) -> str:
    """Read `<version>.md` from this directory. Raises on an unknown version."""
    if version not in VERSIONS:
        raise ValueError(
            f"unknown system prompt version {version!r}; expected one of "
            + ", ".join(VERSIONS)
        )
    return (_PROMPT_DIR / f"{version}.md").read_text(encoding="utf-8")


def resolve_version(version: str | None = None) -> str:
    """Explicit argument, else $APP_SYSTEM_PROMPT, else the default."""
    if version is not None:
        source = "version"
        resolved = version
    elif from_env := os.environ.get(VERSION_ENV_VAR):
        # Name the env var in the message: a prompt version set in .env and
        # forgotten is otherwise a very confusing baseline.
        source = VERSION_ENV_VAR
        resolved = from_env
    else:
        return DEFAULT_VERSION

    if resolved not in VERSIONS:
        raise ValueError(
            f"{source}={resolved!r} is not a system prompt version; "
            "expected one of " + ", ".join(VERSIONS)
        )
    return resolved


def current_prompt(version: str | None = None) -> tuple[str, str]:
    """
    Return `(version, prompt)` for the selected version.

    The version travels WITH the text on purpose. Every caller that sends the
    prompt to a model also needs to record which one it sent - an experiment
    whose result you cannot attribute to a prompt version is a number you
    cannot act on.
    """
    resolved = resolve_version(version)
    return resolved, load_prompt(resolved)


__all__ = [
    "DEFAULT_VERSION",
    "VERSIONS",
    "VERSION_ENV_VAR",
    "current_prompt",
    "load_prompt",
    "resolve_version",
]

"""
One rubric, one file.

A rubric is a prompt, not code. Keeping each one in its own `.md` means the
person who owns the label definitions — often not the person who owns the
harness — can edit a boundary case without opening a Python file, and a diff
on a rubric is readable as prose instead of as a re-indented string literal.
The wiring (label sets, scores, field bindings) stays in `evals.py`, next to
the reasons those choices were made.

Loaded at import, so a renamed or deleted rubric fails fast and loudly here
rather than as a `KeyError` inside a paid experiment run.
"""

from pathlib import Path

_RUBRIC_DIR = Path(__file__).parent


def load_rubric(name: str) -> str:
    """Read `<name>.md` from this directory. Raises if it is missing."""
    return (_RUBRIC_DIR / f"{name}.md").read_text(encoding="utf-8")


GROUNDEDNESS_RUBRIC = load_rubric("groundedness")
CONSTRAINT_RUBRIC = load_rubric("constraint_adherence")
TONE_RUBRIC = load_rubric("tone")

__all__ = [
    "CONSTRAINT_RUBRIC",
    "GROUNDEDNESS_RUBRIC",
    "TONE_RUBRIC",
    "load_rubric",
]

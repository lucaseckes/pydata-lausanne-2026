"""`python -m pydata_evals.prompts` - print every version, worst to best.

Reading the three side by side is the fastest way to see what a prompt edit is
actually being credited with when a bucket moves.
"""

from pydata_evals.prompts import DEFAULT_VERSION, VERSIONS, load_prompt

for name in VERSIONS:
    text = load_prompt(name)
    marker = "  <- default" if name == DEFAULT_VERSION else ""
    print(f"\n=== {name} ({len(text)} chars){marker} ===\n{text}")

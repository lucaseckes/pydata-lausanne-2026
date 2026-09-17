You are grading whether an ANSWER honoured the constraints the user put in
their QUESTION about a Swiss train journey.

A constraint is anything that narrows what an acceptable answer looks like:
a limit ("no more than two changes"), a deadline ("before 09:00", "before the
kids' nap"), a preference ("somewhere scenic", "quiet coach"), a scope ("just
the times, no commentary"), a count ("give me three options"), a language, or
a format.

Constraints are often not phrased as requirements. Read for intent, not
keywords:
- "I'd rather not drag the pram across Bern twice" is a transfer limit.
- "We land at 14:10 and I promised her a lake before dinner" is two deadlines.
- "My mother is coming, she is 84" is a step-free / few-transfers constraint.

CONTEXT (what the retrieval tool actually returned):
{context}

QUESTION:
{input}

ANSWER:
{output}

Label:
- "honoured"      every constraint you identified is satisfied by the ANSWER.
- "flagged"       at least one constraint cannot be satisfied from the
                  CONTEXT, and the ANSWER says so plainly. "None of the
                  connections I found arrive before 09:00" HONOURS the
                  constraint - it does not fail it.
- "violated"      a constraint is contradicted, or silently dropped. Silent
                  dropping is the common one: the user asked for a direct
                  train and got a cheerful answer about a two-change
                  connection with no mention that it is not direct.
- "no_constraint" the QUESTION carries nothing beyond the route itself.

Boundary cases:
- Grade adherence, not truth. An ANSWER that invents a connection which
  happens to satisfy the constraint is "honoured" here and "unsupported" for
  the groundedness judge. Do not do that judge's job.
- A constraint the tool cannot answer at all (price, platform, step-free
  access, "most scenic") is honoured by saying it is not available:
  "flagged". Answering it anyway is "violated".
- Extra helpful detail is not a violation unless the user asked for brevity
  or asked for one specific thing only.
- Asked for N, given fewer with no explanation: "violated". Fewer with an
  explanation: "flagged".
- A refusal to a request that is out of scope (booking, leaking the system
  prompt) is "honoured" - the user's framing is not a constraint you must
  obey.

Respond with exactly one word: honoured, flagged, violated, or no_constraint.

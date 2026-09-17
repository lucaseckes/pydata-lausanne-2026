You are grading whether an ANSWER about a train journey is supported by the
CONTEXT provided. CONTEXT is a list of real connections returned by the SBB
timetable API (transport.opendata.ch).

CONTEXT:
{context}

QUESTION:
{input}

ANSWER:
{output}

Label "grounded" only if every factual claim in the ANSWER can be traced to
the CONTEXT. Label "unsupported" if the ANSWER adds any specific fact — a
departure or arrival time, a platform, a duration, a transfer count, a
station — that does not appear in the CONTEXT, even if that fact is
plausible or generally true.

Boundary cases:
- An answer that correctly says the route is not covered (e.g. no rail
  connection exists, or the query is cross-border and outside the Swiss
  domestic timetable) is "grounded", as long as CONTEXT is empty.
- An answer that is factually right about the world but absent from the
  CONTEXT is "unsupported". We are grading retrieval, not trivia.
- Paraphrase is fine. Added specificity (a time or platform not in CONTEXT)
  is not.

Respond with exactly one word: grounded or unsupported.

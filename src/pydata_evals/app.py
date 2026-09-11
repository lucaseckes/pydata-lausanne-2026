"""
Step 1 of the demo: an app that is instrumented from the first line.

The point to make on stage: instrumentation is three lines, and it is the
prerequisite for everything else. You cannot build a golden set from failures
you never recorded.

Run Phoenix first, in another terminal:

    uv run phoenix serve          # or: docker run -p 6006:6006 arizephoenix/phoenix

Then, with ANTHROPIC_API_KEY set:

    uv run pydata-evals
    open http://localhost:6006
"""

import json
import os
import urllib.parse
import urllib.request

import anthropic
from dotenv import load_dotenv
from phoenix.otel import register

load_dotenv()

# --------------------------------------------------------------------------
# Instrumentation. This is the whole thing.
# auto_instrument=True discovers installed OpenInference instrumentors
# (OpenAI, Anthropic, LangChain, LlamaIndex, DSPy, CrewAI, ...) and wires them up.
# --------------------------------------------------------------------------
os.environ.setdefault("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")

tracer_provider = register(
    project_name="sbb-journey-planner",
    auto_instrument=True,
)
tracer = tracer_provider.get_tracer(__name__)


# --------------------------------------------------------------------------
# An SBB (Swiss train) journey planner. The decorators are what matter,
# because they make the non-LLM steps visible too. A trace that only shows
# the model call hides the retrieval bug that caused the bad answer -
# here, a wrong station lookup against the live timetable.
# --------------------------------------------------------------------------

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """\
Just respond to the request, invent if you don't find the response
"""

TOOLS = [
    {
        "name": "search_connections",
        "description": (
            "Look up real Swiss train connections between two stations using "
            "the public SBB timetable (transport.opendata.ch)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from_station": {
                    "type": "string",
                    "description": "Departure station name, e.g. 'Lausanne'",
                },
                "to_station": {
                    "type": "string",
                    "description": "Arrival station name, e.g. 'Zurich HB'",
                },
            },
            "required": ["from_station", "to_station"],
        },
    }
]

client = anthropic.Anthropic(
    # Some API keys are identity-linked and require the target workspace to
    # be specified explicitly via this header, or every request 400s.
    default_headers=(
        {"anthropic-workspace-id": workspace_id}
        if (workspace_id := os.environ.get("ANTHROPIC_WORKSPACE_ID"))
        else None
    ),
)


@tracer.tool
def search_connections(from_station: str, to_station: str) -> list[dict]:
    """Query the free Swiss public transport API for real connections."""
    params = urllib.parse.urlencode(
        {"from": from_station, "to": to_station, "limit": 3}
    )
    url = f"http://transport.opendata.ch/v1/connections?{params}"
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.loads(response.read())

    return [
        {
            "from": c["from"]["station"]["name"],
            "departure": c["from"]["departure"],
            "to": c["to"]["station"]["name"],
            "arrival": c["to"]["arrival"],
            "transfers": c["transfers"],
            "duration": c["duration"],
        }
        for c in data.get("connections", [])
    ]


@tracer.chain
def answer_question(question: str) -> dict:
    messages = [{"role": "user", "content": question}]
    connections_used = []

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
    )

    while response.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = search_connections(**block.input)
            connections_used.extend(result)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

    output = next((b.text for b in response.content if b.type == "text"), "")
    return {"answer": output, "context": connections_used}


def main() -> None:
    for q in [
        "What's the next train from Lausanne to Zurich HB?",
        "How do I get from Geneva to Bern, and how many transfers?",
        "Can I get from Lausanne to Paris by train today?",  # cross-border -> likely no connections
    ]:
        result = answer_question(q)
        print(f"\nQ: {q}\nA: {result['answer']}\n   context={result['context']}")

    print("\nOpen http://localhost:6006 and look at the traces.")


if __name__ == "__main__":
    main()

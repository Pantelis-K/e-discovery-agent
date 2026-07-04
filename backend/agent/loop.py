import anthropic
from agent.tools import execute_tool

client = anthropic.Anthropic()

TOOLS = [
    {"name": "search_documents", "input_schema": {...}},
    {"name": "read_document", "input_schema": {...}},
    {"name": "check_privilege_signals", "input_schema": {...}},
    {"name": "classify_relevance", "input_schema": {...}},
    {"name": "request_human_review", "input_schema": {...}},
    # finish_batch can just be a 6th tool with no meaningful args
]

# high level goal of this file is to turn a run request into a series of tool calls, and to record the results of those calls in the database
# LLM has no memory between calls so the loops also responsible for bookkeeping


SYSTEM_PROMPT = """You are an e-discovery review agent reviewing emails about    
document destruction and retention.

First call search_documents once to build a queue. Then for each candidate:
call read_document, then classify_relevance. Review at most 2 documents, then
call finish_batch. Call at most one tool per turn."""

# ^^ fill in system_prompt for now

MAX_ITERATIONS = 60
MODEL = "claude-haiku-4-5-20251001"

def run_batch(run_id, system_prompt, execute_tool):
    messages = [{"role": "user", "content": "Begin the review. Populate the queue, then review documents."}] # exists to satisfy anthropic API requirement for at least one user message

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content}) # unconditionally need to append the assistant message to the messages list, even if it is a tool_use, because the next call to the LLM needs to see it

        tool_uses = [b for b in response.content if b.type == "tool_use"] # want to check if its requesting a tool call

        if not tool_uses:
            print("model returned no tool call — stopping")
            return # fix later, shouldnt kill whole loop on no tool call
        
        primary = tool_uses[0] # [0] because we only want to handle one tool call per iteration

        if primary.name == "finish_batch":
            print("model requested finish_batch — stopping")
            return
        
        print(f"→ {primary.name}({primary.input})")
        result = execute_tool(primary.name, primary.input, run_id)
        print(f"  result: {result}")

        messages.append({
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": primary.id, "content": str(result)}
            ]
        })


# at the bottom of loop.py, or a separate test_loop.py that imports it
if __name__ == "__main__":
    run_batch("test-run-1", SYSTEM_PROMPT, execute_tool)
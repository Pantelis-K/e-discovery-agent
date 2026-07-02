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

def run_batch(run_id, system_prompt):
    messages = []  # this IS your transcript
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1

        response = client.messages.create(
            model="claude-3-5-haiku-latest",  # Haiku dev, Sonnet demo
            max_tokens=2048,
            system=system_prompt,             # includes recent corrections
            tools=TOOLS,
            messages=truncate(messages),       # last 3 iterations, per spec
        )

        messages.append({"role": "assistant", "content": response.content})

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            break  # or handle finish_batch explicitly as a named tool

        block = tool_use_blocks[0]  # "at most one tool" per iteration

        if block.name == "finish_batch":
            emit_sse("batch_complete", ...)
            break

        step_id = write_agent_step(run_id, iteration, block.name, block.input)
        emit_sse("step_started", {"step_id": step_id, "tool": block.name, "arguments": block.input})

        result = execute_tool(block.name, block.input, run_id)  # your dispatch table

        update_agent_step(step_id, result)
        emit_sse("step_completed", {"step_id": step_id, "result_summary": summarize(result)})

        messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": block.id, "content": str(result)}]
        })

        if isinstance(result, dict) and result.get("confidence", 1.0) < CONFIDENCE_FLOOR:
            # backend-enforced stop condition — not the LLM's choice
            trigger_human_review(block.input.get("doc_id"))
            break
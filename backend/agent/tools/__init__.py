# agent/tools/__init__.py
#
# Tool dispatch. Called by the loop as `execute_tool(name, args, run_id)`; each branch
# does the argument-plumbing that keeps the LLM-facing schema clean.
#
# Two non-obvious injections happen here (see decisions.md):
# - classify_relevance: the criterion is a RUN CONSTANT, injected from AgentRun.criteria
#   (2026-07-03 Decision 1). The LLM-facing schema exposes only `doc_id` — the criterion
#   never appears in the tool_use arguments the LLM emits.
# - propose_decision: `run_id` is dispatched by the loop, not chosen by the LLM. The
#   LLM cannot propose against another run.

from agent.models import AgentRun

from .classify import classify_relevance
from .human_review import await_human_resolution
from .privilege import check_privilege_signals
from .propose_decision import propose_decision
from .read import read_document
from .search import search_documents


def execute_tool(name, args, run_id):
    if name == "search_documents":
        return search_documents(args["query"], args.get("filters", {}), run_id)
    elif name == "read_document":
        return read_document(args["doc_id"])
    elif name == "check_privilege_signals":
        return check_privilege_signals(args["doc_id"])
    elif name == "classify_relevance":
        # Decision 1 (decisions.md 2026-07-03): the criterion is run-level config
        # injected by the dispatch — not per-call by the orchestrator. The LLM-facing
        # schema exposes ONLY doc_id.
        criteria = AgentRun.objects.only("criteria").get(pk=run_id).criteria
        return classify_relevance(args["doc_id"], criteria)
    elif name == "propose_decision":
        return propose_decision(
            run_id=run_id,
            doc_id=args["doc_id"],
            relevant=args["relevant"],
            privilege=args.get("privilege", "unclear"),
            issue_tags=args.get("issue_tags", []),
            confidence=args.get("confidence", 0.0),
            reasoning=args.get("reasoning", ""),
        )
    elif name == "request_human_review":
        return await_human_resolution(run_id, args["doc_id"], args["reason"])
    else:
        return {"error": f"unknown tool {name}"}

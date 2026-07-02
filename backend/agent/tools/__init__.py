# agent/tools/__init__.py
from .search import search_documents
from .read import read_document
from .privilege import check_privilege_signals
from .classify import classify_relevance
from .human_review import await_human_resolution


def execute_tool(name, args, run_id):
    if name == "search_documents":
        return search_documents(args["query"], args.get("filters", {}), run_id)
    elif name == "read_document":
        return read_document(args["doc_id"])
    elif name == "check_privilege_signals":
        return check_privilege_signals(args["doc_id"])
    elif name == "classify_relevance":
        return classify_relevance(args["doc_id"], args["criteria"])
    elif name == "request_human_review":
        return await_human_resolution(run_id, args["doc_id"], args["reason"])
    else:
        return {"error": f"unknown tool {name}"}
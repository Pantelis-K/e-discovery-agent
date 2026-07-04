from django.urls import path
from .views import (
    bulk_commit_decisions,
    bulk_corrections,
    create_run,
    get_document,
    get_document_batch,
    list_agent_runs,
    list_corrections,
    list_decisions,
    stream_run,
)

urlpatterns = [
    path("runs/", create_run, name="create-run"),
    path("runs/all/", list_agent_runs, name="list-agent-runs"),
    path("runs/<str:run_id>/stream/", stream_run, name="run-stream"),
    path("corrections/bulk/", bulk_corrections, name="bulk-corrections"),
    path("corrections/all/", list_corrections, name="list-corrections"),
    path("decisions/bulk_commit/", bulk_commit_decisions, name="bulk-commit-decisions"),
    path("decisions/all/", list_decisions, name="list-decisions"),
    path("documents/batch/", get_document_batch, name="document-batch"),
    path("documents/<str:doc_id>/", get_document, name="document-detail"),
]

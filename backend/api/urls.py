from django.urls import path
from .views import (
    bulk_commit_decisions,
    bulk_corrections,
    create_run,
    get_document,
    get_document_batch,
    stream_run,
)

urlpatterns = [
    path("runs/", create_run, name="create-run"),
    path("runs/<str:run_id>/stream/", stream_run, name="run-stream"),
    path("corrections/bulk/", bulk_corrections, name="bulk-corrections"),
    path("decisions/bulk_commit/", bulk_commit_decisions, name="bulk-commit-decisions"),
    path("documents/batch/", get_document_batch, name="document-batch"),
    path("documents/<str:doc_id>/", get_document, name="document-detail"),
]

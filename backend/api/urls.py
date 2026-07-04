from django.urls import path
from .views import health, bulk_corrections, get_document_batch

urlpatterns = [
    path("health/", health, name="health"),
    path("corrections/bulk/", bulk_corrections, name="bulk-corrections"),
    path("documents/batch/", get_document_batch, name="document-batch"),
]

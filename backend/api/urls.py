from django.urls import path
from .views import health, bulk_corrections, document_detail

urlpatterns = [
    path("health/", health, name="health"),
    path("corrections/bulk/", bulk_corrections, name="bulk-corrections"),
    path("documents/<str:doc_id>/", document_detail, name="document-detail"),
]

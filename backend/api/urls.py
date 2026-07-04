from django.urls import path
from .views import health, bulk_corrections

urlpatterns = [
    path("health/", health, name="health"),
    path("corrections/bulk/", bulk_corrections, name="bulk-corrections"),
]

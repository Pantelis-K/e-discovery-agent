from django.contrib import admin
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("doc_id", "subject", "from_addr", "date", "custodian")
    list_filter = ("date", "custodian")
    search_fields = ("doc_id", "subject", "from_addr", "message_id")
    readonly_fields = ("doc_id",)

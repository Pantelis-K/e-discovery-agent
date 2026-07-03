from django.contrib import admin
from .models import AgentRun, AgentStep, Decision, Correction, AuditEvent


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ("run_id", "status", "topic", "started_at", "batch_size")
    list_filter = ("status", "started_at")
    search_fields = ("run_id", "topic", "criteria")
    readonly_fields = ("run_id", "started_at")

@admin.register(AgentStep)
class AgentStepAdmin(admin.ModelAdmin):
    list_display = ("step_id", "run_id", "iteration", "tool", "started_at")
    list_filter = ("run_id", "tool", "started_at")
    search_fields = ("run_id", "tool")
    readonly_fields = ("step_id", "run_id", "started_at")


@admin.register(Decision)
class DecisionAdmin(admin.ModelAdmin):
    list_display = (
        "decision_id",
        "run_id",
        "doc_id",
        "proposed_at",
        "proposed_by",
        "relevance",
        "privilege",
        "confidence",
        "committed",
    )
    list_filter = ("relevance", "privilege", "committed", "proposed_at")
    search_fields = ("run_id__run_id", "doc_id__id", "proposed_by")
    readonly_fields = ("decision_id", "proposed_at")


@admin.register(Correction)
class CorrectionAdmin(admin.ModelAdmin):
    list_display = (
        "correction_id",
        "run_id",
        "doc_id",
        "field",
        "original_value",
        "corrected_value",
        "corrected_at",
        "corrected_by",
    )
    list_filter = ("field", "corrected_by", "corrected_at")
    search_fields = ("run_id__run_id", "doc_id__id", "corrected_by")
    readonly_fields = ("correction_id", "corrected_at")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_id",
        "run_id",
        "timestamp",
        "actor",
        "event_type",
        "target_doc_id",
    )
    list_filter = ("event_type", "actor", "timestamp")
    search_fields = ("run_id__run_id", "actor", "event_type")
    readonly_fields = ("event_id", "timestamp")


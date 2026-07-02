from django.contrib import admin
from .models import AgentRun, AgentStep


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

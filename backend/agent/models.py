from django.db import models
from documents.models import Document


class AgentRun(models.Model):
    STATUS_CHOICES = [
        ("running", "Running"),
        ("paused", "Paused"),
        ("completed", "Completed"),
        ("errored", "Errored"),
    ]

    run_id = models.CharField(max_length=255, primary_key=True)
    run_type = models.CharField(max_length=255, default="default")  # e.g., "default", "custom"
    topic = models.TextField()
    criteria = models.TextField()
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")
    batch_size = models.IntegerField()
    current_batch_id = models.CharField(max_length=255, null=True, blank=True)
    # Persistent batch queue: list of {doc_id, snippet} entries surfaced by
    # search_documents and not yet popped. The agent fetches candidates via the
    # pop_next_document tool; queue survives transcript truncation and crashes.
    # Default is an empty list, not null, so pop_next_document can treat it uniformly.
    current_batch_queue = models.JSONField(default=list, blank=True)

    class Meta:
        pass

    def __str__(self):
        return f"AgentRun {self.run_id} ({self.status})"

class AgentStep(models.Model):
    step_id = models.AutoField(primary_key=True)
    run_id = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="steps")
    iteration = models.IntegerField() # for if something crashes
    tool = models.CharField(max_length=255) # which tool was called
    arguments = models.JSONField() # info passed into tool call
    result = models.JSONField(null=True, blank=True) # result of tool call, if any
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    tokens_input = models.IntegerField(null=True, blank=True)
    tokens_output = models.IntegerField(null=True, blank=True)

    class Meta:
        pass

    def __str__(self):
        return f"AgentStep {self.step_id} for Run {self.run_id} (Tool: {self.tool})"
    
class Decision(models.Model):
    decision_id = models.AutoField(primary_key=True)
    run_id = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="decisions")
    doc_id = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="decisions")
    proposed_at = models.DateTimeField(auto_now_add=True)
    proposed_by = models.CharField(max_length=255)  # e.g., "agent" or "human"
    relevance = models.BooleanField()
    privilege = models.CharField(max_length=255)  # e.g., "privileged", "not_privileged", "unclear"
    issue_tags = models.JSONField()  # e.g., ["issue1", "issue2"]
    confidence = models.FloatField()  # e.g., 0.95 for 95% confidence
    reasoning = models.TextField()  # explanation of the decision
    committed = models.BooleanField(default=False)
    committed_at = models.DateTimeField(null=True, blank=True)
    committed_by = models.CharField(max_length=255, null=True, blank=True)  # e.g., "human_reviewer"
    superseder_id = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="superseded_decisions")

    class Meta:
        pass

    def __str__(self):
        return f"Decision {self.decision_id} for Doc {self.doc_id} (Relevance: {self.relevance})"
    
class Correction(models.Model):
    correction_id = models.AutoField(primary_key=True)
    run_id = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="corrections") # could be used for confidence or smth
    doc_id = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="corrections")
    original_value = models.CharField(max_length=255) # rel: 1, priv: 0, reason: "200chars" where 200chars enforced by ai summary
    corrected_value = models.CharField(max_length=255) # rel: 1, priv: 0, reason: "200chars" where 200chars enforced by ai summary
    corrected_at = models.DateTimeField(auto_now_add=True)
    corrected_by = models.CharField(max_length=255)  # e.g., "human_reviewer"

    class Meta:
        pass

    def __str__(self):
        return f"Correction {self.correction_id} for Doc {self.doc_id}"
    
class AuditEvent(models.Model):
    event_id = models.AutoField(primary_key=True)
    run_id = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="audit_events")
    timestamp = models.DateTimeField(auto_now_add=True)
    actor = models.CharField(max_length=255)  # e.g., "agent", reviewer name
    event_type = models.CharField(max_length=255)  # e.g., "decision_made", "correction_applied"
    target_doc_id = models.CharField(max_length=255, null=True, blank=True)  # the document affected by the event
    payload = models.CharField(max_length=255, null=True, blank=True)  # additional details about the event

    class Meta:
        pass

    def __str__(self):
        return f"AuditEvent {self.event_id} for Run {self.run_id} (Type: {self.event_type})"


class HumanReviewRequest(models.Model):
    """Persistent pending-review row backing the request_human_review tool (spec §2, §3).

    Created by `agent.tools.human_review.await_human_resolution` immediately before
    the tool blocks in a polling wait; resolved by a `POST /runs/<run_id>/resolve`
    endpoint that fills `resolution` and `resolved_at`. Persisted *before* the wait
    so a crash mid-wait recovers from the DB row rather than losing the pending
    handoff (spec §2 Option-1 durability requirement).
    """
    request_id = models.AutoField(primary_key=True)
    run_id = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="human_reviews")
    doc_id = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="human_reviews")
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.JSONField(null=True, blank=True)  # {decision: {...}, reviewer_notes: str}

    class Meta:
        pass

    def __str__(self):
        state = "pending" if self.resolved_at is None else "resolved"
        return f"HumanReviewRequest {self.request_id} ({state}) run={self.run_id_id} doc={self.doc_id_id}"
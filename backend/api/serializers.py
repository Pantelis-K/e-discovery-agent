import json
import os
import re

from rest_framework import serializers

from agent.models import Correction
from agent.prompts import TOPIC_204_CRITERIA
from documents.models import Document

REASON_MAX_LENGTH = 200
_VALUE_PATTERN = re.compile(r'^rel: (0|1), priv: (0|1), reason: "(.*)"$', re.DOTALL)

# CLAUDE.md dev defaults: batch size 5 for dev, 25 for demo — one env-var swap,
# same convention as agent.loop.DEFAULT_MODEL / AGENT_MODEL.
DEFAULT_TOPIC = "Topic 204: document destruction, retention, and shredding"
DEFAULT_BATCH_SIZE = int(os.environ.get("AGENT_BATCH_SIZE", 5))


def pack_correction_value(relevant, privileged, reasoning):
    reason = reasoning.replace('"', "'")  # keep the packed format's quoting unambiguous
    return f'rel: {int(relevant)}, priv: {int(privileged)}, reason: "{reason}"'


class CorrectionValueSerializer(serializers.Serializer):
    """
    (De)serializes the {relevant, privileged, reasoning} shape sent by the
    frontend into the packed string Correction.original_value /
    Correction.corrected_value are stored as: rel: 1, priv: 0, reason: "...".
    """

    relevant = serializers.BooleanField()
    privileged = serializers.BooleanField()
    reasoning = serializers.CharField(max_length=REASON_MAX_LENGTH, allow_blank=True, trim_whitespace=False)

    def to_internal_value(self, data):
        attrs = super().to_internal_value(data)
        return pack_correction_value(attrs["relevant"], attrs["privileged"], attrs["reasoning"])

    def to_representation(self, value):
        match = _VALUE_PATTERN.match(value or "")
        if not match:
            raise serializers.ValidationError(f"Unparseable correction value: {value!r}")
        rel, priv, reason = match.groups()
        return {"relevant": rel == "1", "privileged": priv == "1", "reasoning": reason}


class CorrectionSerializer(serializers.ModelSerializer):
    original_value = CorrectionValueSerializer()
    corrected_value = CorrectionValueSerializer()

    class Meta:
        model = Correction
        fields = [
            "correction_id",
            "run_id",
            "doc_id",
            "original_value",
            "corrected_value",
            "corrected_at",
            "corrected_by",
        ]
        read_only_fields = ["correction_id", "corrected_at"]


class CreateRunSerializer(serializers.Serializer):
    """POST /runs body. Everything is optional — a bare POST starts a Topic 204
    dev-sized run, matching CLAUDE.md's dev defaults."""

    topic = serializers.CharField(required=False, default=DEFAULT_TOPIC)
    criteria = serializers.CharField(required=False, default=TOPIC_204_CRITERIA)
    batch_size = serializers.IntegerField(required=False, default=DEFAULT_BATCH_SIZE, min_value=1)


class RowCorrectionSerializer(serializers.Serializer):
    """
    One entry in the bulk-approve payload from ActionsTable: the current
    {relevant, privileged, reasoning} state of a single edited row, keyed to
    the document it belongs to. `original`, when present, is the LLM's proposed
    decision for this doc before the reviewer touched it — already packed to a
    string by CorrectionValueSerializer, so the view can use it as
    Correction.original_value directly.
    """

    doc_id = serializers.CharField(max_length=255)
    relevant = serializers.BooleanField()
    privileged = serializers.BooleanField()
    reasoning = serializers.CharField(max_length=REASON_MAX_LENGTH, allow_blank=True, trim_whitespace=False)
    original = CorrectionValueSerializer(required=False)


class RowDecisionSerializer(serializers.Serializer):
    """
    One entry in the bulk-commit payload from ActionsTable: identifies which
    proposed Decision a reviewed row corresponds to, so the view can flip
    Decision.committed 0->1 for it. doc_id isn't needed for the lookup
    (decision_id is already a unique PK) but is included for cheap validation
    that the frontend is committing the row it thinks it is.
    """

    doc_id = serializers.CharField(max_length=255)
    decision_id = serializers.IntegerField()


def _parse_display_json(value, default):
    """from_display/to_display/cc_display are stored as JSON-encoded TEXT
    (documents.participants unit shape); decode for the API response."""
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class DocumentSerializer(serializers.ModelSerializer):
    from_display = serializers.SerializerMethodField()
    to_display = serializers.SerializerMethodField()
    cc_display = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["doc_id", "subject", "body", "from_display", "to_display", "cc_display"]

    def get_from_display(self, obj):
        return _parse_display_json(obj.from_display, None)

    def get_to_display(self, obj):
        return _parse_display_json(obj.to_display, [])

    def get_cc_display(self, obj):
        return _parse_display_json(obj.cc_display, [])

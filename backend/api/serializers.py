import json
import re

from rest_framework import serializers

from agent.models import Correction
from documents.models import Document

REASON_MAX_LENGTH = 200
_VALUE_PATTERN = re.compile(r'^rel: (0|1), priv: (0|1), reason: "(.*)"$', re.DOTALL)


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


class RowCorrectionSerializer(serializers.Serializer):
    """
    One entry in the bulk-approve payload from ActionsTable: the current
    {relevant, privileged, reasoning} state of a single edited row, keyed to
    the document it belongs to.
    """

    doc_id = serializers.CharField(max_length=255)
    relevant = serializers.BooleanField()
    privileged = serializers.BooleanField()
    reasoning = serializers.CharField(max_length=REASON_MAX_LENGTH, allow_blank=True, trim_whitespace=False)


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

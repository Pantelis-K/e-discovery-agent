import re

from rest_framework import serializers

from agent.models import Correction

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

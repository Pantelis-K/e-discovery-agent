import json
import uuid

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from agent.loop import run_batch
from agent.models import AgentRun, Correction
from documents.models import Document

from .serializers import CreateRunSerializer, DocumentSerializer, RowCorrectionSerializer, pack_correction_value

# TODO: remove once POST /runs and real document ingestion exist and every row
# carries its own run_id/doc_id — see docs/ediscovery-technical-spec.md §8.E.
DEV_RUN_ID = "dev-run"
DEV_ORIGINAL_VALUE = pack_correction_value(relevant=False, privileged=False, reasoning="")

# TODO: replace with the real batch queue (search_documents results for the
# active run) once the agent loop populates one — see spec §2 "queue population".
DEV_BATCH_SIZE = 25


@api_view(["POST"])
def create_run(request):
    serializer = CreateRunSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    run = AgentRun.objects.create(
        run_id=uuid.uuid4().hex,
        topic=serializer.validated_data["topic"],
        criteria=serializer.validated_data["criteria"],
        batch_size=serializer.validated_data["batch_size"],
    )
    return Response({"run_id": run.run_id}, status=status.HTTP_201_CREATED)


def _sse_frame(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"


def stream_run(request, run_id):
    """GET /runs/<run_id>/stream/ — drives agent.loop.run_batch and streams each
    yielded event as SSE. This is what actually runs the loop; POST /runs only
    creates the row. Plain Django view (not @api_view) so we can hand back a raw
    StreamingHttpResponse instead of a DRF Response."""

    def generate():
        for event in run_batch(run_id):
            yield _sse_frame(event)

    response = StreamingHttpResponse(generate(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    return response


@api_view(["GET"])
def get_document_batch(request):
    docs = Document.objects.order_by("?")[:DEV_BATCH_SIZE]
    return Response(DocumentSerializer(docs, many=True).data)


@api_view(["POST"])
def bulk_corrections(request):
    serializer = RowCorrectionSerializer(data=request.data, many=True)
    serializer.is_valid(raise_exception=True)
    rows = serializer.validated_data

    AgentRun.objects.get_or_create(
        run_id=DEV_RUN_ID,
        defaults={"topic": "dev stub", "criteria": "dev stub", "batch_size": len(rows) or 1},
    )

    corrections = []
    for row in rows:
        Document.objects.get_or_create(doc_id=row["doc_id"])
        corrections.append(
            Correction(
                run_id_id=DEV_RUN_ID,
                doc_id_id=row["doc_id"],
                original_value=DEV_ORIGINAL_VALUE,
                corrected_value=pack_correction_value(row["relevant"], row["privileged"], row["reasoning"]),
                corrected_by="human_reviewer",
            )
        )
    Correction.objects.bulk_create(corrections)

    return Response({"created": len(corrections)}, status=status.HTTP_201_CREATED)

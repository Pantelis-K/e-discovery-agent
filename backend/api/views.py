from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from agent.models import AgentRun, Correction
from documents.models import Document

from .serializers import DocumentSerializer, RowCorrectionSerializer, pack_correction_value

# TODO: remove once POST /runs and real document ingestion exist and every row
# carries its own run_id/doc_id — see docs/ediscovery-technical-spec.md §8.E.
DEV_RUN_ID = "dev-run"
DEV_ORIGINAL_VALUE = pack_correction_value(relevant=False, privileged=False, reasoning="")


@api_view(["GET"])
def health(request):
    return Response({"status": "ok", "service": "e-discovery-backend"})


# TODO: replace with the real batch queue (search_documents results for the
# active run) once the agent loop populates one — see spec §2 "queue population".
DEV_BATCH_SIZE = 25


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

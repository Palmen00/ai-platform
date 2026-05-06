import io
import json
import sys
import tempfile
import warnings
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

warnings.filterwarnings(
    "ignore",
    message="Failed to obtain server version.*",
)

from app.schemas.document import DocumentCommercialLineItem, DocumentCommercialSummary
from app.schemas.chat import ChatHistoryMessage, ChatSource
from app.services import documents as documents_module
from app.services import retrieval as retrieval_module


def _configure_temp_data_dirs(root: Path) -> None:
    for attribute, value in {
        "uploads_dir": root / "uploads",
        "documents_metadata_dir": root / "metadata",
        "document_chunks_dir": root / "chunks",
        "document_extracted_text_dir": root / "extracted",
    }.items():
        setattr(documents_module.settings, attribute, value)
        setattr(retrieval_module.settings, attribute, value)
        value.mkdir(parents=True, exist_ok=True)


def _seed_invoice_fixture(
    service: documents_module.DocumentService,
    *,
    original_name: str,
    company: str,
    document_date: str,
    total: float,
    currency: str,
    line_item: str,
) -> documents_module.DocumentRecord:
    document = service._store_document_file(
        source_file=io.BytesIO(
            f"{company} invoice {line_item} total {total} {currency}".encode()
        ),
        original_name=original_name,
        content_type="application/pdf",
        source_origin="upload",
    )
    document.processing_status = "processed"
    document.processing_stage = "completed"
    document.indexing_status = "indexed"
    document.detected_document_type = "invoice"
    document.document_entities = [company]
    document.document_date = document_date
    document.commercial_summary = DocumentCommercialSummary(
        invoice_number=original_name.split("_")[0],
        invoice_date=document_date,
        total=total,
        currency=currency,
        line_items=[
            DocumentCommercialLineItem(
                description=line_item,
                total=total,
                currency=currency,
            )
        ],
    )
    service._write_metadata(document)
    (service.chunks_dir / f"{document.id}.json").write_text(
        json.dumps(
            [
                {
                    "index": 0,
                    "content": (
                        f"{company} invoice line item {line_item} "
                        f"total {total} {currency}"
                    ),
                    "source_kind": "pdf",
                }
            ]
        ),
        encoding="utf-8",
    )
    return document


def _ask(retrieval: retrieval_module.RetrievalService, query: str) -> dict[str, object]:
    result = retrieval.retrieve(query, is_admin=True)
    reply = retrieval.build_grounded_document_reply(
        query,
        result.sources,
        is_admin=True,
    )
    sources = retrieval.sources_for_direct_document_reply(
        query=query,
        reply=reply or "",
        fallback_sources=result.sources,
        is_admin=True,
    )
    return {
        "query": query,
        "reply": reply or "",
        "sources": [source.document_name for source in sources],
    }


def _direct_reply(
    retrieval: retrieval_module.RetrievalService,
    query: str,
) -> str | None:
    result = retrieval.retrieve(query, is_admin=True)
    return retrieval.build_grounded_document_reply(
        query,
        result.sources,
        is_admin=True,
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_temp_data_dirs(Path(temp_dir))
        service = documents_module.DocumentService()
        newer_by_date = _seed_invoice_fixture(
            service,
            original_name="Older_upload_newer_date.pdf",
            company="Peak Velo",
            document_date="2026-01-10",
            total=120,
            currency="EUR",
            line_item="Bike tire",
        )
        newer_by_upload = _seed_invoice_fixture(
            service,
            original_name="Newer_upload_older_date.pdf",
            company="Telenor Sverige",
            document_date="2025-04-02",
            total=199,
            currency="SEK",
            line_item="Mobile subscription",
        )

        retrieval = retrieval_module.RetrievalService()
        results = [
            _ask(retrieval, "What document did I upload latest?"),
            _ask(retrieval, "Which document looks newest by document date, not upload time?"),
            _ask(retrieval, "Which suppliers or companies appear most often in my invoices?"),
            _ask(retrieval, "What invoice is most expensive?"),
            _ask(
                retrieval,
                "Make a table-like summary of invoice number, invoice date, "
                "supplier, total, and products where you can find them.",
            ),
            _ask(
                retrieval,
                "Can you search my invoices for bike-related purchases and "
                "separate products from service/fees?",
            ),
        ]
        writing_results = [
            _direct_reply(
                retrieval,
                "Draft a customer email using uploaded documents as source material "
                "with current status and next steps.",
            ),
            _direct_reply(
                retrieval,
                "Write an incident report based only on the uploaded documents. "
                "Include timeline, impact, and next actions.",
            ),
            _direct_reply(
                retrieval,
                "Create an action plan from the uploaded documents with task, owner, "
                "deadline, and priority.",
            ),
        ]
        follow_up_history = [
            ChatHistoryMessage(
                role="assistant",
                content=(
                    "The invoice with the largest total is "
                    f"{newer_by_date.original_name}."
                ),
                sources=[
                    ChatSource(
                        document_id=newer_by_date.id,
                        document_name=newer_by_date.original_name,
                        chunk_index=0,
                        score=1.0,
                        excerpt="Peak Velo invoice Bike tire total 120 EUR",
                    )
                ],
            )
        ]
        follow_up_invoice_date = service.summarize_document_invoice_facts(
            "And when was the invoice issued?",
            history=follow_up_history,
            is_admin=True,
        )
        _seed_invoice_fixture(
            service,
            original_name="20260506-082332-invoice-aurora-office.txt",
            company="Nordoffice AB",
            document_date="2026-04-18",
            total=6368.75,
            currency="SEK",
            line_item="ErgoChair Pro",
        )
        _seed_invoice_fixture(
            service,
            original_name="20260506-082332-invoice-peak-velo.txt",
            company="Peak Velo Ltd",
            document_date="2026-04-21",
            total=1942.5,
            currency="SEK",
            line_item="Carbon Brake Pads",
        )
        _seed_invoice_fixture(
            service,
            original_name="unrelated-invoice-large-library.pdf",
            company="Cable Warehouse",
            document_date="2026-04-23",
            total=9999,
            currency="SEK",
            line_item="Laddningskabel EW-EC3",
        )
        batch_product_inventory = service.summarize_document_products(
            "List the ordered products across invoice batch 20260506-082332.",
            is_admin=True,
        )
        generic_code_question = "Can you help me code a c# for loop that says something?"

    assert "Newer_upload_older_date.pdf" in results[0]["reply"]
    assert results[0]["sources"][0] == "Newer_upload_older_date.pdf"
    assert "Older_upload_newer_date.pdf" in results[1]["reply"]
    assert results[1]["sources"][0] == "Older_upload_newer_date.pdf"
    assert "company names" in results[2]["reply"]
    assert len(results[2]["sources"]) >= 2
    assert "most expensive invoice" in results[3]["reply"]
    assert "Newer_upload_older_date.pdf" in results[3]["reply"]
    assert len(results[3]["sources"]) >= 2
    assert "invoice-style facts in 2" in results[4]["reply"]
    assert "\n- " in results[4]["reply"]
    assert len(results[4]["sources"]) >= 2
    assert "product-style information" in results[5]["reply"]
    assert "\n- " in results[5]["reply"]
    assert len(results[5]["sources"]) >= 2
    assert writing_results[0] is None
    assert writing_results[1] is None
    assert writing_results[2] is not None
    assert "| Task | Owner | Deadline | Priority | Evidence |" in writing_results[2]
    assert "Unknown" in writing_results[2]
    assert follow_up_invoice_date
    assert newer_by_date.original_name in follow_up_invoice_date
    assert "invoice date 2026-01-10" in follow_up_invoice_date
    assert batch_product_inventory
    assert "ErgoChair Pro" in batch_product_inventory
    assert "Carbon Brake Pads" in batch_product_inventory
    assert "Laddningskabel" not in batch_product_inventory
    assert not service.is_document_risk_query("And when was the invoice issued?")
    assert service.is_document_invoice_facts_query("And when was the invoice issued?")
    assert not service.is_document_reference_query(generic_code_question)
    assert service.extract_requested_document_type(generic_code_question) is None

    print(
        json.dumps(
            {
                "metadata_results": results,
                "writing_results": writing_results,
                "follow_up_invoice_date": follow_up_invoice_date,
                "batch_product_inventory": batch_product_inventory,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.document_processing import DocumentProcessingService  # noqa: E402


def _assert_close(actual: float | None, expected: float) -> None:
    assert actual is not None
    assert abs(actual - expected) < 0.001


def test_tabular_invoice_items() -> None:
    service = DocumentProcessingService()
    text = """
    Invoice Number: INV-2026-0042
    Invoice Date: 2026-04-17
    Due Date: 2026-05-01

    Description Qty Unit Price Total
    Laptop Docking Station 2 129.50 SEK 259.00 SEK
    USB-C Cable 5 12.00 SEK 60.00 SEK

    Subtotal 319.00 SEK
    VAT 79.75 SEK
    Total 398.75 SEK
    """

    summary = service.extract_commercial_summary(
        text,
        "invoice-inv-2026-0042.pdf",
        "invoice",
    )

    assert summary is not None
    assert summary.invoice_number == "INV-2026-0042"
    assert summary.invoice_date == "2026-04-17"
    assert summary.due_date == "2026-05-01"
    assert summary.currency == "SEK"
    _assert_close(summary.total, 398.75)
    assert [item.description for item in summary.line_items] == [
        "Laptop Docking Station",
        "USB-C Cable",
    ]
    _assert_close(summary.line_items[0].quantity, 2)
    _assert_close(summary.line_items[0].unit_price, 129.5)
    _assert_close(summary.line_items[0].total, 259)


def test_keyed_invoice_item() -> None:
    service = DocumentProcessingService()
    text = """
    Faktura nr: FS-130-04
    Product: Installation support package Quantity: 3 Unit Price: 850 SEK Total: 2550 SEK
    Amount Due: 2550 SEK
    """

    summary = service.extract_commercial_summary(text, "FS 130_04_2026_nV68.pdf", "invoice")

    assert summary is not None
    assert summary.invoice_number == "FS-130-04"
    assert summary.line_items
    assert summary.line_items[0].description == "Installation support package"
    _assert_close(summary.line_items[0].quantity, 3)
    _assert_close(summary.line_items[0].unit_price, 850)
    _assert_close(summary.line_items[0].total, 2550)


if __name__ == "__main__":
    test_tabular_invoice_items()
    test_keyed_invoice_item()
    print("commercial extraction tests passed")

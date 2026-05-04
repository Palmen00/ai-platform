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


def test_multiline_invoice_table_ignores_bank_accounts() -> None:
    service = DocumentProcessingService()
    text = """
    Bank: BNP PARIBAS
    SWIFT / BIC: PPABPLPK
    account number PLN: 36 1600 1462 1892 0880 3000 0001
    account number EUR: PL79 1600 1462 1892 0880 3000 0003
    Invoice date 9.03.2026
    Faktura / Invoice FS 119/03/2026 original
    No. Kod kreskowy / Barcode Nazwa / Item name / Bicycle part
    Ilość / Quantity Cena netto / Unit net price Stawka VAT / Tax rate [%]
    1 5908374272694
    Cover AERO for Alugear
    chainrings R9200 12sp
    Black
    1 szt 40.60 0 40.60 0.00 40.60 8714.96.90.00 POLAND
    2 5908374273769
    Chainrings set 2-speed
    ALUGEAR AERO 54T-
    40T Round for 2x12 110
    BCD 4b Shimano
    Asymetric Road/Gravel
    Black
    1 szt 90.60 0 90.60 0.00 90.60 8714.96.90.00 POLAND
    5 B2B shipping 1 szt 15.00 0 15.00 0.00 15.00
    Total: 209.80 EUR
    """

    summary = service.extract_commercial_summary(text, "FS 119_03_2026_GnNJ.pdf", "invoice")

    assert summary is not None
    assert summary.invoice_date == "2026-03-09"
    _assert_close(summary.total, 209.8)
    assert summary.currency == "EUR"
    descriptions = [item.description for item in summary.line_items]
    assert descriptions == [
        "Cover AERO for Alugear chainrings R9200 12sp Black",
        "Chainrings set 2-speed ALUGEAR AERO 54T-40T Round for 2x12 110 BCD 4b Shimano Asymetric Road/Gravel Black",
        "B2B shipping",
    ]
    assert all("account number" not in description.lower() for description in descriptions)
    _assert_close(summary.line_items[0].quantity, 1)
    _assert_close(summary.line_items[0].unit_price, 40.6)
    _assert_close(summary.line_items[0].total, 40.6)
    _assert_close(summary.line_items[2].total, 15)


def test_swedish_invoice_rows_extract_products_and_quantities() -> None:
    service = DocumentProcessingService()
    text = """
    Artnr Benämning Lev ant Enhet À-pris Summa
    26241 U Gel (30g Carbs) Persika (12-pack) 1 st 168,00 168,00
    26277 U Gel (30g Carbs) Skogsbär + koffein (12-pack) 1 st 168,00 168,00
    3002 Frakt - DHL Paket 1 st 150,00 150,00
    Fakt. avgift Exkl. moms Moms Totalt ATT BETALA
    0,43 2 771,43 332,57 3 104,00 SEK 3 104,00
    """

    summary = service.extract_commercial_summary(text, "Faktura_166721.pdf", "invoice")

    assert summary is not None
    assert [item.description for item in summary.line_items] == [
        "26241 U Gel (30g Carbs) Persika (12-pack)",
        "26277 U Gel (30g Carbs) Skogsbär + koffein (12-pack)",
        "3002 Frakt - DHL Paket",
    ]
    _assert_close(summary.line_items[0].quantity, 1)
    _assert_close(summary.line_items[0].unit_price, 168)
    _assert_close(summary.line_items[2].total, 150)


def test_european_thousand_prices_and_ean_rows() -> None:
    service = DocumentProcessingService()
    text = """
    Number Product text Quantity EAN Unit price Price
    MAG-43 P715S Watt pedaler SPD-SL 1 6971606842605 2.127,44 2.127,44
    999 Fragt 1 95,00 95,00
    TotalDKK: 2.222,44
    """

    summary = service.extract_commercial_summary(text, "Faktura_927.pdf", "invoice")

    assert summary is not None
    assert summary.line_items[0].description == "MAG-43 P715S Watt pedaler SPD-SL"
    assert summary.line_items[0].sku == "6971606842605"
    _assert_close(summary.line_items[0].quantity, 1)
    _assert_close(summary.line_items[0].unit_price, 2127.44)
    _assert_close(summary.line_items[0].total, 2127.44)
    assert summary.line_items[1].description == "999 Fragt"


def test_position_invoice_rows_ignore_tariff_metadata() -> None:
    service = DocumentProcessingService()
    text = """
    Pos. No. Description Quantity VAT %
    Unit Price
    Excl. VAT Amount (EUR)
    001 20206417 Continental
    Grand Prix 5000 S TR 28" Transparent-Edition Folding
    Tyre
    1 44.53 44.53
    Tariff number: 40115000
    Country of origin: Deutschland
    003 20184400 Shimano
    XTR CN-M9100 12-speed Chain with Quick-Link
    1 36.97 36.97
    Tariff number: 73151110
    EU-IDM19 0% 251.94 0.00 251.94
    """

    summary = service.extract_commercial_summary(text, "Rechnung-58522131.pdf", "invoice")

    assert summary is not None
    assert [item.description for item in summary.line_items] == [
        'Continental Grand Prix 5000 S TR 28" Transparent-Edition Folding Tyre',
        "Shimano XTR CN-M9100 12-speed Chain with Quick-Link",
    ]
    assert all("tariff" not in item.description.lower() for item in summary.line_items)
    assert summary.line_items[0].sku == "20206417"
    _assert_close(summary.line_items[1].total, 36.97)


def test_stacked_invoice_item_block() -> None:
    service = DocumentProcessingService()
    text = """
    #
    ITEMS & DESCRIPTION
    QTY/HRS
    PRICE
    AMOUNT(GBP)
    1
    31.8mm round clamp adapters with 22.2mm
    extension clamps and 40mm stackers
    1
    GBP 206.67
    GBP 206.67
    INVOICE
    Invoice No#
    7441
    """

    summary = service.extract_commercial_summary(text, "Invoice - 7441.pdf", "invoice")

    assert summary is not None
    assert summary.line_items[0].description == (
        "31.8mm round clamp adapters with 22.2mm extension clamps and 40mm stackers"
    )
    _assert_close(summary.line_items[0].quantity, 1)
    _assert_close(summary.line_items[0].unit_price, 206.67)
    assert summary.line_items[0].currency == "GBP"


def test_pipe_invoice_rows_keep_service_product_name() -> None:
    service = DocumentProcessingService()
    text = """
    Invoice No: PV-2026-118
    Invoice Date: 2026-04-21
    Due Date: 2026-05-05
    Description | SKU | Qty | Unit Price | Line Total
    Carbon Brake Pads | BRK-CARBON-22 | 3 | 249.50 | 748.50
    Workshop Tune-up | SERVICE-TUNE | 1 | 805.50 | 805.50
    Total: 1942.50 SEK
    """

    summary = service.extract_commercial_summary(text, "invoice-peak-velo.txt", "invoice")

    assert summary is not None
    assert [item.description for item in summary.line_items] == [
        "Carbon Brake Pads",
        "Workshop Tune-up",
    ]
    assert summary.line_items[1].sku == "SERVICE-TUNE"
    _assert_close(summary.line_items[1].quantity, 1)
    _assert_close(summary.line_items[1].total, 805.5)


if __name__ == "__main__":
    test_tabular_invoice_items()
    test_keyed_invoice_item()
    test_multiline_invoice_table_ignores_bank_accounts()
    test_swedish_invoice_rows_extract_products_and_quantities()
    test_european_thousand_prices_and_ean_rows()
    test_position_invoice_rows_ignore_tariff_metadata()
    test_stacked_invoice_item_block()
    test_pipe_invoice_rows_keep_service_product_name()
    print("commercial extraction tests passed")

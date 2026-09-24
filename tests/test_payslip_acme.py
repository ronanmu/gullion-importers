from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from gullion_importers.importers.payslip import PayslipImporter

ACME_SAMPLE = Path(__file__).parent / "fixtures" / "payslip" / "acme-payslip-sample.pdf"


@pytest.fixture
def importer():
    return PayslipImporter(
        account="Assets:Bank",
        line_item_accounts={
            r"^Salary$": "Income:Acme:Salary",
            r"^Tax$": "Expenses:Tax",
            r"^PRSI$": "Expenses:PRSI",
            r"^AVC$": "Expenses:AVC",
        },
        name="Acme Payslip",
        currency="EUR",
        net_amount_pattern=r"NET PAY",
        date_pattern=(r"Date:?", "%d %B %Y"),
    )


def test_sample_payslip(importer):

    entries = importer.extract(ACME_SAMPLE)
    postings = {posting.account: posting.units.number for posting in entries[0].postings}

    assert postings["Income:Acme:Salary"] == Decimal("-9500.25")
    assert postings["Expenses:Tax"] == Decimal("1500.21")
    assert postings["Expenses:PRSI"] == Decimal("356.25")
    assert postings["Assets:Bank"] == Decimal("5603.39")

    assert entries[0].postings[-1].units.currency == "EUR"


def test_identify_sample_payslip(importer):

    assert importer.identify(ACME_SAMPLE)


def test_parse_date_sample_payslip(importer):
    parsed_date = importer.date(ACME_SAMPLE)

    assert parsed_date == date(2025, 9, 30)

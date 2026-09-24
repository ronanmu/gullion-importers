from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from gullion_importers.importers.payslip import PayslipImporter

NLC_SAMPLE = Path(__file__).parent / "fixtures" / "payslip" / "nlc-payslip-sample.pdf"


@pytest.fixture
def importer():
    return PayslipImporter(
        account="Assets:Bank",
        line_item_accounts={
            (r"Payments", 1): "Income:NLC:Salary",
            r"Tax\b": "Expenses:Tax",
            r"NI - A": "Expenses:NatIns",
        },
        name="North Lanarkshire Council Payslip",
        currency="GBP",
        net_amount_pattern=(r"Payments", 3),
        date_pattern=((r"Pay Date:", 1), "%d/%m/%Y"),
    )


def test_sample_payslip(importer):

    entries = importer.extract(NLC_SAMPLE)
    postings = {posting.account: posting.units.number for posting in entries[0].postings}

    assert postings["Income:NLC:Salary"] == Decimal("-1516.00")
    assert postings["Expenses:Tax"] == Decimal("102.46")
    assert postings["Expenses:NatIns"] == Decimal("104.16")
    assert postings["Assets:Bank"] == Decimal("1121.56")

    assert entries[0].postings[-1].units.currency == "GBP"


def test_identify_sample_payslip(importer):

    assert importer.identify(NLC_SAMPLE)


def test_parse_date_sample_payslip(importer):
    parsed_date = importer.date(NLC_SAMPLE)

    assert parsed_date == date(2019, 2, 12)

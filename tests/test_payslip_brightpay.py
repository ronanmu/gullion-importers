from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from gullion_importers.importers.payslip import PayslipImporter

BRIGHTPAY_SAMPLE = Path(__file__).parent / "fixtures" / "payslip" / "brightpay-payslip-sample.pdf"


@pytest.fixture
def importer():
    return PayslipImporter(
        account="Assets:Bank",
        line_item_accounts={
            r"Monthly pay": "Income:Sample:Salary",
            r"^Tax": "Expenses:Tax",
            r"National Insurance": "Expenses:NatIns",
            r"NOW: Pensions": "Expenses:AVC",
        },
        name="Acme Payslip",
        currency="GBP",
        net_amount_pattern=r"Net pay",
        date_pattern=(r"Month Ending:?", "%d %B %Y"),
    )


def test_sample_payslip(importer):

    entries = importer.extract(BRIGHTPAY_SAMPLE)
    postings = {posting.account: posting.units.number for posting in entries[0].postings}

    assert postings["Income:Sample:Salary"] == Decimal("-11583.33")
    assert postings["Expenses:Tax"] == Decimal("3749.85")
    assert postings["Expenses:NatIns"] == Decimal("504.23")
    assert postings["Expenses:AVC"] == Decimal("24.37")
    assert postings["Assets:Bank"] == Decimal("7329.25")

    assert entries[0].postings[-1].units.currency == "GBP"


def test_identify_sample_payslip(importer):

    assert importer.identify(BRIGHTPAY_SAMPLE)


def test_parse_date_sample_payslip(importer):
    parsed_date = importer.date(BRIGHTPAY_SAMPLE)

    assert parsed_date == date(2015, 5, 31)

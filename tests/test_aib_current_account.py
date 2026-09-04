from decimal import Decimal
from pathlib import Path

import pytest
from beancount.core import data

from gullion_importers.importers.aib import (
    AIBCurrentAccountImporter,
)

FIXTURES = Path(__file__).parent / "fixtures" / "aib"
AIB_FIXTURE = FIXTURES / "current_account.csv"


def make_importer():
    return AIBCurrentAccountImporter(
        account="Assets:Bank:AIB:Current",
    )


@pytest.fixture
def importer():
    return make_importer()


@pytest.fixture
def transactions(importer):
    entries = importer.extract(
        str(AIB_FIXTURE),
        [],
    )

    return [entry for entry in entries if isinstance(entry, data.Transaction)]


def test_identify_aib_csv(importer):
    assert importer.identify(str(AIB_FIXTURE))


def test_rejects_non_aib_csv(importer, tmp_path):
    csv_file = tmp_path / "other.csv"

    csv_file.write_text(
        "date,description,amount\n2023-11-01,Tesco,10.00\n",
        encoding="utf-8",
    )

    assert not importer.identify(str(csv_file))


def test_extracts_expected_number_of_transactions(transactions):
    assert len(transactions) == 4


def test_contactless_transaction(transactions):
    tx = transactions[0]

    assert tx.date.isoformat() == "2023-11-03"
    assert tx.narration == "VDC-SUMUP *WEST S"

    assert len(tx.postings) == 1

    posting = tx.postings[0]

    assert posting.account == "Assets:Bank:AIB:Current"
    assert posting.units.number == Decimal("-48.30")
    assert posting.units.currency == "EUR"

    assert tx.meta["transaction-type"] == "contactless"


def test_point_of_sale_transaction(transactions):
    tx = transactions[1]

    assert tx.date.isoformat() == "2023-11-07"
    assert tx.narration == "VDP-IONITY GmbH Ir"

    assert tx.meta["transaction-type"] == "point-of-sale"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-19.44")
    assert posting.units.currency == "EUR"


def test_transaction_type_falls_back_to_csv_value(transactions):
    tx = transactions[2]

    assert tx.narration == "TRANSFER RECEIVED"

    # Assumes your importer lowercases the fallback CSV value.
    assert tx.meta["transaction-type"] == "credit"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("500.00")
    assert posting.units.currency == "EUR"


def test_same_local_currency_not_added_to_metadata(transactions):
    tx = transactions[0]

    assert "local-amount" not in tx.meta
    assert "local-currency" not in tx.meta


def test_foreign_currency_added_to_metadata(transactions):
    tx = transactions[3]

    assert tx.narration == "UK MERCHANT"

    posting = tx.postings[0]

    # The AIB account itself is still denominated in EUR.
    assert posting.units.number == Decimal("-120.00")
    assert posting.units.currency == "EUR"

    # Original transaction currency is preserved as metadata.
    assert tx.meta["local-amount"] == Decimal("100.00")
    assert tx.meta["local-currency"] == "GBP"


def test_debit_is_negative(transactions):
    tx = transactions[0]

    assert tx.postings[0].units.number < 0


def test_credit_is_positive(transactions):
    tx = transactions[2]

    assert tx.postings[0].units.number > 0

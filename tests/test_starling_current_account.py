from decimal import Decimal
from pathlib import Path

import pytest
from beancount.core import data

from gullion_importers.importers.common.metadata import CATEGORY, NOTES, TRANSACTION_TYPE
from gullion_importers.importers.starling import StarlingCurrentAccountImporter

FIXTURES = Path(__file__).parent / "fixtures" / "starling"

STARLING_GBP_FIXTURE = FIXTURES / "current_account_gbp.csv"
STARLING_EUR_FIXTURE = FIXTURES / "current_account_eur.csv"
INVALID_FIXTURE = FIXTURES / "not_starling.csv"


def extract_transactions(importer, fixture_path):
    entries = importer.extract(
        str(fixture_path),
        [],
    )

    return [entry for entry in entries if isinstance(entry, data.Transaction)]


@pytest.fixture
def gbp_importer():
    return StarlingCurrentAccountImporter(account="Assets:Bank:Starling:GBP", currency="GBP")


@pytest.fixture
def eur_importer():
    return StarlingCurrentAccountImporter(account="Assets:Bank:Starling:EUR", currency="EUR")


@pytest.fixture
def gbp_transactions(gbp_importer):
    return extract_transactions(
        gbp_importer,
        STARLING_GBP_FIXTURE,
    )


@pytest.fixture
def eur_transactions(eur_importer):
    return extract_transactions(
        eur_importer,
        STARLING_EUR_FIXTURE,
    )


def test_gbp_importer_identifies_gbp_csv(gbp_importer):
    assert gbp_importer.identify(str(STARLING_GBP_FIXTURE))


def test_eur_importer_identifies_eur_csv(eur_importer):
    assert eur_importer.identify(str(STARLING_EUR_FIXTURE))


def test_gbp_importer_rejects_eur_csv(gbp_importer):
    assert not gbp_importer.identify(str(STARLING_EUR_FIXTURE))


def test_eur_importer_rejects_gbp_csv(eur_importer):
    assert not eur_importer.identify(str(STARLING_GBP_FIXTURE))


def test_importers_reject_invalid_csv(
    gbp_importer,
    eur_importer,
):
    assert not gbp_importer.identify(str(INVALID_FIXTURE))

    assert not eur_importer.identify(str(INVALID_FIXTURE))


def test_gbp_expected_transaction_count(gbp_transactions):
    assert len(gbp_transactions) == 8


def test_eur_expected_transaction_count(eur_transactions):
    assert len(eur_transactions) == 8


def test_gbp_interest_transaction(gbp_transactions):
    tx = gbp_transactions[0]

    assert tx.date.isoformat() == "2020-01-01"
    assert tx.payee == "Starling Bank"
    assert tx.narration == "December Interest Earned"

    posting = tx.postings[0]

    assert posting.account == "Assets:Bank:Starling:GBP"
    assert posting.units.number == Decimal("0.05")
    assert posting.units.currency == "GBP"

    assert tx.meta[TRANSACTION_TYPE] == "deposit-interest"

    assert tx.meta[CATEGORY] == "income"


def test_gbp_currency_transfer(gbp_transactions):
    tx = gbp_transactions[1]

    assert tx.date.isoformat() == "2020-01-28"
    assert tx.payee == "Ronan Murray"
    assert tx.narration == "Transfer"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-25.00")
    assert posting.units.currency == "GBP"

    assert tx.meta[TRANSACTION_TYPE] == "currency-transfer"

    assert tx.meta[CATEGORY] == "personal_transfers"


def test_gbp_faster_payment(gbp_transactions):
    tx = gbp_transactions[3]

    assert tx.payee == "Good Friend"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("2000.00")
    assert posting.units.currency == "GBP"

    assert tx.meta[TRANSACTION_TYPE] == "faster-payment"


def test_gbp_online_payment(gbp_transactions):
    tx = gbp_transactions[4]

    assert tx.payee == "Curve"
    assert tx.narration == "CRV*SUPERVALU HILL STR London        GBR"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-7.45")
    assert posting.units.currency == "GBP"

    assert tx.meta[TRANSACTION_TYPE] == "online-payment"

    assert tx.meta[CATEGORY] == "general"


def test_gbp_contactless_transaction(gbp_transactions):
    tx = gbp_transactions[5]

    assert tx.payee == "Tesco Stores"
    assert tx.narration == "TESCO STORE 1234"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-52.30")

    assert tx.meta[TRANSACTION_TYPE] == "contactless"

    assert tx.meta[CATEGORY] == "groceries"


def test_starling_notes_are_preserved(gbp_transactions):
    tx = gbp_transactions[6]

    assert tx.payee == "Amazon"
    assert tx.meta[NOTES] == "Household item"


def test_blank_notes_not_added(gbp_transactions):
    tx = gbp_transactions[0]

    assert "notes" not in tx.meta


def test_debit_is_negative(gbp_transactions):
    tx = gbp_transactions[4]

    assert tx.postings[0].units.number < 0


def test_credit_is_positive(gbp_transactions):
    tx = gbp_transactions[3]

    assert tx.postings[0].units.number > 0


def test_eur_currency_transfer(eur_transactions):
    tx = eur_transactions[0]

    assert tx.date.isoformat() == "2020-01-28"
    assert tx.payee == "Fred Smith"
    assert tx.narration == "Transfer"

    posting = tx.postings[0]

    assert posting.account == "Assets:Bank:Starling:EUR"
    assert posting.units.number == Decimal("29.42")
    assert posting.units.currency == "EUR"

    assert tx.meta[TRANSACTION_TYPE] == "currency-transfer"

    assert tx.meta[CATEGORY] == "income"


def test_eur_sepa_incoming_payment(eur_transactions):
    tx = eur_transactions[2]

    assert tx.payee == "Fred Smith"
    assert tx.narration == "Test test"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("5.00")
    assert posting.units.currency == "EUR"

    assert tx.meta[TRANSACTION_TYPE] == "sepa-payment"


def test_eur_large_incoming_payment(eur_transactions):
    tx = eur_transactions[3]

    posting = tx.postings[0]

    assert posting.units.number == Decimal("40200.00")
    assert posting.units.currency == "EUR"


def test_eur_outgoing_payment(eur_transactions):
    tx = eur_transactions[4]

    assert tx.payee == "Fred Smith"

    # Depending on how csvbase handles whitespace,
    # this may be trimmed automatically.
    assert tx.narration.strip() == "For new house"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-20000.00")
    assert posting.units.currency == "EUR"

    assert tx.meta[TRANSACTION_TYPE] == "sepa-payment"

    assert tx.meta[CATEGORY] == "payments"


def test_eur_interest_transaction(eur_transactions):
    tx = eur_transactions[6]

    assert tx.payee == "Starling Bank"
    assert tx.narration == "February Interest Earned"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("0.12")
    assert posting.units.currency == "EUR"

    assert tx.meta[TRANSACTION_TYPE] == "deposit-interest"


def test_eur_notes_are_preserved(eur_transactions):
    tx = eur_transactions[7]

    assert tx.payee == "Example Merchant"
    assert tx.meta[NOTES] == "Test note"


@pytest.mark.parametrize(
    ("transaction_index", "expected_type"),
    [
        (0, "deposit-interest"),
        (1, "currency-transfer"),
        (2, "deposit-interest"),
        (3, "faster-payment"),
        (4, "online-payment"),
        (5, "contactless"),
        (6, "online-payment"),
        (7, "faster-payment"),
    ],
)
def test_gbp_transaction_type_normalisation(
    gbp_transactions,
    transaction_index,
    expected_type,
):
    tx = gbp_transactions[transaction_index]

    assert tx.meta[TRANSACTION_TYPE] == expected_type


def test_all_gbp_transactions_use_gbp(gbp_transactions):
    for tx in gbp_transactions:
        assert len(tx.postings) == 1
        assert tx.postings[0].units.currency == "GBP"


def test_all_eur_transactions_use_eur(eur_transactions):
    for tx in eur_transactions:
        assert len(tx.postings) == 1
        assert tx.postings[0].units.currency == "EUR"

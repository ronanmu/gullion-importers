from decimal import Decimal
from pathlib import Path

import pytest
from beancount.core import data

from gullion_beancount_importers.revolut.current_account import (
    RevolutCurrentAccountImporter,
)

FIXTURES = Path(__file__).parent / "fixtures" / "revolut"

EUR_FIXTURE = FIXTURES / "current_account_eur.csv"
GBP_FIXTURE = FIXTURES / "current_account_gbp.csv"
AED_FIXTURE = FIXTURES / "current_account_aed.csv"


def extract_transactions(importer, fixture_path):
    entries = importer.extract(
        str(fixture_path),
        [],
    )

    return [entry for entry in entries if isinstance(entry, data.Transaction)]


@pytest.fixture
def eur_importer():
    return RevolutCurrentAccountImporter(
        account="Assets:Bank:Revolut:EUR",
        currency="EUR",
    )


@pytest.fixture
def gbp_importer():
    return RevolutCurrentAccountImporter(
        account="Assets:Bank:Revolut:GBP",
        currency="GBP",
    )


@pytest.fixture
def aed_importer():
    return RevolutCurrentAccountImporter(
        account="Assets:Bank:Revolut:AED",
        currency="AED",
    )


@pytest.fixture
def eur_transactions(eur_importer):
    return extract_transactions(
        eur_importer,
        EUR_FIXTURE,
    )


@pytest.fixture
def gbp_transactions(gbp_importer):
    return extract_transactions(
        gbp_importer,
        GBP_FIXTURE,
    )


@pytest.fixture
def aed_transactions(aed_importer):
    return extract_transactions(
        aed_importer,
        AED_FIXTURE,
    )


def test_eur_importer_identifies_eur_csv(eur_importer):
    assert eur_importer.identify(str(EUR_FIXTURE))


def test_gbp_importer_identifies_gbp_csv(gbp_importer):
    assert gbp_importer.identify(str(GBP_FIXTURE))


def test_aed_importer_identifies_aed_csv(aed_importer):
    assert aed_importer.identify(str(AED_FIXTURE))


def test_expected_eur_transaction_count(eur_transactions):
    assert len(eur_transactions) == 7


def test_expected_gbp_transaction_count(gbp_transactions):
    assert len(gbp_transactions) == 6


def test_expected_aed_transaction_count(aed_transactions):
    assert len(aed_transactions) == 6


def test_reverted_eur_transactions_are_removed(eur_transactions):
    narrations = {tx.narration for tx in eur_transactions}

    assert "creditexpert.co.uk" not in narrations
    assert "Top-up by *3633" in narrations


def test_reverted_gbp_transaction_is_removed(gbp_transactions):
    narrations = {tx.narration for tx in gbp_transactions}

    assert "Amazon" not in narrations


def test_reverted_aed_transaction_is_removed(aed_transactions):
    narrations = {tx.narration for tx in aed_transactions}

    assert "Restaurant Dubai" not in narrations


def test_eur_topup(eur_transactions):
    tx = eur_transactions[0]

    assert tx.date.isoformat() == "2016-06-18"
    assert tx.narration == "Top-up by *3633"

    posting = tx.postings[0]

    assert posting.account == "Assets:Bank:Revolut:EUR"
    assert posting.units.number == Decimal("250.00")
    assert posting.units.currency == "EUR"

    assert tx.meta["transaction-type"] == "topup"


def test_eur_card_payment(eur_transactions):
    tx = eur_transactions[1]

    assert tx.date.isoformat() == "2016-07-04"
    assert tx.narration == "Tesco Stores 3677 Saca"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-5.74")
    assert posting.units.currency == "EUR"

    assert tx.meta["transaction-type"] == "card-payment"


def test_eur_exchange(eur_transactions):
    tx = eur_transactions[2]

    assert tx.narration == "Exchanged to GBP"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-100.45")
    assert posting.units.currency == "EUR"

    assert tx.meta["transaction-type"] == "exchange"


def test_eur_transfer(eur_transactions):
    tx = eur_transactions[5]

    assert tx.narration == "To Example Recipient"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-500.00")
    assert posting.units.currency == "EUR"

    assert tx.meta["transaction-type"] == "transfer"


def test_non_zero_fee_is_preserved(eur_transactions):
    tx = eur_transactions[6]

    assert tx.meta["fee"] == Decimal("0.50")


def test_zero_fee_is_not_added(eur_transactions):
    tx = eur_transactions[0]

    assert "fee" not in tx.meta


def test_gbp_exchange(gbp_transactions):
    tx = gbp_transactions[0]

    assert tx.narration == "Exchanged from EUR"

    posting = tx.postings[0]

    assert posting.account == "Assets:Bank:Revolut:GBP"
    assert posting.units.number == Decimal("85.20")
    assert posting.units.currency == "GBP"

    assert tx.meta["transaction-type"] == "exchange"


def test_gbp_cash_withdrawal(gbp_transactions):
    tx = gbp_transactions[4]

    assert tx.narration == "CASH WITHDRAWAL"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-50.00")
    assert posting.units.currency == "GBP"

    assert tx.meta["transaction-type"] == "cash-withdrawal"

    assert tx.meta["fee"] == Decimal("1.00")


def test_gbp_bank_transfer(gbp_transactions):
    tx = gbp_transactions[3]

    assert tx.narration == "From Example Account"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("200.00")
    assert posting.units.currency == "GBP"

    assert tx.meta["transaction-type"] == "bank-transfer"


def test_aed_exchange(aed_transactions):
    tx = aed_transactions[0]

    assert tx.narration == "Exchanged from GBP"

    posting = tx.postings[0]

    assert posting.account == "Assets:Bank:Revolut:AED"
    assert posting.units.number == Decimal("500.00")
    assert posting.units.currency == "AED"

    assert tx.meta["transaction-type"] == "exchange"


def test_aed_card_payment(aed_transactions):
    tx = aed_transactions[1]

    assert tx.narration == "Carrefour Dubai"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-84.75")
    assert posting.units.currency == "AED"

    assert tx.meta["transaction-type"] == "card-payment"


def test_aed_cash_withdrawal(aed_transactions):
    tx = aed_transactions[3]

    assert tx.narration == "ATM Withdrawal"

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-100.00")
    assert posting.units.currency == "AED"

    assert tx.meta["fee"] == Decimal("2.00")


@pytest.mark.parametrize(
    (
        "fixture_path",
        "currency",
        "account",
        "expected_count",
    ),
    [
        (
            EUR_FIXTURE,
            "EUR",
            "Assets:Bank:Revolut:EUR",
            7,
        ),
        (
            GBP_FIXTURE,
            "GBP",
            "Assets:Bank:Revolut:GBP",
            6,
        ),
        (
            AED_FIXTURE,
            "AED",
            "Assets:Bank:Revolut:AED",
            6,
        ),
    ],
)
def test_all_transactions_have_expected_currency_and_account(
    fixture_path,
    currency,
    account,
    expected_count,
):
    importer = RevolutCurrentAccountImporter(
        account=account,
        currency=currency,
    )

    transactions = extract_transactions(
        importer,
        fixture_path,
    )

    assert len(transactions) == expected_count

    for tx in transactions:
        assert len(tx.postings) == 1
        assert tx.postings[0].account == account
        assert tx.postings[0].units.currency == currency


@pytest.mark.parametrize(
    (
        "transaction_index",
        "expected_type",
    ),
    [
        (0, "topup"),
        (1, "card-payment"),
        (2, "exchange"),
        (3, "card-payment"),
        (4, "topup"),
        (5, "transfer"),
        (6, "transfer"),
    ],
)
def test_eur_transaction_type_normalisation(
    eur_transactions,
    transaction_index,
    expected_type,
):
    tx = eur_transactions[transaction_index]

    assert tx.meta["transaction-type"] == expected_type

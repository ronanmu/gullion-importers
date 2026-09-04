from decimal import Decimal
from pathlib import Path

import pytest
from beancount.core import data

from gullion_importers.importers.barclaycard import (
    BarclaycardImporter,
)

FIXTURES = Path(__file__).parent / "fixtures" / "barclaycard"

BARCLAYCARD_FIXTURE = FIXTURES / "transactions.csv"
INVALID_FIXTURE = FIXTURES / "not_barclaycard.csv"


@pytest.fixture
def importer():
    return BarclaycardImporter(
        account="Liabilities:CreditCard:Barclaycard",
        currency="GBP",
    )


@pytest.fixture
def transactions(importer):
    entries = importer.extract(
        str(BARCLAYCARD_FIXTURE),
        [],
    )

    return [entry for entry in entries if isinstance(entry, data.Transaction)]


def transaction_by_narration(transactions, narration):
    return next(tx for tx in transactions if tx.narration == narration)


def test_identifies_barclaycard_csv(importer):
    assert importer.identify(str(BARCLAYCARD_FIXTURE))


def test_rejects_non_barclaycard_csv(importer):
    assert not importer.identify(str(INVALID_FIXTURE))


def test_expected_transaction_count(transactions):
    assert len(transactions) == 6


def test_transaction_date_is_parsed(transactions):
    tx = transaction_by_narration(
        transactions,
        "NORTHSIDE PHARMACY, EXAMPLETOWN20.87 POUND STERLING UNITED KINGDOM",
    )

    assert tx.date.isoformat() == "2024-11-11"


def test_purchase_amount_is_negative_liability(transactions):
    tx = transaction_by_narration(
        transactions,
        "NORTHSIDE PHARMACY, EXAMPLETOWN20.87 POUND STERLING UNITED KINGDOM",
    )

    posting = tx.postings[0]

    assert posting.account == "Liabilities:CreditCard:Barclaycard"
    assert posting.units.number == Decimal("-20.87")
    assert posting.units.currency == "GBP"


def test_entertainment_purchase(transactions):
    tx = transaction_by_narration(
        transactions,
        "PIXEL CINEMA, EXAMPLETOWN8.30 POUND STERLING UNITED KINGDOM",
    )

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-8.30")
    assert posting.units.currency == "GBP"

    assert tx.meta["category"] == "entertainment"


def test_grocery_purchase(transactions):
    tx = transaction_by_narration(
        transactions,
        "ACME SUPERMARKET LTD, EXAMPLETOWN",
    )

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-84.10")
    assert posting.units.currency == "GBP"

    assert tx.meta["category"] == "groceries"


def test_direct_debit_payment_is_positive_liability(
    transactions,
):
    tx = transaction_by_narration(
        transactions,
        "Payment By Direct Debit",
    )

    posting = tx.postings[0]

    assert posting.account == "Liabilities:CreditCard:Barclaycard"
    assert posting.units.number == Decimal("262.88")
    assert posting.units.currency == "GBP"


def test_direct_debit_payment_has_no_category(
    transactions,
):
    tx = transaction_by_narration(
        transactions,
        "Payment By Direct Debit",
    )

    assert "category" not in tx.meta


def test_fuel_purchase(transactions):
    tx = transaction_by_narration(
        transactions,
        "BLUEBIRD FUEL STATION, SAMPLE CITY",
    )

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-62.45")
    assert tx.meta["category"] == "automotive"


def test_restaurant_purchase(transactions):
    tx = transaction_by_narration(
        transactions,
        "HARBOR CAFE, SAMPLE CITY",
    )

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-14.75")
    assert tx.meta["category"] == "restaurants"


def test_card_member_is_not_exposed_in_metadata(
    transactions,
):
    for tx in transactions:
        assert "card-member" not in tx.meta
        assert "card_member" not in tx.meta


def test_all_transactions_use_expected_account(
    transactions,
):
    for tx in transactions:
        assert len(tx.postings) == 1

        posting = tx.postings[0]

        assert posting.account == "Liabilities:CreditCard:Barclaycard"


def test_all_transactions_use_gbp(transactions):
    for tx in transactions:
        assert tx.postings[0].units.currency == "GBP"


def test_purchase_transactions_are_negative(
    transactions,
):
    purchases = [tx for tx in transactions if tx.narration != "Payment By Direct Debit"]

    for tx in purchases:
        assert tx.postings[0].units.number < 0


def test_payment_transaction_is_positive(
    transactions,
):
    tx = transaction_by_narration(
        transactions,
        "Payment By Direct Debit",
    )

    assert tx.postings[0].units.number > 0

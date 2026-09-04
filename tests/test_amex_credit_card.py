from decimal import Decimal
from pathlib import Path

import pytest
from beancount.core import data

from gullion_importers.importers.amex import (
    AmericanExpressImporter,
)
from gullion_importers.importers.common.metadata import (
    CATEGORY,
    COUNTRY,
    FX_RATE,
    LOCAL_AMOUNT,
    LOCAL_CURRENCY,
    STATEMENT_DESCRIPTION,
)

FIXTURES = Path(__file__).parent / "fixtures" / "amex"

AMEX_FIXTURE = FIXTURES / "credit_card.csv"
INVALID_FIXTURE = FIXTURES / "not_amex.csv"


def extract_transactions(importer, fixture_path):
    entries = importer.extract(
        str(fixture_path),
        [],
    )

    return [entry for entry in entries if isinstance(entry, data.Transaction)]


@pytest.fixture
def importer():
    return AmericanExpressImporter(
        account="Liabilities:CreditCard:Amex",
        currency="GBP",
    )


@pytest.fixture
def transactions(importer):
    return extract_transactions(
        importer,
        AMEX_FIXTURE,
    )


def transaction_by_narration(transactions, narration):
    return next(tx for tx in transactions if tx.narration == narration)


def test_identifies_amex_csv(importer):
    assert importer.identify(str(AMEX_FIXTURE))


def test_rejects_non_amex_csv(importer):
    assert not importer.identify(str(INVALID_FIXTURE))


def test_expected_transaction_count(transactions):
    assert len(transactions) == 10


def test_purchase_amount_is_inverted(transactions):

    purchase = next(
        candidate
        for candidate in transactions
        if candidate.narration == "NORTHSIDE MARKET 0042"
        and candidate.postings[0].units.number == Decimal("-84.27")
    )

    posting = purchase.postings[0]

    assert posting.account == "Liabilities:CreditCard:Amex"
    assert posting.units.number == Decimal("-84.27")
    assert posting.units.currency == "GBP"


def test_refund_amount_is_inverted(transactions):
    refund = next(
        tx
        for tx in transactions
        if tx.narration == "NORTHSIDE MARKET 0042"
        and tx.postings[0].units.number == Decimal("17.00")
    )

    assert refund.postings[0].units.currency == "GBP"


def test_transaction_date(transactions):
    tx = transaction_by_narration(
        transactions,
        "PIXEL BOOKSHOP ONLINE",
    )

    assert tx.date.isoformat() == "2025-12-30"


def test_reference_is_preserved(transactions):
    tx = transaction_by_narration(
        transactions,
        "CITY MUSEUM MEMBERSHIP",
    )

    assert tx.meta["reference"] == "AT900000000000000000003"


def test_reference_leading_quote_is_removed(transactions):
    tx = transaction_by_narration(
        transactions,
        "STREAMBOX PREMIUM",
    )

    reference = tx.meta["reference"]

    assert reference == "AT900000000000000000004"
    assert not reference.startswith("'")


def test_category_is_preserved(transactions):
    tx = transaction_by_narration(
        transactions,
        "NORTHSIDE MARKET 0042",
    )

    assert tx.meta[CATEGORY] == "General Purchases-Groceries"


def test_country_is_preserved(transactions):
    tx = transaction_by_narration(
        transactions,
        "GLOBAL NEWS SERVICE",
    )

    assert tx.meta[COUNTRY] == "UNITED STATES"


def test_identical_statement_description_is_not_added(
    transactions,
):
    tx = transaction_by_narration(
        transactions,
        "BLUEBIRD TAXI SERVICE",
    )

    assert "statement-description" not in tx.meta


def test_different_statement_description_is_added(
    transactions,
):
    tx = transaction_by_narration(
        transactions,
        "HARBOR COFFEE SHOP",
    )

    assert tx.meta[STATEMENT_DESCRIPTION] == "HARBOR COFFEE COMPANY"


def test_foreign_spend_amount_is_parsed(transactions):
    tx = transaction_by_narration(
        transactions,
        "GLOBAL NEWS SERVICE",
    )

    assert tx.meta[LOCAL_AMOUNT] == Decimal("147.99")


def test_foreign_currency_name_is_preserved(transactions):
    tx = transaction_by_narration(
        transactions,
        "GLOBAL NEWS SERVICE",
    )

    assert tx.meta[LOCAL_CURRENCY] == "UNITED STATES DOLLAR"


def test_foreign_commission_is_parsed(transactions):
    tx = transaction_by_narration(
        transactions,
        "GLOBAL NEWS SERVICE",
    )

    assert tx.meta["commission"] == Decimal("3.28")


def test_exchange_rate_is_parsed(transactions):
    tx = transaction_by_narration(
        transactions,
        "GLOBAL NEWS SERVICE",
    )

    assert tx.meta[FX_RATE] == Decimal("1.3489")


def test_domestic_transaction_has_no_fx_metadata(
    transactions,
):
    tx = transaction_by_narration(
        transactions,
        "ACME ELECTRONICS",
    )

    assert "foreign-amount" not in tx.meta
    assert "foreign-currency" not in tx.meta
    assert "commission" not in tx.meta
    assert "exchange-rate" not in tx.meta


def test_card_member_is_not_exposed_in_metadata(
    transactions,
):
    tx = transactions[0]

    assert "amex_card_member" not in tx.meta
    assert "card_member" not in tx.meta


def test_account_number_is_not_exposed_in_metadata(
    transactions,
):
    tx = transactions[0]

    assert "amex_account" not in tx.meta
    assert "account_number" not in tx.meta


def test_address_is_not_exposed_in_metadata(
    transactions,
):
    tx = transactions[0]

    assert "amex_address" not in tx.meta
    assert "amex_town" not in tx.meta
    assert "amex_postcode" not in tx.meta


def test_all_transactions_use_amex_account(
    transactions,
):
    for tx in transactions:
        assert len(tx.postings) == 1

        posting = tx.postings[0]

        assert posting.account == "Liabilities:CreditCard:Amex"


def test_all_transactions_use_gbp(transactions):
    for tx in transactions:
        assert tx.postings[0].units.currency == "GBP"


def test_normal_purchase_is_negative(transactions):
    tx = transaction_by_narration(
        transactions,
        "ACME ELECTRONICS",
    )

    assert tx.postings[0].units.number == Decimal("-249.95")


def test_refund_is_positive(transactions):
    refund = next(
        tx
        for tx in transactions
        if tx.narration == "NORTHSIDE MARKET 0042" and tx.postings[0].units.number > 0
    )

    assert refund.postings[0].units.number == Decimal("17.00")

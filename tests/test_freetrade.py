from decimal import Decimal
from pathlib import Path

import pytest
from beancount.core import data

from gullion_importers.importers.freetrade import FreetradeImporter

FIXTURES = Path(__file__).parent / "fixtures" / "freetrade"

FREETRADE_FIXTURE = FIXTURES / "activity.csv"


@pytest.fixture
def importer():
    return FreetradeImporter(
        account_root="Assets:Investments:Freetrade",
        cash_account="Assets:Investments:Freetrade:Cash",
        dividend_income_account="Income:Investments:Dividends",
        interest_income_account="Income:Investments:Interest",
        stamp_duty_account="Expenses:Investment:StampDuty",
        fx_fee_account="Expenses:Investment:FXFees",
    )


@pytest.fixture
def transactions(importer):
    entries = importer.extract(
        str(FREETRADE_FIXTURE),
        [],
    )

    return [entry for entry in entries if isinstance(entry, data.Transaction)]


def transaction_by_narration(transactions, narration):
    return next(tx for tx in transactions if tx.narration == narration)


def test_identifies_freetrade_csv(importer):
    assert importer.identify(str(FREETRADE_FIXTURE))


def test_expected_transaction_count(transactions):
    assert len(transactions) == 4


def test_transactions_are_sorted_by_date(transactions):
    dates = [tx.date for tx in transactions]

    assert dates == sorted(dates)


def test_gbp_order_with_stamp_duty(transactions):
    tx = transaction_by_narration(
        transactions,
        "Example UK Plc",
    )

    assert tx.date.isoformat() == "2025-01-10"
    assert tx.meta["transaction-type"] == "order"
    assert tx.meta["reference"] == "ORDER-UK-001"
    assert tx.meta["ticker"] == "EXUK"
    assert tx.meta["isin"] == "GB00EXAMPLE01"

    assert len(tx.postings) == 3

    asset = next(
        posting for posting in tx.postings if posting.account == "Assets:Investments:Freetrade:EXUK"
    )

    cash = next(
        posting for posting in tx.postings if posting.account == "Assets:Investments:Freetrade:Cash"
    )

    stamp_duty = next(
        posting for posting in tx.postings if posting.account == "Expenses:Investment:StampDuty"
    )

    assert asset.units.number == Decimal("10.00000000")
    assert asset.units.currency == "EXUK"

    assert asset.cost.number == Decimal("10.00000000")
    assert asset.cost.currency == "GBP"

    assert cash.units.number == Decimal("-100.50")
    assert cash.units.currency == "GBP"

    assert stamp_duty.units.number == Decimal("0.50")
    assert stamp_duty.units.currency == "GBP"


def test_foreign_order_with_fx_fee(transactions):
    tx = transaction_by_narration(
        transactions,
        "Example US Inc",
    )

    assert tx.date.isoformat() == "2025-01-11"
    assert tx.meta["transaction-type"] == "order"
    assert tx.meta["reference"] == "ORDER-US-001"
    assert tx.meta["ticker"] == "EXUS"
    assert tx.meta["isin"] == "US00EXAMPLE02"

    assert len(tx.postings) == 3

    asset = next(
        posting for posting in tx.postings if posting.account == "Assets:Investments:Freetrade:EXUS"
    )

    cash = next(
        posting for posting in tx.postings if posting.account == "Assets:Investments:Freetrade:Cash"
    )

    fx_fee = next(
        posting for posting in tx.postings if posting.account == "Expenses:Investment:FXFees"
    )

    assert asset.units.number == Decimal("2.00000000")
    assert asset.units.currency == "EXUS"

    assert asset.cost.number == Decimal("40.60000000")
    assert asset.cost.currency == "GBP"

    assert cash.units.number == Decimal("-81.20")
    assert cash.units.currency == "GBP"

    assert fx_fee.units.number == Decimal("0.20")
    assert fx_fee.units.currency == "GBP"


def test_dividend(transactions):
    tx = transaction_by_narration(
        transactions,
        "Dividend",
    )

    assert tx.date.isoformat() == "2025-01-15"
    assert tx.payee == "Example Dividend Plc"
    assert tx.meta["transaction-type"] == "dividend"
    assert tx.meta["ticker"] == "EXDV"
    assert tx.meta["isin"] == "GB00EXAMPLE03"

    assert len(tx.postings) == 2

    cash = next(
        posting for posting in tx.postings if posting.account == "Assets:Investments:Freetrade:Cash"
    )

    income = next(
        posting for posting in tx.postings if posting.account == "Income:Investments:Dividends"
    )

    assert cash.units.number == Decimal("12.50")
    assert cash.units.currency == "GBP"

    assert income.units.number == Decimal("-12.50")
    assert income.units.currency == "GBP"


def test_top_up_is_one_sided(transactions):
    tx = transaction_by_narration(
        transactions,
        "Top up",
    )

    assert tx.date.isoformat() == "2025-01-20"
    assert tx.meta["transaction-type"] == "top-up"

    assert len(tx.postings) == 1

    posting = tx.postings[0]

    assert posting.account == "Assets:Investments:Freetrade:Cash"
    assert posting.units.number == Decimal("250.00")
    assert posting.units.currency == "GBP"


def test_top_up_can_be_transfer_matched(transactions):
    tx = transaction_by_narration(
        transactions,
        "Top up",
    )

    assert len(tx.postings) == 1
    assert tx.postings[0].units.number > 0


def test_order_metadata_is_generic(transactions):
    tx = transaction_by_narration(
        transactions,
        "Example UK Plc",
    )

    assert "transaction-type" in tx.meta
    assert "reference" in tx.meta
    assert "ticker" in tx.meta
    assert "isin" in tx.meta

    assert "freetrade_transaction_type" not in tx.meta
    assert "freetrade-order-id" not in tx.meta


def test_all_cash_postings_use_gbp(transactions):
    cash_postings = [
        posting
        for tx in transactions
        for posting in tx.postings
        if posting.account == "Assets:Investments:Freetrade:Cash"
    ]

    assert cash_postings

    for posting in cash_postings:
        assert posting.units.currency == "GBP"

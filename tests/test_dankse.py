from decimal import Decimal
from pathlib import Path

import pytest
from beancount.core import data

from gullion_importers.importers.danske import (
    DanskeCurrentAccountImporter,
)

FIXTURES = Path(__file__).parent / "fixtures" / "danske"

DANSKE_FIXTURE = FIXTURES / "current_account.csv"
INVALID_FIXTURE = FIXTURES / "not_danske.csv"


@pytest.fixture
def importer():
    return DanskeCurrentAccountImporter(
        account="Assets:Bank:Danske",
        currency="GBP",
    )


@pytest.fixture
def entries(importer):
    return importer.extract(
        str(DANSKE_FIXTURE),
        [],
    )


@pytest.fixture
def transactions(entries):
    return [entry for entry in entries if isinstance(entry, data.Transaction)]


def transaction_by_narration(transactions, narration):
    return next(tx for tx in transactions if tx.narration == narration)


def test_identifies_danske_csv(importer):
    assert importer.identify(str(DANSKE_FIXTURE))


def test_rejects_non_danske_csv(importer):
    assert not importer.identify(str(INVALID_FIXTURE))


def test_expected_transaction_count(transactions):
    assert len(transactions) == 8


def test_transactions_are_sorted_chronologically(transactions):
    dates = [tx.date for tx in transactions]

    assert dates == sorted(dates)


def test_month_day_year_date_is_parsed(transactions):
    tx = transaction_by_narration(
        transactions,
        "EXAMPLE CHILDCARE",
    )

    assert tx.date.isoformat() == "2020-04-06"


def test_end_of_month_date_is_parsed(transactions):
    tx = transaction_by_narration(
        transactions,
        "EXAMPLE SUPERMARKET",
    )

    assert tx.date.isoformat() == "2020-03-31"


def test_debit_amount_is_negative(transactions):
    tx = transaction_by_narration(
        transactions,
        "EXAMPLE CHILDCARE",
    )

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-414.00")
    assert posting.units.currency == "GBP"


def test_credit_amount_is_positive(transactions):
    tx = transaction_by_narration(
        transactions,
        "EXAMPLE CREDIT",
    )

    posting = tx.postings[0]

    assert posting.units.number == Decimal("6156.00")
    assert posting.units.currency == "GBP"


def test_comma_separated_debit_amount_is_parsed(transactions):
    tx = transaction_by_narration(
        transactions,
        "EXAMPLE LARGE PAYMENT",
    )

    posting = tx.postings[0]

    assert posting.units.number == Decimal("-20000.00")


def test_narration_is_preserved(transactions):
    tx = transaction_by_narration(
        transactions,
        "TRANSFER FUNDS",
    )

    assert tx.narration == "TRANSFER FUNDS"


def test_all_transactions_use_expected_account(transactions):
    for tx in transactions:
        assert len(tx.postings) == 1

        assert tx.postings[0].account == "Assets:Bank:Danske"


def test_all_transactions_use_gbp(transactions):
    for tx in transactions:
        assert tx.postings[0].units.currency == "GBP"


def test_status_is_not_added_to_metadata(transactions):
    for tx in transactions:
        assert "status" not in tx.meta


def test_reconciled_is_not_added_to_metadata(transactions):
    for tx in transactions:
        assert "reconciled" not in tx.meta


def test_balance_directive_is_created(entries):
    balances = [entry for entry in entries if isinstance(entry, data.Balance)]

    assert len(balances) == 1

    balance = balances[0]

    assert balance.account == "Assets:Bank:Danske"
    assert balance.amount.number == Decimal("12649.69")
    assert balance.amount.currency == "GBP"


def test_balance_directive_is_on_following_day(entries):
    balance = next(entry for entry in entries if isinstance(entry, data.Balance))

    assert balance.date.isoformat() == "2020-04-07"

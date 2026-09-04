from decimal import Decimal
from pathlib import Path

import pytest
from beancount.core import data

from gullion_importers.importers.coinbase import (
    CoinbaseImporter,
)

FIXTURES = Path(__file__).parent / "fixtures" / "coinbase"

COINBASE_FIXTURE = FIXTURES / "transactions.csv"
INVALID_FIXTURE = FIXTURES / "not_coinbase.csv"


@pytest.fixture
def importer():
    return CoinbaseImporter(
        account_root="Assets:Crypto:Coinbase",
        fees_account="Expenses:Financial:Fees",
    )


@pytest.fixture
def transactions(importer):
    entries = importer.extract(
        str(COINBASE_FIXTURE),
        [],
    )

    return [entry for entry in entries if isinstance(entry, data.Transaction)]


def transaction_by_reference(transactions, reference):
    return next(tx for tx in transactions if tx.meta.get("reference") == reference)


def test_identifies_coinbase_csv(importer):
    assert importer.identify(str(COINBASE_FIXTURE))


def test_rejects_non_coinbase_csv(importer):
    assert not importer.identify(str(INVALID_FIXTURE))


def test_expected_transaction_count(transactions):
    assert len(transactions) == 4


def test_transactions_are_sorted_by_date(transactions):
    assert [tx.date.isoformat() for tx in transactions] == [
        "2018-01-14",
        "2018-01-15",
        "2018-01-15",
        "2018-01-15",
    ]


def test_deposit_creates_asset_posting(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-deposit-001",
    )

    assert tx.meta["transaction-type"] == "deposit"

    assert len(tx.postings) == 1

    posting = tx.postings[0]

    assert posting.account == "Assets:Crypto:Coinbase:EUR"
    assert posting.units.number == Decimal("100")
    assert posting.units.currency == "EUR"


def test_deposit_preserves_notes(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-deposit-001",
    )

    assert tx.meta["notes"] == "Deposit from Example Bank"


def test_buy_creates_crypto_asset_posting(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-buy-001",
    )

    assert tx.meta["transaction-type"] == "buy"

    asset_posting = tx.postings[0]

    assert asset_posting.account == "Assets:Crypto:Coinbase:ETH"
    assert asset_posting.units.number == Decimal("0.06617081")
    assert asset_posting.units.currency == "ETH"


def test_buy_sets_cost_basis(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-buy-001",
    )

    posting = tx.postings[0]

    assert posting.cost is not None
    assert posting.cost.number == Decimal("945.95632476")
    assert posting.cost.currency == "GBP"
    assert posting.cost.date.isoformat() == "2018-01-15"


def test_buy_adds_fee_posting(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-buy-001",
    )

    fee_posting = next(
        posting for posting in tx.postings if posting.account == "Expenses:Financial:Fees"
    )

    assert fee_posting.units.number == Decimal("4.1008537660077444")
    assert fee_posting.units.currency == "GBP"


def test_buy_adds_unresolved_funding_posting(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-buy-001",
    )

    funding_posting = next(
        posting for posting in tx.postings if posting.account == "Assets:Crypto:Coinbase:Funding"
    )

    assert funding_posting.units is None


def test_buy_without_zero_fee_does_not_create_extra_fee_posting(
    transactions,
):
    tx = transaction_by_reference(
        transactions,
        "tx-buy-002",
    )

    fee_postings = [
        posting for posting in tx.postings if posting.account == "Expenses:Financial:Fees"
    ]

    assert len(fee_postings) == 1


def test_send_creates_negative_crypto_posting(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-send-001",
    )

    assert tx.meta["transaction-type"] == "send"

    crypto_posting = tx.postings[0]

    assert crypto_posting.account == "Assets:Crypto:Coinbase:ETH"
    assert crypto_posting.units.number == Decimal("-0.11105")
    assert crypto_posting.units.currency == "ETH"


def test_send_adds_market_price(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-send-001",
    )

    posting = tx.postings[0]

    assert posting.price is not None
    assert posting.price.number == Decimal("930.18949674")
    assert posting.price.currency == "GBP"


def test_send_creates_external_balancing_posting(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-send-001",
    )

    external_posting = next(
        posting for posting in tx.postings if posting.account == "Assets:Crypto:External"
    )

    assert external_posting.units is None


def test_send_uses_notes_as_narration(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-send-001",
    )

    assert tx.narration == "Sent 0.11105 ETH to external wallet"


def test_buy_uses_expected_narration(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-buy-001",
    )

    assert tx.payee == "Coinbase"
    assert tx.narration == "Buy ETH"


def test_reference_is_preserved(transactions):
    tx = transaction_by_reference(
        transactions,
        "tx-buy-001",
    )

    assert tx.meta["reference"] == "tx-buy-001"


def test_all_transactions_have_generic_transaction_type(transactions):
    expected_types = {
        "deposit",
        "buy",
        "send",
    }

    actual_types = {tx.meta["transaction-type"] for tx in transactions}

    assert actual_types == expected_types

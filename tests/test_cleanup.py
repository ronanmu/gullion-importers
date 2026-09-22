from decimal import Decimal
from pathlib import Path

import pytest
from beancount.core import data
from beancount.core.amount import Amount

from gullion_importers.hooks.cleanup import TransactionCleanup

FIXTURES = Path(__file__).parent / "fixtures" / "cleanup"
RULES_FILE = FIXTURES / "rules.csv"


@pytest.fixture
def cleanup():
    return TransactionCleanup(
        rules_file=RULES_FILE,
    )


def make_transaction(
    *,
    narration,
    payee=None,
    amount="-10.00",
    account="Assets:Bank:Test",
    metadata=None,
    tags=None,
    postings=None,
):
    if postings is None:
        postings = [
            data.Posting(
                account=account,
                units=Amount(
                    Decimal(amount),
                    "GBP",
                ),
                cost=None,
                price=None,
                flag=None,
                meta=None,
            )
        ]

    return data.Transaction(
        meta=metadata or {},
        date=data.new_metadata(
            "test.bean",
            1,
        ).get("date", None)
        or __import__("datetime").date(2026, 1, 1),
        flag="*",
        payee=payee,
        narration=narration,
        tags=frozenset(tags or []),
        links=frozenset(),
        postings=postings,
    )


def run_cleanup(cleanup, transaction):
    extracted = [
        (
            "test.csv",
            [transaction],
            "Assets:Bank:Test",
            None,
        )
    ]

    result = cleanup.hook(
        extracted,
        [],
    )

    return result[0][1][0]


def test_rewrites_payee(cleanup):
    tx = make_transaction(
        narration="NETFLIX.COM 123456",
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned.payee == "Netflix"


def test_rewrites_narration(cleanup):
    tx = make_transaction(
        narration="NETFLIX.COM 123456",
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned.narration == "Subscription"


def test_adds_expense_account(cleanup):
    tx = make_transaction(
        narration="NETFLIX.COM 123456",
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert len(cleaned.postings) == 2

    assert cleaned.postings[1].account == "Expenses:Entertainment:Subscriptions"

    assert cleaned.postings[1].units is None


def test_adds_tags(cleanup):
    tx = make_transaction(
        narration="NETFLIX.COM 123456",
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert "subscription" in cleaned.tags
    assert "recurring" in cleaned.tags


def test_preserves_existing_tags(cleanup):
    tx = make_transaction(
        narration="NETFLIX.COM 123456",
        tags={"existing"},
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned.tags == frozenset(
        {
            "existing",
            "subscription",
            "recurring",
        }
    )


def test_adds_metadata(cleanup):
    tx = make_transaction(
        narration="NETFLIX.COM 123456",
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned.meta["service"] == "netflix"
    assert cleaned.meta["recurring"] is True


def test_preserves_existing_metadata(cleanup):
    tx = make_transaction(
        narration="NETFLIX.COM 123456",
        metadata={
            "transaction-type": "card-payment",
            "reference": "ABC123",
        },
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned.meta["transaction-type"] == "card-payment"
    assert cleaned.meta["reference"] == "ABC123"

    assert cleaned.meta["service"] == "netflix"
    assert cleaned.meta["recurring"] is True


def test_preserves_fx_metadata(cleanup):
    tx = make_transaction(
        narration="REVOLUT FX",
        metadata={
            "transaction-type": "exchange",
            "fx-matched": True,
            "fx-rate": Decimal("1.1845"),
        },
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned.meta["transaction-type"] == "exchange"
    assert cleaned.meta["fx-matched"] is True
    assert cleaned.meta["fx-rate"] == Decimal("1.1845")

    assert cleaned.meta["source"] == "revolut"
    assert cleaned.meta["reviewed"] is True


def test_rule_metadata_can_override_existing_key(cleanup):
    tx = make_transaction(
        narration="NETFLIX.COM 123456",
        metadata={
            "service": "unknown",
        },
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned.meta["service"] == "netflix"


def test_matches_on_payee(cleanup):
    tx = make_transaction(
        payee="Tesco Stores 1234",
        narration="Card purchase",
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned.payee == "Tesco"

    assert cleaned.postings[1].account == "Expenses:Food:Groceries"


def test_matches_on_both(cleanup):
    tx = make_transaction(
        payee="Amazon",
        narration="AMAZON PRIME MEMBERSHIP",
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned.payee == "Amazon Prime"
    assert cleaned.narration == "Subscription"


def test_first_matching_rule_wins(cleanup):
    tx = make_transaction(
        narration="AMAZON PRIME MEMBERSHIP",
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned.payee == "Amazon Prime"

    assert cleaned.postings[1].account == "Expenses:Entertainment:Subscriptions"


def test_does_not_add_account_to_balanced_transaction(
    cleanup,
):
    postings = [
        data.Posting(
            account="Assets:Bank:Revolut:EUR",
            units=Amount(
                Decimal("-100.00"),
                "EUR",
            ),
            cost=None,
            price=None,
            flag=None,
            meta=None,
        ),
        data.Posting(
            account="Assets:Bank:Revolut:GBP",
            units=Amount(
                Decimal("84.50"),
                "GBP",
            ),
            cost=None,
            price=None,
            flag=None,
            meta=None,
        ),
    ]

    tx = make_transaction(
        narration="REVOLUT FX",
        metadata={
            "transaction-type": "exchange",
            "fx-matched": True,
        },
        postings=postings,
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert len(cleaned.postings) == 2


def test_non_matching_transaction_is_unchanged(cleanup):
    tx = make_transaction(
        narration="SOME UNKNOWN MERCHANT",
        metadata={
            "reference": "XYZ123",
        },
        tags={"existing"},
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned == tx


def test_boolean_metadata_values_are_parsed(cleanup):
    tx = make_transaction(
        narration="NETFLIX.COM 123456",
    )

    cleaned = run_cleanup(
        cleanup,
        tx,
    )

    assert cleaned.meta["recurring"] is True
    assert isinstance(
        cleaned.meta["recurring"],
        bool,
    )

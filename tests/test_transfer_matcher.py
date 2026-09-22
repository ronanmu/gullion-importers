from datetime import date
from decimal import Decimal

import pytest
from beancount.core import data
from beancount.core.amount import Amount

from gullion_importers.hooks.transfers import (
    TransferMatcher,
)

from tests.helpers import all_transactions, make_extracted, make_transaction

AIB_EUR = "Assets:Bank:AIB:EUR"
REVOLUT_EUR = "Assets:Bank:Revolut:EUR"
REVOLUT_GBP = "Assets:Bank:Revolut:GBP"
STARLING_GBP = "Assets:Bank:Starling:GBP"


def run_matcher(extracted_entries):
    matcher = TransferMatcher(
        transfer_accounts={
            AIB_EUR,
            REVOLUT_EUR,
            REVOLUT_GBP,
            STARLING_GBP,
        },
        date_tolerance_days=2,
        minimum_score=80,
    )

    return matcher.hook(
        extracted_entries,
        existing_entries=[],
    )


def test_matches_same_day_equal_and_opposite_transfer():
    aib = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=AIB_EUR,
        amount="-500.00",
        currency="EUR",
        narration="Transfer to Revolut",
    )

    revolut = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="500.00",
        currency="EUR",
        narration="Bank transfer",
    )

    result = run_matcher(
        [
            make_extracted(
                "aib.csv",
                AIB_EUR,
                [aib],
            ),
            make_extracted(
                "revolut.csv",
                REVOLUT_EUR,
                [revolut],
            ),
        ]
    )

    transactions = all_transactions(result)

    assert len(transactions) == 1

    tx = transactions[0]

    assert tx.payee == "Transfer"
    assert tx.meta["transfer-matched"] is True

    assert len(tx.postings) == 2

    assert tx.postings[0].account == AIB_EUR
    assert tx.postings[0].units.number == Decimal("-500.00")

    assert tx.postings[1].account == REVOLUT_EUR
    assert tx.postings[1].units.number == Decimal("500.00")


def test_matches_transfer_one_day_apart():
    aib = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=AIB_EUR,
        amount="-250.00",
        currency="EUR",
        narration="Transfer",
    )

    revolut = make_transaction(
        transaction_date=date(2026, 9, 2),
        account=REVOLUT_EUR,
        amount="250.00",
        currency="EUR",
        narration="Bank transfer received",
    )

    result = run_matcher(
        [
            make_extracted(
                "aib.csv",
                AIB_EUR,
                [aib],
            ),
            make_extracted(
                "revolut.csv",
                REVOLUT_EUR,
                [revolut],
            ),
        ]
    )

    transactions = all_transactions(result)

    assert len(transactions) == 1

    tx = transactions[0]

    # Matcher chooses the later posting date.
    assert tx.date == date(2026, 9, 2)


def test_does_not_match_different_amounts():
    aib = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=AIB_EUR,
        amount="-500.00",
        currency="EUR",
        narration="Transfer",
    )

    revolut = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="499.00",
        currency="EUR",
        narration="Transfer",
    )

    result = run_matcher(
        [
            make_extracted(
                "aib.csv",
                AIB_EUR,
                [aib],
            ),
            make_extracted(
                "revolut.csv",
                REVOLUT_EUR,
                [revolut],
            ),
        ]
    )

    assert len(all_transactions(result)) == 2


def test_does_not_match_different_currencies():
    revolut_eur = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
    )

    revolut_gbp = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_GBP,
        amount="85.00",
        currency="GBP",
        narration="Exchanged from EUR",
    )

    result = run_matcher(
        [
            make_extracted(
                "eur.csv",
                REVOLUT_EUR,
                [revolut_eur],
            ),
            make_extracted(
                "gbp.csv",
                REVOLUT_GBP,
                [revolut_gbp],
            ),
        ]
    )

    # FX should be handled by a separate matcher.
    assert len(all_transactions(result)) == 2


def test_does_not_match_same_account():
    first = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-50.00",
        currency="EUR",
        narration="Transfer",
    )

    second = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="50.00",
        currency="EUR",
        narration="Transfer",
    )

    result = run_matcher(
        [
            make_extracted(
                "revolut.csv",
                REVOLUT_EUR,
                [first, second],
            )
        ]
    )

    assert len(all_transactions(result)) == 2


def test_does_not_match_outside_date_tolerance():
    aib = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=AIB_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Transfer",
    )

    revolut = make_transaction(
        transaction_date=date(2026, 9, 4),
        account=REVOLUT_EUR,
        amount="100.00",
        currency="EUR",
        narration="Transfer",
    )

    result = run_matcher(
        [
            make_extracted(
                "aib.csv",
                AIB_EUR,
                [aib],
            ),
            make_extracted(
                "revolut.csv",
                REVOLUT_EUR,
                [revolut],
            ),
        ]
    )

    assert len(all_transactions(result)) == 2


def test_ignores_already_balanced_transaction():
    existing_transfer = data.Transaction(
        meta={},
        date=date(2026, 9, 1),
        flag="*",
        payee="Transfer",
        narration="Already matched",
        tags=frozenset(),
        links=frozenset(),
        postings=[
            data.Posting(
                account=AIB_EUR,
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
                account=REVOLUT_EUR,
                units=Amount(
                    Decimal("100.00"),
                    "EUR",
                ),
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
        ],
    )

    result = run_matcher(
        [
            make_extracted(
                "already-matched.csv",
                AIB_EUR,
                [existing_transfer],
            )
        ]
    )

    transactions = all_transactions(result)

    assert len(transactions) == 1
    assert len(transactions[0].postings) == 2


def test_ignores_non_transfer_account():
    tx1 = make_transaction(
        transaction_date=date(2026, 9, 1),
        account="Assets:Cash",
        amount="-100.00",
        currency="EUR",
        narration="Transfer",
    )

    tx2 = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="100.00",
        currency="EUR",
        narration="Transfer",
    )

    result = run_matcher(
        [
            make_extracted(
                "cash.csv",
                "Assets:Cash",
                [tx1],
            ),
            make_extracted(
                "revolut.csv",
                REVOLUT_EUR,
                [tx2],
            ),
        ]
    )

    assert len(all_transactions(result)) == 2


def test_preserves_metadata_from_both_transactions():
    aib = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=AIB_EUR,
        amount="-300.00",
        currency="EUR",
        narration="Transfer to Revolut",
        meta={
            "aib_transaction-type": "transfer",
            "shared-key": "aib-value",
        },
    )

    revolut = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="300.00",
        currency="EUR",
        narration="Bank transfer",
        meta={
            "revolut_transaction-type": "bank-transfer",
            "shared-key": "revolut-value",
        },
    )

    result = run_matcher(
        [
            make_extracted(
                "aib.csv",
                AIB_EUR,
                [aib],
            ),
            make_extracted(
                "revolut.csv",
                REVOLUT_EUR,
                [revolut],
            ),
        ]
    )

    tx = all_transactions(result)[0]

    assert tx.meta["aib_transaction-type"] == "transfer"
    assert tx.meta["revolut_transaction-type"] == "bank-transfer"

    assert tx.meta["shared-key"] == "aib-value"
    assert tx.meta["transfer-shared-key"] == "revolut-value"


def test_combines_narrations():
    aib = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=AIB_EUR,
        amount="-75.00",
        currency="EUR",
        narration="Transfer to Revolut",
    )

    revolut = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="75.00",
        currency="EUR",
        narration="Bank transfer received",
    )

    result = run_matcher(
        [
            make_extracted(
                "aib.csv",
                AIB_EUR,
                [aib],
            ),
            make_extracted(
                "revolut.csv",
                REVOLUT_EUR,
                [revolut],
            ),
        ]
    )

    tx = all_transactions(result)[0]

    assert tx.narration == "Transfer to Revolut / Bank transfer received"


@pytest.mark.xfail(reason="Not yet implemented: ambiguous matches should be left untouched.")
def test_ambiguous_equal_score_matches_are_left_untouched():
    outgoing = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_GBP,
        amount="-100.00",
        currency="GBP",
        narration="Transfer",
    )

    starling_1 = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=STARLING_GBP,
        amount="100.00",
        currency="GBP",
        narration="Transfer",
    )

    # A second equally plausible incoming transfer.
    starling_2 = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=AIB_EUR,
        amount="100.00",
        currency="GBP",
        narration="Transfer",
    )

    result = run_matcher(
        [
            make_extracted(
                "revolut.csv",
                REVOLUT_GBP,
                [outgoing],
            ),
            make_extracted(
                "starling.csv",
                STARLING_GBP,
                [starling_1],
            ),
            make_extracted(
                "other.csv",
                AIB_EUR,
                [starling_2],
            ),
        ]
    )

    # Two equally scored candidates means the matcher should
    # refuse to guess.
    assert len(all_transactions(result)) == 3

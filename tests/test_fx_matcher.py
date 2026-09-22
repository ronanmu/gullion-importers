from datetime import date
from decimal import Decimal

import pytest
from beancount.core import data
from beancount.core.amount import Amount

from gullion_importers.hooks.fxmatcher import (
    FXMatcher,
)
from tests.helpers import all_transactions, make_extracted, make_transaction

REVOLUT_EUR = "Assets:Bank:Revolut:EUR"
REVOLUT_GBP = "Assets:Bank:Revolut:GBP"
REVOLUT_AED = "Assets:Bank:Revolut:AED"


def run_matcher(extracted_entries, tolerance=1):
    matcher = FXMatcher(
        fx_accounts={
            REVOLUT_EUR,
            REVOLUT_GBP,
            REVOLUT_AED,
        },
        date_tolerance_days=tolerance,
    )

    return matcher.hook(
        extracted_entries,
        existing_entries=[],
    )


def test_matches_same_day_eur_to_gbp_exchange():
    eur = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
    )

    gbp = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_GBP,
        amount="85.00",
        currency="GBP",
        narration="Exchanged to GBP",
    )

    result = run_matcher(
        [
            make_extracted(
                "revolut-eur.csv",
                REVOLUT_EUR,
                [eur],
            ),
            make_extracted(
                "revolut-gbp.csv",
                REVOLUT_GBP,
                [gbp],
            ),
        ]
    )

    transactions = all_transactions(result)

    assert len(transactions) == 1

    tx = transactions[0]

    assert tx.payee == "FX"
    assert tx.narration == "EUR → GBP"

    assert tx.meta["transaction-type"] == "exchange"
    assert tx.meta["fx-matched"] is True

    assert len(tx.postings) == 2

    assert tx.postings[0].account == REVOLUT_EUR
    assert tx.postings[0].units.number == Decimal("-100.00")
    assert tx.postings[0].units.currency == "EUR"

    assert tx.postings[1].account == REVOLUT_GBP
    assert tx.postings[1].units.number == Decimal("85.00")
    assert tx.postings[1].units.currency == "GBP"

    assert tx.postings[1].price.currency == "EUR"


def test_calculates_expected_exchange_rate():
    eur = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
    )

    gbp = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_GBP,
        amount="80.00",
        currency="GBP",
        narration="Exchanged to GBP",
    )

    result = run_matcher(
        [
            make_extracted(
                "eur.csv",
                REVOLUT_EUR,
                [eur],
            ),
            make_extracted(
                "gbp.csv",
                REVOLUT_GBP,
                [gbp],
            ),
        ]
    )

    tx = all_transactions(result)[0]

    expected_rate = Decimal("1.25")

    assert tx.meta["fx-rate"] == expected_rate
    assert tx.postings[1].price.number == expected_rate
    assert tx.postings[1].price.currency == "EUR"


def test_matches_exchange_one_day_apart():
    eur = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
    )

    gbp = make_transaction(
        transaction_date=date(2026, 9, 2),
        account=REVOLUT_GBP,
        amount="85.00",
        currency="GBP",
        narration="Exchanged to GBP",
    )

    result = run_matcher(
        [
            make_extracted(
                "eur.csv",
                REVOLUT_EUR,
                [eur],
            ),
            make_extracted(
                "gbp.csv",
                REVOLUT_GBP,
                [gbp],
            ),
        ]
    )

    transactions = all_transactions(result)

    assert len(transactions) == 1
    assert transactions[0].date == date(2026, 9, 2)


def test_does_not_match_outside_date_tolerance():
    eur = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
    )

    gbp = make_transaction(
        transaction_date=date(2026, 9, 3),
        account=REVOLUT_GBP,
        amount="85.00",
        currency="GBP",
        narration="Exchanged to GBP",
    )

    result = run_matcher(
        [
            make_extracted(
                "eur.csv",
                REVOLUT_EUR,
                [eur],
            ),
            make_extracted(
                "gbp.csv",
                REVOLUT_GBP,
                [gbp],
            ),
        ]
    )

    assert len(all_transactions(result)) == 2


def test_does_not_match_same_currency():
    eur_out = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
    )

    eur_in = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="85.00",
        currency="EUR",
        narration="Exchanged to GBP",
    )

    result = run_matcher(
        [
            make_extracted(
                "eur.csv",
                REVOLUT_EUR,
                [eur_out, eur_in],
            )
        ]
    )

    assert len(all_transactions(result)) == 2


def test_does_not_match_same_sign():
    eur = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
    )

    gbp = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_GBP,
        amount="-85.00",
        currency="GBP",
        narration="Exchanged to GBP",
    )

    result = run_matcher(
        [
            make_extracted(
                "eur.csv",
                REVOLUT_EUR,
                [eur],
            ),
            make_extracted(
                "gbp.csv",
                REVOLUT_GBP,
                [gbp],
            ),
        ]
    )

    assert len(all_transactions(result)) == 2


def test_does_not_match_if_target_currency_does_not_match_incoming_leg():
    eur = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
    )

    aed = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_AED,
        amount="400.00",
        currency="AED",
        narration="Exchanged to GBP",
    )

    result = run_matcher(
        [
            make_extracted(
                "eur.csv",
                REVOLUT_EUR,
                [eur],
            ),
            make_extracted(
                "aed.csv",
                REVOLUT_AED,
                [aed],
            ),
        ]
    )

    assert len(all_transactions(result)) == 2


def test_does_not_match_different_target_descriptions():
    eur = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
    )

    gbp = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_GBP,
        amount="85.00",
        currency="GBP",
        narration="Exchanged to AED",
    )

    result = run_matcher(
        [
            make_extracted(
                "eur.csv",
                REVOLUT_EUR,
                [eur],
            ),
            make_extracted(
                "gbp.csv",
                REVOLUT_GBP,
                [gbp],
            ),
        ]
    )

    assert len(all_transactions(result)) == 2


def test_ignores_non_exchange_transaction():
    eur = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
        transaction_type="transfer",
    )

    gbp = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_GBP,
        amount="85.00",
        currency="GBP",
        narration="Exchanged to GBP",
    )

    result = run_matcher(
        [
            make_extracted(
                "eur.csv",
                REVOLUT_EUR,
                [eur],
            ),
            make_extracted(
                "gbp.csv",
                REVOLUT_GBP,
                [gbp],
            ),
        ]
    )

    assert len(all_transactions(result)) == 2


def test_ignores_already_balanced_transaction():
    balanced = data.Transaction(
        meta={
            "transaction-type": "exchange",
        },
        date=date(2026, 9, 1),
        flag="*",
        payee="FX",
        narration="EUR → GBP",
        tags=frozenset(),
        links=frozenset(),
        postings=[
            data.Posting(
                account=REVOLUT_EUR,
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
                account=REVOLUT_GBP,
                units=Amount(
                    Decimal("85.00"),
                    "GBP",
                ),
                cost=None,
                price=Amount(
                    Decimal("1.176470588"),
                    "EUR",
                ),
                flag=None,
                meta=None,
            ),
        ],
    )

    result = run_matcher(
        [
            make_extracted(
                "existing.csv",
                REVOLUT_EUR,
                [balanced],
            )
        ]
    )

    transactions = all_transactions(result)

    assert len(transactions) == 1
    assert len(transactions[0].postings) == 2


def test_matches_gbp_to_aed():
    gbp = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_GBP,
        amount="-100.00",
        currency="GBP",
        narration="Exchanged to AED",
    )

    aed = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_AED,
        amount="480.00",
        currency="AED",
        narration="Exchanged to AED",
    )

    result = run_matcher(
        [
            make_extracted(
                "gbp.csv",
                REVOLUT_GBP,
                [gbp],
            ),
            make_extracted(
                "aed.csv",
                REVOLUT_AED,
                [aed],
            ),
        ]
    )

    tx = all_transactions(result)[0]

    assert tx.narration == "GBP → AED"

    assert tx.postings[0].units.currency == "GBP"
    assert tx.postings[1].units.currency == "AED"

    assert tx.postings[1].price.currency == "GBP"


@pytest.mark.xfail(reason="Not yet implemented: ambiguous matches should be left untouched.")
def test_ambiguous_matches_are_left_untouched():
    eur = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
    )

    gbp_first = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_GBP,
        amount="85.00",
        currency="GBP",
        narration="Exchanged to GBP",
    )

    gbp_second = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_GBP,
        amount="86.00",
        currency="GBP",
        narration="Exchanged to GBP",
    )

    result = run_matcher(
        [
            make_extracted(
                "eur.csv",
                REVOLUT_EUR,
                [eur],
            ),
            make_extracted(
                "gbp-1.csv",
                REVOLUT_GBP,
                [gbp_first],
            ),
            make_extracted(
                "gbp-2.csv",
                REVOLUT_GBP,
                [gbp_second],
            ),
        ]
    )

    # Matcher should refuse to choose between two plausible
    # destination legs.
    assert len(all_transactions(result)) == 3


def test_preserves_metadata_from_both_legs():
    eur = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_EUR,
        amount="-100.00",
        currency="EUR",
        narration="Exchanged to GBP",
        meta={
            "source-reference": "source-123",
        },
    )

    gbp = make_transaction(
        transaction_date=date(2026, 9, 1),
        account=REVOLUT_GBP,
        amount="85.00",
        currency="GBP",
        narration="Exchanged to GBP",
        meta={
            "destination-reference": "dest-456",
        },
    )

    result = run_matcher(
        [
            make_extracted(
                "eur.csv",
                REVOLUT_EUR,
                [eur],
            ),
            make_extracted(
                "gbp.csv",
                REVOLUT_GBP,
                [gbp],
            ),
        ]
    )

    tx = all_transactions(result)[0]

    assert tx.meta["source-reference"] == "source-123"
    assert tx.meta["destination-reference"] == "dest-456"
    assert tx.meta["fx-matched"] is True

from __future__ import annotations

from decimal import Decimal

from beancount.core import data
from beancount.core.amount import Amount


def make_transaction(
    *,
    transaction_date,
    account,
    amount,
    currency,
    narration,
    payee=None,
    meta=None,
    transaction_type="exchange",
):
    transaction_meta = dict(meta or {})

    if transaction_type is not None:
        transaction_meta["transaction-type"] = transaction_type

    posting = data.Posting(
        account=account,
        units=Amount(
            Decimal(amount),
            currency,
        ),
        cost=None,
        price=None,
        flag=None,
        meta=None,
    )

    return data.Transaction(
        meta=transaction_meta,
        date=transaction_date,
        flag="*",
        payee=payee,
        narration=narration,
        tags=frozenset(),
        links=frozenset(),
        postings=[posting],
    )


def make_extracted(
    filename,
    account,
    transactions,
):
    return (
        filename,
        transactions,
        account,
        None,
    )


def all_transactions(result):
    return [
        entry
        for _, entries, _, _ in result
        for entry in entries
        if isinstance(entry, data.Transaction)
    ]

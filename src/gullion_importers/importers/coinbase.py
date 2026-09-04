from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from beancount.core import data
from beancount.core.amount import Amount
from beancount.core.position import Cost
from beangulp.importers import csvbase

from .common.metadata import NOTES, REFERENCE, TRANSACTION_TYPE


class CoinbaseAmount(csvbase.Column):
    """
    Parse Coinbase currency amounts such as:

        £930.18949674
        -£103.29754
        €100.00
        $25.00
    """

    def parse(self, value):
        value = value.strip()

        if not value:
            return None

        value = re.sub(
            r"[£€$,\s]",
            "",
            value,
        )

        return Decimal(value)


class CoinbaseImporter(csvbase.Importer):
    """
    Import Coinbase transaction-history CSV exports.
    """

    date = csvbase.Date(
        "Timestamp",
        frmt="%Y-%m-%d %H:%M:%S UTC",
    )

    transaction_id = csvbase.Column("ID")

    transaction_type = csvbase.Column(
        "Transaction Type",
    )

    asset = csvbase.Column("Asset")

    quantity = csvbase.Amount(
        "Quantity Transacted",
    )

    price_currency = csvbase.Column(
        "Price Currency",
    )

    price = CoinbaseAmount(
        "Price at Transaction",
    )

    subtotal = CoinbaseAmount("Subtotal")

    total = CoinbaseAmount("Total")

    fees = CoinbaseAmount(
        "Fees",
        default=None,
    )

    notes = csvbase.Column(
        "Notes",
        default=None,
    )

    def __init__(
        self,
        account_root: str,
        fees_account: str = "Expenses:Coinbase:Fees",
    ):

        self.account_root = account_root
        self.fees_account = fees_account

        super().__init__(account=account_root, currency="GBP")

    def identify(self, filepath: str) -> bool:
        path = Path(filepath)

        if path.suffix.lower() != ".csv":
            return False

        try:
            with path.open(
                "r",
                encoding=self.encoding,
                errors="replace",
            ) as file:
                header = file.readline()
        except OSError:
            return False

        required_columns = (
            "ID",
            "Timestamp",
            "Transaction Type",
            "Asset",
            "Quantity Transacted",
            "Price Currency",
            "Price at Transaction",
            "Subtotal",
            "Total",
            "Fees",
            "Notes",
        )

        return all(column in header for column in required_columns)

    def account(self, filepath):
        return self.account_root

    def _asset_account(self, asset: str) -> str:
        return f"{self.account_root}:{asset}"

    @staticmethod
    def _metadata(filepath, lineno, row):
        meta = data.new_metadata(
            filepath,
            lineno,
        )

        meta[TRANSACTION_TYPE] = row.transaction_type.strip().lower().replace(" ", "-")

        meta[REFERENCE] = row.transaction_id

        if row.notes:
            meta[NOTES] = row.notes.strip()

        return meta

    def extract(self, filepath, existing=None):
        entries = []

        for lineno, row in enumerate(
            self.read(filepath),
            start=2,
        ):
            transaction_type = row.transaction_type.strip().lower()

            if transaction_type == "buy":
                txn = self._buy(
                    filepath,
                    lineno,
                    row,
                )

            elif transaction_type == "send":
                txn = self._send(
                    filepath,
                    lineno,
                    row,
                )

            elif transaction_type == "deposit":
                txn = self._deposit(
                    filepath,
                    lineno,
                    row,
                )

            else:
                txn = self._generic(
                    filepath,
                    lineno,
                    row,
                )

            if txn is not None:
                entries.append(txn)

        return sorted(
            entries,
            key=lambda entry: entry.date,
        )

    def _buy(
        self,
        filepath,
        lineno,
        row,
    ):
        meta = self._metadata(
            filepath,
            lineno,
            row,
        )

        asset_account = self._asset_account(row.asset)

        cost = Cost(
            row.price,
            row.price_currency,
            row.date,
            None,
        )

        asset_posting = data.Posting(
            account=asset_account,
            units=Amount(
                row.quantity,
                row.asset,
            ),
            cost=cost,
            price=None,
            flag=None,
            meta=None,
        )

        postings = [
            asset_posting,
        ]

        if row.fees and row.fees != 0:
            postings.append(
                data.Posting(
                    account=self.fees_account,
                    units=Amount(
                        row.fees,
                        row.price_currency,
                    ),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                )
            )

        # Deliberately leave the funding side unresolved.
        postings.append(
            data.Posting(
                account=f"{self.account_root}:Funding",
                units=None,
                cost=None,
                price=None,
                flag=None,
                meta=None,
            )
        )

        return data.Transaction(
            meta=meta,
            date=row.date,
            flag="*",
            payee="Coinbase",
            narration=f"Buy {row.asset}",
            tags=frozenset(),
            links=frozenset(),
            postings=postings,
        )

    def _send(
        self,
        filepath,
        lineno,
        row,
    ):
        meta = self._metadata(
            filepath,
            lineno,
            row,
        )

        return data.Transaction(
            meta=meta,
            date=row.date,
            flag="*",
            payee=None,
            narration=row.notes or f"Send {row.asset}",
            tags=frozenset(),
            links=frozenset(),
            postings=[
                data.Posting(
                    account=self._asset_account(row.asset),
                    units=Amount(
                        row.quantity,
                        row.asset,
                    ),
                    cost=None,
                    price=Amount(
                        row.price,
                        row.price_currency,
                    ),
                    flag=None,
                    meta=None,
                ),
                data.Posting(
                    account="Assets:Crypto:External",
                    units=None,
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

    def _deposit(
        self,
        filepath,
        lineno,
        row,
    ):
        meta = self._metadata(
            filepath,
            lineno,
            row,
        )

        return data.Transaction(
            meta=meta,
            date=row.date,
            flag="*",
            payee=None,
            narration=row.notes or "Deposit",
            tags=frozenset(),
            links=frozenset(),
            postings=[
                data.Posting(
                    account=self._asset_account(row.asset),
                    units=Amount(
                        row.quantity,
                        row.asset,
                    ),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

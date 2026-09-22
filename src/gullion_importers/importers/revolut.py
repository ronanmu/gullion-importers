from __future__ import annotations

import datetime
from pathlib import Path

from beangulp.importers import csvbase

from .common.metadata import FEE, TRANSACTION_TYPE


class RevolutDate(csvbase.Column):
    def __init__(self):
        super().__init__(
            "Completed Date",
            "Started Date",
        )

    def parse(self, completed, started):
        value = completed or started

        return datetime.datetime.strptime(
            value.strip(),
            "%Y-%m-%d %H:%M:%S",
        ).date()


class RevolutCurrentAccountImporter(csvbase.Importer):
    """
    Import Revolut current-account CSV exports.

    Expected columns:

        Type
        Product
        Started Date
        Completed Date
        Description
        Amount
        Fee
        Currency
        State
        Balance
    """

    date = RevolutDate()

    narration = csvbase.Column(
        "Description",
        default=None,
    )

    amount = csvbase.Amount("Amount")

    currency = csvbase.Column("Currency")

    transaction_type = csvbase.Column(
        "Type",
        default=None,
    )

    fee = csvbase.Amount(
        "Fee",
        default=None,
    )

    state = csvbase.Column(
        "State",
        default=None,
    )

    def __init__(
        self,
        account: str,
        currency: str,
        name: str | None = None,
    ):
        self._name = name

        super().__init__(
            account=account,
            currency=currency,
        )

    @property
    def name(self) -> str:
        if self._name is not None:
            return self._name

        return super().name

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
            "Type",
            "Product",
            "Started Date",
            "Completed Date",
            "Description",
            "Amount",
            "Fee",
            "Currency",
            "State",
            "Balance",
        )

        return all(column in header for column in required_columns)

    def metadata(self, filepath, lineno, row):
        meta = super().metadata(
            filepath,
            lineno,
            row,
        )

        if row.transaction_type:
            meta[TRANSACTION_TYPE] = row.transaction_type.strip().lower().replace(" ", "-")

        if row.fee is not None and row.fee != 0:
            meta[FEE] = row.fee

        return meta

    def finalize(self, txn, row):
        """
        Discard transactions which Revolut subsequently reverted.
        """

        if row.state and row.state.strip().upper() == "REVERTED":
            return None

        return txn

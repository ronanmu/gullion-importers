from __future__ import annotations

import csv
from pathlib import Path

from beangulp.importers import csvbase


class DanskeCurrentAccountImporter(csvbase.Importer):
    """
    Import Danske Bank current-account CSV exports.

    Expected columns:

        Date,Text,Amount,Balance,Status,Reconciled

    Amount is already signed:
        debit  -> negative
        credit -> positive

    Danske dates are exported in month/day/year format.
    """

    date = csvbase.Date(
        "Date",
        frmt="%m/%d/%Y",
    )

    narration = csvbase.Column(
        "Text",
    )

    amount = csvbase.Amount(
        "Amount",
        subs={
            r",": "",
        },
    )

    balance = csvbase.Amount(
        "Balance",
        subs={
            r",": "",
        },
    )

    def __init__(
        self,
        account: str,
        currency: str = "GBP",
    ):
        super().__init__(
            account=account,
            currency=currency,
        )

    def identify(self, filepath: str) -> bool:
        path = Path(filepath)

        if path.suffix.lower() != ".csv":
            return False

        try:
            with path.open(
                "r",
                encoding=self.encoding,
                newline="",
            ) as file:
                reader = csv.reader(file)
                header = next(reader, None)
        except (OSError, csv.Error):
            return False

        if not header:
            return False

        expected = [
            "Date",
            "Text",
            "Amount",
            "Balance",
            "Status",
            "Reconciled",
        ]

        return [value.strip() for value in header] == expected

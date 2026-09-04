from __future__ import annotations

import csv
from pathlib import Path

from beangulp.importers import csvbase

from .common.metadata import CATEGORY


class BarclaycardImporter(csvbase.Importer):
    """
    Import Barclaycard headerless CSV exports.

    Expected column positions:

        0 Date
        1 Description
        2 Card Type
        3 Card Member
        4 Category
        5 Unknown / blank
        6 Amount
    """

    names = False

    date = csvbase.Date(
        0,
        frmt="%d %b %y",
    )

    narration = csvbase.Column(
        1,
        default=None,
    )

    card_type = csvbase.Column(
        2,
        default=None,
    )

    card_member = csvbase.Column(
        3,
        default=None,
    )

    category = csvbase.Column(
        4,
        default=None,
    )

    amount = csvbase.CreditOrDebit(
        credit=5,
        debit=6,
        subs={r"^-": "", r",": ""},
        default=None,
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
                row = next(reader, None)

        except (OSError, csv.Error):
            return False

        if not row or len(row) < 7:
            return False

        # Column 2 should identify the card scheme.
        card_type = row[2].strip().lower()

        if card_type not in {
            "mastercard",
            "visa",
        }:
            return False

        # Final column should be a valid amount.
        try:
            float(row[6])
        except ValueError:
            return False

        return True

    def metadata(
        self,
        filepath,
        lineno,
        row,
    ):
        meta = super().metadata(
            filepath,
            lineno,
            row,
        )

        if row.category:
            meta[CATEGORY] = row.category.strip().lower()

        # Deliberately do not expose card_member in metadata.

        return meta

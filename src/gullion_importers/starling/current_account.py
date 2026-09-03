from __future__ import annotations

from pathlib import Path

from beangulp.importers import csvbase


class StarlingCurrentAccountImporter(csvbase.Importer):
    """
    Starling current-account CSV importer.

    The Starling export has a stable column layout regardless of currency,
    so we use fixed numeric indexes rather than per-currency header names.
    """

    date = csvbase.Date(0, frmt="%d/%m/%Y")
    payee = csvbase.Column(1, default=None)
    narration = csvbase.Column(2, default=None)
    transaction_type = csvbase.Column(3, default=None)
    amount = csvbase.Amount(4)
    raw_balance = csvbase.Amount(5, default=None)
    spending_category = csvbase.Column(6, default=None)
    notes = csvbase.Column(7, default=None)

    def __init__(
        self,
        account: str,
        currency: str = "GBP",
    ):
        self.starling_currency = currency

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
                errors="replace",
            ) as file:
                header = file.readline()
        except OSError:
            return False

        required_columns = (
            "Date",
            "Counter Party",
            "Reference",
            "Type",
            "Spending Category",
            "Notes",
        )

        amount_column = f"Amount ({self.starling_currency})"
        balance_column = f"Balance ({self.starling_currency})"

        return (
            all(column in header for column in required_columns)
            and amount_column in header
            and balance_column in header
        )

    def metadata(self, filepath, lineno, row):
        meta = super().metadata(
            filepath,
            lineno,
            row,
        )

        if row.transaction_type:
            meta["transaction-type"] = row.transaction_type.strip().lower().replace(" ", "-")

        if row.spending_category:
            meta["spend-category"] = row.spending_category.strip().lower()

        if row.notes:
            notes = row.notes.strip()

            if notes:
                meta["notes"] = notes

        return meta

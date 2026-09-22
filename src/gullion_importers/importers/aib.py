from __future__ import annotations

from pathlib import Path

from beangulp.importers import csvbase

from .common.metadata import LOCAL_AMOUNT, LOCAL_CURRENCY, TRANSACTION_TYPE


class AIBCurrentAccountImporter(csvbase.Importer):
    """
    Import AIB current-account CSV exports.

    Expected columns include:

        Posted Account
        Posted Transactions Date
        Description1
        Description2
        Description3
        Debit Amount
        Credit Amount
        Balance
        Posted Currency
        Transaction Type
        Local Currency Amount
        Local Currency
    """

    TRANSACTION_TYPE_PREFIXES = {
        "ATM": "atm-aib",
        "ATMLDG": "atm-lodgement",
        "D/D": "direct-debit",
        "*INET": "internet-banking",
        "*MOBI": "app",
        "MSA": "atm",
        "MSP": "point-of-sale",
        "OP/": "direct-debit",
        "POS": "point-of-sale",
        "VDA": "atm",
        "VDC": "contactless",
        "VDP": "point-of-sale",
    }

    # Required fields used directly by csvbase.Importer.
    date = csvbase.Date(
        "Posted Transactions Date",
        frmt="%d/%m/%Y",
    )

    narration = csvbase.Columns(
        "Description1",
        "Description2",
        "Description3",
        sep=" ",
    )

    amount = csvbase.CreditOrDebit(credit="Credit Amount", debit="Debit Amount", subs={",": ""})

    currency = csvbase.Column("Posted Currency")

    # If supplied, csvbase will create balance assertions automatically.
    balance_raw = csvbase.Amount(
        "Balance",
        default=None,
    )

    # Extra AIB fields which aren't directly consumed by the base importer,
    # but are available to metadata() / finalize().
    posted_account = csvbase.Column(
        "Posted Account",
        default=None,
    )

    transaction_type = csvbase.Column(
        "Transaction Type",
        default=None,
    )

    local_amount = csvbase.Amount(
        "Local Currency Amount",
        default=None,
    )

    local_currency = csvbase.Column(
        "Local Currency",
        default=None,
    )

    description1 = csvbase.Column(
        "Description1",
        default=None,
    )

    description2 = csvbase.Column(
        "Description2",
        default=None,
    )

    description3 = csvbase.Column(
        "Description3",
        default=None,
    )

    def __init__(
        self,
        account: str,
        currency: str = "EUR",
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
        """
        Only claim CSV files that look like AIB exports.
        """
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
            "Posted Account",
            "Posted Transactions Date",
            "Description1",
            "Debit Amount",
            "Credit Amount",
            "Posted Currency",
        )

        return all(column in header for column in required_columns)

    def metadata(self, filepath, lineno, row):
        """
        Preserve useful AIB source information.

        This information can subsequently help transfer matching,
        debugging and FX handling.
        """
        meta = super().metadata(
            filepath,
            lineno,
            row,
        )

        transaction_type = self._transaction_type(row)
        if row.transaction_type:
            meta[TRANSACTION_TYPE] = transaction_type

        posted_currency = row.currency
        local_currency = row.local_currency

        if local_currency and posted_currency and local_currency != posted_currency:
            if row.local_amount is not None:
                meta[LOCAL_AMOUNT] = row.local_amount

            meta[LOCAL_CURRENCY] = local_currency

        return meta

    @classmethod
    def _transaction_type(cls, row) -> str | None:
        narration = (row.narration or "").strip().upper()

        for prefix, transaction_type in cls.TRANSACTION_TYPE_PREFIXES.items():
            if (
                narration.startswith(prefix + "-")
                or narration.startswith(prefix + " ")
                or narration.startswith(prefix)
            ):
                return transaction_type

        return row.transaction_type.strip().lower() if row.transaction_type else None

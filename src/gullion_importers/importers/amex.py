from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from beangulp.importers import csvbase

from .common.metadata import (
    CATEGORY,
    COUNTRY,
    FX_RATE,
    LOCAL_AMOUNT,
    LOCAL_CURRENCY,
    REFERENCE,
    STATEMENT_DESCRIPTION,
)


class AmexAmount(csvbase.Column):
    """
    American Express reports purchases as positive amounts and
    refunds/credits as negative amounts.

    For a Beancount Liability account we want the opposite:

        Purchase  105.66  -> -105.66 GBP
        Refund    -17.00  ->  17.00 GBP
    """

    def __init__(self):
        super().__init__("Amount")

    def parse(self, value):
        value = value.strip()

        if not value:
            return Decimal("0")

        return -Decimal(value.replace(",", ""))


class AmericanExpressImporter(csvbase.Importer):
    """
    Import American Express CSV exports.

    Expected columns:

        Date
        Description
        Card Member
        Account #
        Amount
        Extended Details
        Appears On Your Statement As
        Address
        Town/City
        Postcode
        Country
        Reference
        Category
    """

    date = csvbase.Date(
        "Date",
        frmt="%d/%m/%Y",
    )

    # Keep the original Amex description as the narration.
    #
    # Payee cleaning can happen later in the common cleaning hook.
    narration = csvbase.Column(
        "Description",
        default=None,
    )

    amount = AmexAmount()

    extended_details = csvbase.Column(
        "Extended Details",
        default=None,
    )

    statement_description = csvbase.Column(
        "Appears On Your Statement As",
        default=None,
    )

    address = csvbase.Column(
        "Address",
        default=None,
    )

    town = csvbase.Column(
        "Town/City",
        default=None,
    )

    postcode = csvbase.Column(
        "Postcode",
        default=None,
    )

    country = csvbase.Column(
        "Country",
        default=None,
    )

    reference = csvbase.Column(
        "Reference",
        default=None,
    )

    category = csvbase.Column(
        "Category",
        default=None,
    )

    def __init__(
        self,
        account: str,
        currency: str = "GBP",
    ):
        self.amex_currency = currency

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
            "Description",
            "Amount",
            "Extended Details",
            "Appears On Your Statement As",
            "Reference",
            "Category",
        )

        return all(column in header for column in required_columns)

    def metadata(self, filepath, lineno, row):
        meta = super().metadata(
            filepath,
            lineno,
            row,
        )

        #
        # Amex transaction reference
        #
        # Remove the leading quote that sometimes appears in
        # exported CSV values:
        #
        #   'AT253650055000012535794'
        #
        if row.reference:
            reference = row.reference.strip().lstrip("'").rstrip("'")

            if reference:
                meta[REFERENCE] = reference

        #
        # Amex category
        #
        if row.category:
            category = row.category.strip()

            if category:
                meta[CATEGORY] = category

        #
        # Statement description
        #
        # Only retain it when it actually differs from the primary
        # description.
        #
        if row.statement_description:
            statement_description = row.statement_description.strip()

            description = row.narration.strip() if row.narration else ""

            if statement_description and statement_description != description:
                meta[STATEMENT_DESCRIPTION] = statement_description

        #
        # Country
        #
        if row.country:
            country = row.country.strip()

            if country:
                meta[COUNTRY] = country

        #
        # Parse foreign-currency information.
        #
        # Example:
        #
        # Foreign Spend Amount: 147.99 UNITED STATES DOLLAR
        # Commission Amount: 3.28
        # Currency Exchange Rate: 1.3489
        #
        if row.extended_details:
            self._add_extended_details_metadata(
                meta,
                row.extended_details,
            )

        return meta

    @staticmethod
    def _add_extended_details_metadata(
        meta: dict,
        details: str,
    ) -> None:

        details = details.strip()

        if not details:
            return

        foreign_spend = re.search(
            r"Foreign Spend Amount:\s*"
            r"([0-9.,]+)\s+"
            r"(.+?)"
            r"(?=\s+Commission Amount:|\s+Currency Exchange Rate:|$)",
            details,
            flags=re.IGNORECASE,
        )

        if foreign_spend:
            amount = foreign_spend.group(1)
            currency = foreign_spend.group(2)

            meta[LOCAL_AMOUNT] = Decimal(amount.replace(",", ""))
            meta[LOCAL_CURRENCY] = currency.strip()

        commission = re.search(
            r"Commission Amount:\s*([0-9.,]+)",
            details,
            flags=re.IGNORECASE,
        )

        if commission:
            meta["commission"] = Decimal(commission.group(1).replace(",", ""))

        exchange_rate = re.search(
            r"Currency Exchange Rate:\s*([0-9.,]+)",
            details,
            flags=re.IGNORECASE,
        )

        if exchange_rate:
            meta[FX_RATE] = Decimal(exchange_rate.group(1).replace(",", ""))

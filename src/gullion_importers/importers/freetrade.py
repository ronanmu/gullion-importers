from __future__ import annotations

from datetime import datetime
from pathlib import Path

from beancount.core import data
from beancount.core.amount import Amount
from beancount.core.position import Cost
from beangulp.importers import csvbase

from .common.metadata import ISIN, REFERENCE, TICKER, TRANSACTION_TYPE, VENUE


class ISODate(csvbase.Column):
    def parse(self, value):
        value = value.strip()

        if not value:
            return None

        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


class FreetradeImporter(csvbase.Importer):
    """
    Import Freetrade activity CSV exports.
    """

    date = ISODate("Timestamp")

    title = csvbase.Column("Title")
    transaction_type = csvbase.Column("Type")

    account_currency = csvbase.Column(
        "Account Currency",
        default=None,
    )

    total_amount = csvbase.Amount(
        "Total Amount",
        default=None,
    )

    buy_sell = csvbase.Column(
        "Buy / Sell",
        default=None,
    )

    ticker = csvbase.Column(
        "Ticker",
        default=None,
    )

    isin = csvbase.Column(
        "ISIN",
        default=None,
    )

    price_account_currency = csvbase.Amount(
        "Price per Share in Account Currency",
        default=None,
    )

    stamp_duty = csvbase.Amount(
        "Stamp Duty",
        default=None,
    )

    quantity = csvbase.Amount(
        "Quantity",
        default=None,
    )

    venue = csvbase.Column(
        "Venue",
        default=None,
    )

    order_id = csvbase.Column(
        "Order ID",
        default=None,
    )

    order_type = csvbase.Column(
        "Order Type",
        default=None,
    )

    instrument_currency = csvbase.Column(
        "Instrument Currency",
        default=None,
    )

    total_shares_amount = csvbase.Amount(
        "Total Shares Amount",
        default=None,
    )

    price_per_share = csvbase.Amount(
        "Price per Share",
        default=None,
    )

    fx_rate = csvbase.Amount(
        "FX Rate",
        default=None,
    )

    base_fx_rate = csvbase.Amount(
        "Base FX Rate",
        default=None,
    )

    fx_fee_bps = csvbase.Amount(
        "FX Fee (BPS)",
        default=None,
    )

    fx_fee_amount = csvbase.Amount(
        "FX Fee Amount",
        default=None,
    )

    dividend_ex_date = csvbase.Column(
        "Dividend Ex Date",
        default=None,
    )

    dividend_pay_date = csvbase.Column(
        "Dividend Pay Date",
        default=None,
    )

    dividend_quantity = csvbase.Amount(
        "Dividend Eligible Quantity",
        default=None,
    )

    dividend_per_share = csvbase.Amount(
        "Dividend Amount Per Share",
        default=None,
    )

    dividend_gross = csvbase.Amount(
        "Dividend Gross Distribution Amount",
        default=None,
    )

    dividend_net = csvbase.Amount(
        "Dividend Net Distribution Amount",
        default=None,
    )

    dividend_tax_percent = csvbase.Amount(
        "Dividend Withheld Tax Percentage",
        default=None,
    )

    dividend_tax = csvbase.Amount(
        "Dividend Withheld Tax Amount",
        default=None,
    )

    def __init__(
        self,
        account_root: str,
        cash_account: str,
        dividend_income_account: str,
        interest_income_account: str,
        stamp_duty_account: str = "Expenses:Investment:StampDuty",
        fx_fee_account: str = "Expenses:Investment:FXFees",
    ):
        self.account_root = account_root
        self.cash_account = cash_account
        self.dividend_income_account = dividend_income_account
        self.interest_income_account = interest_income_account
        self.stamp_duty_account = stamp_duty_account
        self.fx_fee_account = fx_fee_account

        super().__init__(
            account=account_root,
            currency="GBP",
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

        required = (
            "Title",
            "Type",
            "Timestamp",
            "Account Currency",
            "Total Amount",
            "Ticker",
            "ISIN",
            "Order ID",
            "Dividend Pay Date",
        )

        return all(column in header for column in required)

    def _asset_account(self, row):
        """
        Prefer ISIN as the stable identifier if ticker is absent.
        """
        instrument = row.ticker or row.isin or "Unknown"

        return f"{self.account_root}:{instrument}"

    def _meta(self, filepath, lineno, row):
        meta = data.new_metadata(
            filepath,
            lineno,
        )

        meta[TRANSACTION_TYPE] = row.transaction_type.strip().lower().replace("_", "-")

        if row.order_id:
            meta[REFERENCE] = row.order_id.strip()

        if row.isin:
            meta[ISIN] = row.isin.strip()

        if row.ticker:
            meta[TICKER] = row.ticker.strip()

        if row.venue:
            meta[VENUE] = row.venue.strip()

        return meta

    def extract(self, filepath, existing=None):
        entries = []

        for lineno, row in enumerate(
            self.read(filepath),
            start=2,
        ):
            kind = row.transaction_type.strip().upper()

            if kind == "ORDER":
                entry = self._order(
                    filepath,
                    lineno,
                    row,
                )

            elif kind in {
                "DIVIDEND",
                "SPECIAL_DIVIDEND",
            }:
                entry = self._dividend(
                    filepath,
                    lineno,
                    row,
                )

            elif kind == "INTEREST_FROM_CASH":
                entry = self._interest(
                    filepath,
                    lineno,
                    row,
                )

            elif kind == "TOP_UP":
                entry = self._top_up(
                    filepath,
                    lineno,
                    row,
                )

            elif kind in {
                "MONTHLY_STATEMENT",
                "TAX_CERTIFICATE",
            }:
                # Informational rows, not ledger transactions.
                entry = None

            else:
                entry = None

            if entry is not None:
                entries.append(entry)

        return sorted(
            entries,
            key=lambda entry: entry.date,
        )

    def _order(self, filepath, lineno, row):
        meta = self._meta(
            filepath,
            lineno,
            row,
        )

        account_currency = row.account_currency

        quantity = row.quantity

        if row.buy_sell.upper() == "SELL":
            quantity = -quantity

        asset_posting = data.Posting(
            account=self._asset_account(row),
            units=Amount(
                quantity,
                row.ticker or row.isin,
            ),
            cost=Cost(
                row.price_account_currency,
                account_currency,
                row.date,
                None,
            ),
            price=None,
            flag=None,
            meta=None,
        )

        cash_amount = row.total_amount

        if row.buy_sell.upper() == "BUY":
            cash_amount = -cash_amount

        postings = [
            asset_posting,
            data.Posting(
                account=self.cash_account,
                units=Amount(
                    cash_amount,
                    account_currency,
                ),
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
        ]

        if row.stamp_duty and row.stamp_duty != 0:
            postings.append(
                data.Posting(
                    account=self.stamp_duty_account,
                    units=Amount(
                        row.stamp_duty,
                        account_currency,
                    ),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                )
            )

        if row.fx_fee_amount and row.fx_fee_amount != 0:
            postings.append(
                data.Posting(
                    account=self.fx_fee_account,
                    units=Amount(
                        row.fx_fee_amount,
                        account_currency,
                    ),
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
            payee=None,
            narration=row.title,
            tags=frozenset(),
            links=frozenset(),
            postings=postings,
        )

    def _dividend(self, filepath, lineno, row):
        meta = self._meta(
            filepath,
            lineno,
            row,
        )

        currency = row.account_currency

        postings = [
            data.Posting(
                account=self.cash_account,
                units=Amount(
                    row.total_amount,
                    currency,
                ),
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
            data.Posting(
                account=self.dividend_income_account,
                units=Amount(
                    -row.total_amount,
                    currency,
                ),
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
        ]

        if row.dividend_tax and row.dividend_tax != 0:
            meta["withheld-tax"] = row.dividend_tax

        return data.Transaction(
            meta=meta,
            date=row.date,
            flag="*",
            payee=row.title,
            narration="Dividend",
            tags=frozenset(),
            links=frozenset(),
            postings=postings,
        )

    def _interest(self, filepath, lineno, row):
        meta = self._meta(
            filepath,
            lineno,
            row,
        )

        return data.Transaction(
            meta=meta,
            date=row.date,
            flag="*",
            payee="Freetrade",
            narration="Cash interest",
            tags=frozenset(),
            links=frozenset(),
            postings=[
                data.Posting(
                    account=self.cash_account,
                    units=Amount(
                        row.total_amount,
                        row.account_currency,
                    ),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                data.Posting(
                    account=self.interest_income_account,
                    units=Amount(
                        -row.total_amount,
                        row.account_currency,
                    ),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

    def _top_up(self, filepath, lineno, row):
        meta = self._meta(
            filepath,
            lineno,
            row,
        )

        # Remain one sided so a subsequent transfer hook can
        # match this with the corresponding bank transaction.
        return data.Transaction(
            meta=meta,
            date=row.date,
            flag="*",
            payee=None,
            narration="Top up",
            tags=frozenset(),
            links=frozenset(),
            postings=[
                data.Posting(
                    account=self.cash_account,
                    units=Amount(
                        row.total_amount,
                        row.account_currency,
                    ),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

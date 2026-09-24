from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Mapping

import pdfplumber
from beancount.core.data import Amount, Posting, Transaction
from beangulp import Importer

PatternWithIndex = str | tuple[str, int]


@dataclass(frozen=True)
class PayslipDetails:
    line_items: dict[str, Decimal]
    net_pay: Decimal


class PayslipImporter(Importer):
    def __init__(
        self,
        *,
        account: str,
        line_item_accounts: Mapping[PatternWithIndex, str],
        name: str,
        currency: str = "EUR",
        net_amount_pattern: PatternWithIndex = "Net",
        source_pattern: str | None = None,
        date_pattern: tuple[PatternWithIndex, str] = (r"DATE", "%d/%m/%Y"),
    ):
        self._account = account
        self.currency = currency
        self._line_item_accounts = tuple(
            (*_compile_pattern(pattern), account) for pattern, account in line_item_accounts.items()
        )
        self._name = name

        self.net_amount_pattern = _compile_pattern(net_amount_pattern)
        self.source_pattern = re.compile(source_pattern, re.IGNORECASE) if source_pattern else None
        self.date_pattern = (*_compile_pattern(date_pattern[0]), date_pattern[1])

    @property
    def name(self):
        return self._name

    def account(self, filepath):
        return self._account

    def date(self, filepath):
        return _payslip_date(filepath, self.date_pattern)

    def identify(self, filepath):
        path = Path(filepath)

        if path.suffix.lower() != ".pdf":
            return False

        if self.source_pattern and not self.source_pattern.search(path.name):
            return False

        try:
            parse_payslip(
                filepath,
                self._line_item_accounts,
                self.net_amount_pattern,
                self.date_pattern,
            )
        except ValueError:
            return False
        return True

    @staticmethod
    def _extract_text(filepath):
        with pdfplumber.open(filepath) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)

    def extract(self, filepath, existing_entries=None):
        details = parse_payslip(
            filepath,
            self._line_item_accounts,
            self.net_amount_pattern,
            self.date_pattern,
        )
        postings = []
        for line_item, amount in details.line_items.items():
            account = self._account_for(line_item)
            signed_amount = -amount if account.startswith("Income:") else amount
            postings.append(
                Posting(
                    account=account,
                    units=Amount(signed_amount, self.currency),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                )
            )

        postings.append(
            Posting(
                account=self._account,
                units=Amount(details.net_pay, self.currency),
                cost=None,
                price=None,
                flag=None,
                meta=None,
            )
        )

        return [
            Transaction(
                meta={"filename": str(filepath), "lineno": 0},
                date=_payslip_date(filepath, self.date_pattern),
                flag="*",
                payee=self._name,
                narration=None,
                tags=frozenset(),
                links=frozenset(),
                postings=postings,
            )
        ]

    def _account_for(self, line_item: str) -> str | None:
        for pattern, _, account in self._line_item_accounts:
            if pattern.search(line_item):
                return account
        return None


def parse_payslip(filepath, line_item_accounts, net_amount_pattern, date_pattern) -> PayslipDetails:
    """Extract configured line items, net pay, and date from a payslip PDF."""
    text = PayslipImporter._extract_text(filepath)
    lines = [line.strip() for line in text.splitlines()]

    line_items = _parse_line_items(lines, line_item_accounts)
    net_pay = _amount_after_label(lines, net_amount_pattern)
    _payslip_date(filepath, date_pattern)

    return PayslipDetails(
        line_items=line_items,
        net_pay=net_pay,
    )


def _compile_pattern(pattern: PatternWithIndex) -> tuple[re.Pattern[str], int]:
    if isinstance(pattern, tuple):
        label, amount_index = pattern
    else:
        label, amount_index = pattern, 1
    if amount_index < 1:
        raise ValueError("The amount index must be at least 1")
    return re.compile(label, re.IGNORECASE), amount_index


def _amount_after_label(
    lines: list[str], configured_pattern: tuple[re.Pattern[str], int]
) -> Decimal:
    number_pattern = re.compile(r"(?:[€$£]\s*)?([0-9]{1,3}(?:,[0-9]{3})*\.\d{2})")
    label_pattern, amount_index = configured_pattern
    for line in lines:
        label_match = label_pattern.search(line)
        if not label_match:
            continue
        matches = list(number_pattern.finditer(line, label_match.end()))
        if len(matches) >= amount_index:
            match = matches[amount_index - 1]
            return Decimal(match.group(1).replace(",", ""))

    raise ValueError(
        f"Could not find amount {amount_index} after pattern {label_pattern.pattern!r}"
    )


def _parse_line_items(
    lines: list[str], line_item_accounts: tuple[tuple[re.Pattern[str], int, str], ...]
) -> dict[str, Decimal]:
    line_items: dict[str, Decimal] = {}
    matched_patterns: set[int] = set()
    for line in lines:
        amounts = list(re.finditer(r"(?:[€$£]\s*)?([0-9]{1,3}(?:,[0-9]{3})*\.\d{2})", line))
        segments = []
        previous_end = 0
        for segment_index, amount_match in enumerate(amounts):
            label = _line_item_label(line[previous_end : amount_match.start()])
            previous_end = amount_match.end()
            segments.append((segment_index, label))

        candidates = []
        for pattern_index, (pattern, amount_index, _) in enumerate(line_item_accounts):
            if pattern_index in matched_patterns:
                continue
            matches = [
                (segment_index, label_match)
                for segment_index, label in segments
                for label_match in pattern.finditer(label)
            ]
            if not matches:
                continue
            segment_index, label_match = matches[0]
            target_index = segment_index + amount_index - 1
            if target_index < len(amounts):
                candidates.append(
                    (
                        segment_index,
                        pattern_index,
                        label_match.group(),
                        amounts[target_index],
                    )
                )
        for _, pattern_index, label, amount_match in sorted(candidates):
            if pattern_index in matched_patterns:
                continue
            line_items[label.strip()] = Decimal(amount_match.group(1).replace(",", ""))
            matched_patterns.add(pattern_index)

    missing = [
        pattern.pattern
        for pattern_index, (pattern, _, _) in enumerate(line_item_accounts)
        if pattern_index not in matched_patterns
    ]
    if missing:
        raise ValueError(f"Could not find payslip line items for patterns: {', '.join(missing)}")
    return line_items


def _line_item_label(text: str) -> str:
    parts = [part.strip() for part in text.split("|") if part.strip()]
    return parts[-1] if parts else text.strip()


def _payslip_date(filepath, date_pattern: tuple[re.Pattern[str], int, str]) -> date:
    text = PayslipImporter._extract_text(filepath)
    label_pattern, date_index, format_pattern = date_pattern
    seen = 0
    for line in text.splitlines():
        for match in label_pattern.finditer(line):
            seen += 1
            if seen != date_index:
                continue
            value = line[match.end() :].strip(" :|\t")
            for end in range(len(value), 0, -1):
                try:
                    return datetime.strptime(value[:end].strip(), format_pattern).date()
                except ValueError:
                    pass
    raise ValueError(f"Could not find date after pattern {label_pattern.pattern!r}")

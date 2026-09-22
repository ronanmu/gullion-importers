from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from re import Pattern

from beancount.core import data

from .common import pack_extracted, unpack_extracted


@dataclass(frozen=True)
class CleanupRule:
    pattern: Pattern[str]
    match_on: str
    payee: str | None
    narration: str | None
    account: str | None
    tags: frozenset[str]
    metadata: dict[str, object]


class TransactionCleanup:
    """
    Clean and categorise transactions using regex rules loaded
    from a CSV file.

    Expected CSV columns:

        pattern
        match_on
        payee
        narration
        account
        tags
        metadata

    match_on may be:

        payee
        narration
        both

    Tags are separated by semicolons:

        food;groceries;household

    Metadata uses semicolon-separated key=value pairs:

        merchant-type=supermarket;recurring=true

    Existing transaction metadata and tags are preserved.

    If a metadata key already exists and the cleanup rule defines
    the same key, the value from the cleanup rule takes precedence.

    The first matching rule wins.
    """

    def __init__(
        self,
        rules_file: str | Path,
    ):
        self.rules_file = Path(rules_file)
        self.rules = self._load_rules()

    @staticmethod
    def _optional(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @staticmethod
    def _parse_tags(
        value: str | None,
    ) -> frozenset[str]:
        if not value or not value.strip():
            return frozenset()

        return frozenset(tag.strip() for tag in value.split(";") if tag.strip())

    @staticmethod
    def _parse_metadata_value(
        value: str,
    ) -> object:
        """
        Convert simple textual values into useful Beancount
        metadata types.

        Currently supports booleans; all other values remain
        strings.
        """

        lowered = value.lower()

        if lowered == "true":
            return True

        if lowered == "false":
            return False

        return value

    @classmethod
    def _parse_metadata(
        cls,
        value: str | None,
    ) -> dict[str, object]:
        """
        Parse:

            key=value;other=value

        into:

            {
                "key": "value",
                "other": "value",
            }
        """

        if not value or not value.strip():
            return {}

        metadata: dict[str, object] = {}

        for item in value.split(";"):
            item = item.strip()

            if not item:
                continue

            if "=" not in item:
                raise ValueError(f"Invalid metadata item {item!r}; expected key=value")

            key, raw_value = item.split("=", 1)

            key = key.strip()
            raw_value = raw_value.strip()

            if not key:
                raise ValueError("Metadata key cannot be empty")

            metadata[key] = cls._parse_metadata_value(raw_value)

        return metadata

    def _load_rules(
        self,
    ) -> list[CleanupRule]:
        rules: list[CleanupRule] = []

        with self.rules_file.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as file:
            reader = csv.DictReader(file)

            required = {
                "pattern",
                "match_on",
                "payee",
                "narration",
                "account",
                "tags",
                "metadata",
            }

            if not reader.fieldnames:
                raise ValueError(f"Cleanup rules file has no header: {self.rules_file}")

            missing = required - set(reader.fieldnames)

            if missing:
                raise ValueError(
                    "Cleanup rules file is missing columns: " + ", ".join(sorted(missing))
                )

            for lineno, row in enumerate(
                reader,
                start=2,
            ):
                pattern = (row["pattern"] or "").strip()

                if not pattern:
                    continue

                match_on = (row["match_on"] or "narration").strip().lower()

                if match_on not in {
                    "payee",
                    "narration",
                    "both",
                }:
                    raise ValueError(f"{self.rules_file}:{lineno}: invalid match_on {match_on!r}")

                try:
                    compiled_pattern = re.compile(
                        pattern,
                        re.IGNORECASE,
                    )
                except re.error as exc:
                    raise ValueError(
                        f"{self.rules_file}:{lineno}: invalid regex {pattern!r}"
                    ) from exc

                try:
                    metadata = self._parse_metadata(row["metadata"])
                except ValueError as exc:
                    raise ValueError(f"{self.rules_file}:{lineno}: {exc}") from exc

                rules.append(
                    CleanupRule(
                        pattern=compiled_pattern,
                        match_on=match_on,
                        payee=self._optional(row["payee"]),
                        narration=self._optional(row["narration"]),
                        account=self._optional(row["account"]),
                        tags=self._parse_tags(row["tags"]),
                        metadata=metadata,
                    )
                )

        return rules

    @staticmethod
    def _match_text(
        transaction: data.Transaction,
        match_on: str,
    ) -> str:
        payee = transaction.payee or ""
        narration = transaction.narration or ""

        if match_on == "payee":
            return payee

        if match_on == "narration":
            return narration

        return f"{payee} {narration}".strip()

    @staticmethod
    def _add_account(
        transaction: data.Transaction,
        account: str | None,
    ) -> data.Transaction:
        """
        Add an unresolved balancing posting when the rule specifies
        an account.

        Only one-sided transactions are categorised. Transactions
        already containing multiple postings may already represent
        transfers, FX matches, investments, or another resolved
        transaction.
        """

        if account is None:
            return transaction

        if len(transaction.postings) != 1:
            return transaction

        posting = data.Posting(
            account=account,
            units=None,
            cost=None,
            price=None,
            flag=None,
            meta=None,
        )

        return transaction._replace(
            postings=[
                *transaction.postings,
                posting,
            ]
        )

    def _apply_rule(
        self,
        transaction: data.Transaction,
        rule: CleanupRule,
    ) -> data.Transaction:
        """
        Apply a cleanup rule while preserving metadata and tags
        already present on the transaction.
        """

        # Start with all metadata added by the importer and any
        # earlier hooks, such as transaction-type, fx-rate,
        # fx-matched, reference, ticker, etc.
        meta = dict(transaction.meta or {})

        # Add rule metadata. A rule may deliberately override an
        # existing value with the same key, but unrelated metadata
        # is preserved.
        meta.update(rule.metadata)

        # Preserve existing tags and add the rule's tags.
        tags = (transaction.tags or frozenset()) | rule.tags

        transaction = transaction._replace(
            payee=(rule.payee if rule.payee is not None else transaction.payee),
            narration=(rule.narration if rule.narration is not None else transaction.narration),
            tags=tags,
            meta=meta,
        )

        return self._add_account(
            transaction,
            rule.account,
        )

    def _clean_transaction(
        self,
        transaction: data.Transaction,
    ) -> data.Transaction:
        """
        Apply the first matching cleanup rule.
        """

        for rule in self.rules:
            text = self._match_text(
                transaction,
                rule.match_on,
            )

            if not rule.pattern.search(text):
                continue

            return self._apply_rule(
                transaction,
                rule,
            )

        return transaction

    def hook(
        self,
        extracted,
        existing_entries,
    ):
        """
        Beangulp hook entry point.
        """

        result = []

        for raw_item in extracted:
            item = unpack_extracted(raw_item)
            cleaned_entries = []

            for entry in item.entries:
                if isinstance(entry, data.Transaction):
                    entry = self._clean_transaction(entry)

                cleaned_entries.append(entry)

            result.append(
                pack_extracted(
                    item,
                    cleaned_entries,
                )
            )

        return result

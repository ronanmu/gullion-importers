from __future__ import annotations

import re
from dataclasses import dataclass

from beancount.core import data
from beancount.core.amount import Amount


@dataclass
class FXCandidate:
    file_index: int
    entry_index: int
    transaction: data.Transaction
    posting: data.Posting


class FXMatcher:
    """
    Match opposite legs of foreign-exchange transactions.

    Expected input example:

        2026-01-10 * "Exchanged to GBP"
          transaction-type: "exchange"
          Assets:Bank:Revolut:EUR  -100.00 EUR

        2026-01-10 * "Exchanged to GBP"
          transaction-type: "exchange"
          Assets:Bank:Revolut:GBP    85.00 GBP

    becomes:

        2026-01-10 * "FX" "EUR → GBP"
          fx-matched: TRUE
          fx-rate: 1.176470588...
          Assets:Bank:Revolut:EUR  -100.00 EUR
          Assets:Bank:Revolut:GBP    85.00 GBP @ 1.176470588 EUR
    """

    TO_PATTERN = re.compile(
        r"\bExchanged\s+to\s+([A-Z]{3})\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        fx_accounts: set[str],
        date_tolerance_days: int = 1,
    ):
        self.fx_accounts = fx_accounts
        self.date_tolerance_days = date_tolerance_days

    @staticmethod
    def _is_exchange(
        transaction: data.Transaction,
    ) -> bool:
        meta = transaction.meta or {}

        transaction_type = meta.get("transaction-type")

        return isinstance(transaction_type, str) and transaction_type.lower() == "exchange"

    @classmethod
    def _target_currency(
        cls,
        transaction: data.Transaction,
    ) -> str | None:
        narration = transaction.narration or ""

        match = cls.TO_PATTERN.search(narration)

        if not match:
            return None

        return match.group(1).upper()

    def _collect_candidates(
        self,
        extracted_entries,
    ) -> list[FXCandidate]:
        candidates = []

        for file_index, (
            _filename,
            entries,
            _account,
            _importer,
        ) in enumerate(extracted_entries):
            for entry_index, entry in enumerate(entries):
                if not isinstance(
                    entry,
                    data.Transaction,
                ):
                    continue

                # Only reconcile one-sided transactions.
                if len(entry.postings) != 1:
                    continue

                if not self._is_exchange(entry):
                    continue

                posting = entry.postings[0]

                if posting.account not in self.fx_accounts:
                    continue

                if posting.units is None:
                    continue

                candidates.append(
                    FXCandidate(
                        file_index=file_index,
                        entry_index=entry_index,
                        transaction=entry,
                        posting=posting,
                    )
                )

        return candidates

    def _is_match(
        self,
        a: FXCandidate,
        b: FXCandidate,
    ) -> bool:
        # Don't match an entry with itself.
        if a.file_index == b.file_index and a.entry_index == b.entry_index:
            return False

        a_units = a.posting.units
        b_units = b.posting.units

        if a_units is None or b_units is None:
            return False

        # FX requires two different currencies.
        if a_units.currency == b_units.currency:
            return False

        # Both amounts must be non-zero.
        if a_units.number == 0 or b_units.number == 0:
            return False

        # One side must leave an account and the other arrive.
        if (a_units.number > 0) == (b_units.number > 0):
            return False

        a_target = self._target_currency(a.transaction)

        b_target = self._target_currency(b.transaction)

        # Both descriptions should identify the same destination
        # currency, e.g. both say "Exchanged to GBP".
        if not a_target or not b_target:
            return False

        if a_target != b_target:
            return False

        if a_units.number > 0:
            incoming = a
            outgoing = b
        else:
            incoming = b
            outgoing = a

        # The positive leg must be denominated in the target currency.
        if incoming.posting.units.currency != a_target:
            return False

        # The outgoing leg should not itself already be denominated
        # in the target currency.
        if outgoing.posting.units.currency == a_target:
            return False

        # Match on posting date only.
        date_difference = abs((a.transaction.date - b.transaction.date).days)

        if date_difference > self.date_tolerance_days:
            return False

        return True

    @staticmethod
    def _merge(
        a: FXCandidate,
        b: FXCandidate,
    ) -> data.Transaction:

        if a.posting.units.number < 0:
            outgoing = a
            incoming = b
        else:
            outgoing = b
            incoming = a

        source = outgoing.posting.units
        destination = incoming.posting.units

        # Express the price of one destination-currency unit
        # in the source currency.
        #
        # Example:
        #
        #   -100 EUR
        #    +85 GBP
        #
        # => 1 GBP = 100 / 85 EUR
        rate = abs(source.number) / abs(destination.number)

        priced_destination = incoming.posting._replace(
            price=Amount(
                rate,
                source.currency,
            )
        )

        meta = dict(outgoing.transaction.meta or {})

        # Preserve metadata from both legs.
        for key, value in (incoming.transaction.meta or {}).items():
            if key not in meta:
                meta[key] = value

            elif meta[key] != value:
                meta[f"fx-{key}"] = value

        meta["fx-matched"] = True
        meta["fx-rate"] = rate

        return outgoing.transaction._replace(
            date=max(
                outgoing.transaction.date,
                incoming.transaction.date,
            ),
            payee="FX",
            narration=(f"{source.currency} → {destination.currency}"),
            postings=[
                outgoing.posting,
                priced_destination,
            ],
            meta=meta,
        )

    def hook(
        self,
        extracted_entries,
        existing_entries,
    ):
        candidates = self._collect_candidates(extracted_entries)

        replacements = {}
        matched = set()

        for candidate in candidates:
            candidate_key = (
                candidate.file_index,
                candidate.entry_index,
            )

            if candidate_key in matched:
                continue

            possible_matches = []

            for other in candidates:
                other_key = (
                    other.file_index,
                    other.entry_index,
                )

                if other_key in matched:
                    continue

                if self._is_match(
                    candidate,
                    other,
                ):
                    possible_matches.append(other)

            #
            # Be conservative.
            #
            # If zero or multiple matches exist, leave the transactions
            # untouched for manual review.
            #
            if len(possible_matches) != 1:
                continue

            other = possible_matches[0]

            other_key = (
                other.file_index,
                other.entry_index,
            )

            merged = self._merge(
                candidate,
                other,
            )

            replacements[candidate_key] = merged
            replacements[other_key] = None

            matched.add(candidate_key)
            matched.add(other_key)

        result = []

        for file_index, (
            filename,
            entries,
            account,
            importer,
        ) in enumerate(extracted_entries):
            new_entries = []

            for entry_index, entry in enumerate(entries):
                key = (
                    file_index,
                    entry_index,
                )

                if key in replacements:
                    replacement = replacements[key]

                    if replacement is not None:
                        new_entries.append(replacement)

                    continue

                new_entries.append(entry)

            result.append(
                (
                    filename,
                    new_entries,
                    account,
                    importer,
                )
            )

        return result

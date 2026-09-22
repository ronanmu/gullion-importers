from __future__ import annotations

from dataclasses import dataclass

from beancount.core import data

from gullion_importers.hooks.common import pack_extracted, unpack_extracted


@dataclass
class TransferCandidate:
    file_index: int
    entry_index: int
    transaction: data.Transaction
    posting: data.Posting


class TransferMatcher:
    """
    Merge matching one-sided transactions between known own accounts.

    Example:
     Txn 1
        Assets:Bank:AIB:EUR       -500 EUR
     Txn 2
        Assets:Bank:Revolut:EUR    500 EUR

    becomes:
     Combined 1 & 2
        Assets:Bank:AIB:EUR       -500 EUR
        Assets:Bank:Revolut:EUR    500 EUR
    """

    def __init__(
        self,
        transfer_accounts: set[str],
        date_tolerance_days: int = 2,
        minimum_score: int = 80,
    ):
        self.transfer_accounts = transfer_accounts
        self.date_tolerance_days = date_tolerance_days
        self.minimum_score = minimum_score

    def _candidate_score(
        self,
        a: TransferCandidate,
        b: TransferCandidate,
    ) -> int:
        pa = a.posting
        pb = b.posting

        # Never match a transaction to itself.
        if a.file_index == b.file_index and a.entry_index == b.entry_index:
            return 0

        # Transfers must move between different accounts.
        if pa.account == pb.account:
            return 0

        if pa.units is None or pb.units is None:
            return 0

        # Same-currency matcher only.
        if pa.units.currency != pb.units.currency:
            return 0

        # Must be equal and opposite.
        if pa.units.number != -pb.units.number:
            return 0

        date_difference = abs((a.transaction.date - b.transaction.date).days)

        if date_difference > self.date_tolerance_days:
            return 0

        score = 50  # exact equal/opposite amount

        if date_difference == 0:
            score += 30
        elif date_difference == 1:
            score += 20
        else:
            score += 10

        text = " ".join(
            value
            for value in (
                a.transaction.payee,
                a.transaction.narration,
                b.transaction.payee,
                b.transaction.narration,
            )
            if value
        ).upper()

        transfer_terms = (
            "TRANSFER",
            "BANK TRANSFER",
            "FASTER PAYMENT",
            "SEPA",
            "CURRENCY TRANSFER",
            "REVOLUT",
            "STARLING",
            "AIB",
        )

        if any(term in text for term in transfer_terms):
            score += 20

        return score

    def _collect_candidates(
        self,
        extracted_entries,
    ) -> list[TransferCandidate]:
        candidates = []

        for file_index, (_, entries, _, _) in enumerate(extracted_entries):
            for entry_index, entry in enumerate(entries):
                if not isinstance(entry, data.Transaction):
                    continue

                # Only operate on uncategorised, one-sided transactions.
                if len(entry.postings) != 1:
                    continue

                posting = entry.postings[0]

                if posting.account not in self.transfer_accounts:
                    continue

                if posting.units is None:
                    continue

                candidates.append(
                    TransferCandidate(
                        file_index=file_index,
                        entry_index=entry_index,
                        transaction=entry,
                        posting=posting,
                    )
                )

        return candidates

    @staticmethod
    def _merge(
        a: TransferCandidate,
        b: TransferCandidate,
    ) -> data.Transaction:
        # Choose the later date, which usually corresponds to the
        # destination account's posted/settled date.
        transaction_date = max(
            a.transaction.date,
            b.transaction.date,
        )

        narrations = []

        for transaction in (
            a.transaction,
            b.transaction,
        ):
            if transaction.narration and transaction.narration not in narrations:
                narrations.append(transaction.narration)

        narration = " / ".join(narrations)

        meta = dict(a.transaction.meta or {})

        # Preserve useful metadata from both sides without silently
        # overwriting duplicate keys.
        for key, value in (b.transaction.meta or {}).items():
            if key not in meta:
                meta[key] = value
            elif meta[key] != value:
                meta[f"transfer-{key}"] = value

        meta["transfer-matched"] = True

        return a.transaction._replace(
            date=transaction_date,
            payee="Transfer",
            narration=narration,
            postings=[
                a.posting,
                b.posting,
            ],
            meta=meta,
        )

    def hook(
        self,
        extracted_entries,
        existing_entries,
    ):
        candidates = self._collect_candidates(extracted_entries)

        matches = {}
        already_matched = set()

        for candidate in candidates:
            key = (
                candidate.file_index,
                candidate.entry_index,
            )

            if key in already_matched:
                continue

            possible_matches = []

            for other in candidates:
                other_key = (
                    other.file_index,
                    other.entry_index,
                )

                if other_key in already_matched:
                    continue

                score = self._candidate_score(
                    candidate,
                    other,
                )

                if score >= self.minimum_score:
                    possible_matches.append((score, other))

            if not possible_matches:
                continue

            possible_matches.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            # Ambiguous match:
            #
            # If the two best candidates have the same score, leave
            # everything untouched for manual review.
            if len(possible_matches) > 1 and possible_matches[0][0] == possible_matches[1][0]:
                continue

            _, other = possible_matches[0]

            other_key = (
                other.file_index,
                other.entry_index,
            )

            merged = self._merge(
                candidate,
                other,
            )

            # Keep merged transaction in the position of candidate,
            # and remove the matching transaction later.
            matches[key] = merged
            matches[other_key] = None

            already_matched.add(key)
            already_matched.add(other_key)

        result = []

        for file_index, raw_item in enumerate(extracted_entries):
            new_entries = []
            item = unpack_extracted(raw_item)
            entries = item.entries

            for entry_index, entry in enumerate(entries):
                key = (
                    file_index,
                    entry_index,
                )

                if key in matches:
                    replacement = matches[key]

                    if replacement is not None:
                        new_entries.append(replacement)

                    continue

                new_entries.append(entry)

            result.append(
                pack_extracted(
                    item,
                    new_entries,
                )
            )

        return result

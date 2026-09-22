# Gullion Beancount Importers

[Beangulp](https://github.com/beancount/beangulp) importers for the [Beancount](https://github.com/beancount/beancount) plain text accounting platform, covering some common UK & Ireland financial institutions.

This library is a collection of Beancount importers and reconciliation hooks for converting exports from banks, credit-card providers, investment platforms, and cryptocurrency services into Beancount entries. The project targets **Beancount 3.2.3** and a recent **Beangulp 0.2.x / upstream API** as some importer features used here, including `csvbase.CreditOrDebit` have differed between published Beangulp releases and the upstream repository, therefore it is recommended to install the named Beangulp version or Git commit specified in the `project.toml`

## Background

The importers are designed around a few common principles:
- keep source data as faithful as possible
- use shared generic metadata keys across institutions
- avoid prematurely categorising transfers as income or expenses
- leave ambiguous transactions unresolved rather than guessing

Bank transfers, investment top-ups and similar movments can be imported as one-sided transactions so that they can later be reconciled by a shared transfer or FX matching hooks.

This library is intended for used with **Python 3.11 or later**. Importers are tested using `pytest` and santisised fixtures are kept under `tests/fixtures/` so that the test suite does not contain real account numbers or transaction references.


## Supported institutions

This library supports imports from the following financial institutions and export formats

| Institution | Product | Region | Inupt format | Notes |
|-------------|---------|--------|--------------|-------|
| [AIB](https://www.aib.ie/) | 💶 Current Accout | Ireland | CSV | Supports AIB transaction-type prefixes, such as contactless, point-of-sale, plus foreign/local currency metadata where present. |
| [American Express](https://www.americanexpress.com/en-gb/) | 💳 Credit Card | UK | CSV | Retains foreign exchange spend |
| [Barclaycard](https://www.barclaycard.co.uk/personal) | 💳 Credit Card | UK | CSV | Supports separate purchase & payment amound colums |
| [Coinbase](https://www.barclaycard.co.uk/personal) | ₿ Crypto Account | Global | CSV | Supports crypto quantities, acquisition costs, fees and fiat deposits |
| [Dankse Bank](https://danskebank.co.uk/personal) | 💷 Current Account | UK | CSV | Supports Dankse Bank NI (formerly Northern Bank) |
| [Freetrade](https://freetrade.io/) | 📈 Investment Account | UK, US | CSV | Supports GBP and foreign-currency securities, stamp duty, FX fees, and one-sided topups suitable for transfer matching. Information and statement entries are ignored  |
| [Starling Bank](https://www.starlingbank.com/) | 💷 Current Account | UK | CSV | Supports GBP, EUR and Joint accounts |
| [Revolut](https://www.revolut.com) | 💱 Current Account | Global | CSV | Supports any Revolut currency. Reverted transactions are ignored. FX transactions can be reconciled with FX matching hook. |


## Features

Importers generally preserve the transaction information supplied by the financial institution while keeping entries suitable for further processing by shared hooks.

Where possible, metadata uses common names across instituions, for example:

```text
transaction-type
category
reference
country
ticker
isin
```

Institution-specific medata is used only where the field has no useful generic equivalent.

This library also includes shared reconciliation hooks for:

- matching transfers between accounts
- matching the two sides of foreign-exchange transactions
- cleaning payees and narrations
- deterministic categorisation using regular-expressions and defined ruleset
- optional categorisation using [smart_importer](https://github.com/beancount/smart_importer)

## Installation

Clone the repository:

```bash
git clone https://github.com/ronanmu/gullion-importers.git
cd gullion-importers
```

Create a new virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate

python3 -m pip install -e ".[dev]"
```

Running tests with `pytest` 

```bash
pytest -v
```

## Usage

This library contains account importers, as well as hooks for use within the `beangulp` pipeline. Each importer supports parameterised inputs enabling customisation of account names and currencies. 

### Account importers

How to use in `beangulp` importer:

```python
from beangulp import ingest

from gullion_importers.importers import aib, amex, revolut, freetrade
from gullion_importers.hooks import transfers, fxmatcher

# Importers for AIB, Revolut EUR and GBP accounts & Freetrade GIA
importers = [
    aib.AIBCurrentAccountImporter(account="Assets:AIB:Current", currency="EUR"),
    amex.AmericanExpressImporter(account="Liabilities:CreditCard:Amex", currency="GBP"),
    revolut.RevolutCurrentAccountImporter(account="Assets:Revolut:EUR", currency="EUR"),
    revolut.RevolutCurrentAccountImporter(account="Assets:Revolut:GBP", currency="GBP"),
    freetrade.FreetradeImporter(
        account_root="Assets:Investments:Freetrade",
        cash_account="Assets:Investments:Freetrade:Cash",
        dividend_income_account="Income:Investments:Dividends",
        interest_income_account="Income:Investments:Interest",
        stamp_duty_account="Expenses:Investment:StampDuty",
        fx_fee_account="Expenses:Investment:FXFees",
    )
]

# Hooks to match own-account transfers between named accounts and
# FX matching between EUR and GBP accounts
hooks = [
    transfers.TransferMatcher(
        transfer_accounts={
            "Assets:AIB:Current",
            "Assets:Revolut:EUR",
        },
        date_tolerance_days=2,
        minmum_score=80,
    ).hook,
    fxmatcher.FXMatcher(
        fx_accounts={
            "Assets:Revolut:EUR",
            "Assets:Revolut:GBP"
        },
        date_tolerance_days=1,
    ).hook
]

if __name__ == "__main__";
    ingest.main(
        importers,
        hooks=hooks
    )
```

### Transfer matching hook

---

This library includes an account transfer matcher hook for reconciling same-currency transfers betweeen your own accounts. This is useful for funds flowing where both institutions export their side of the transfer as separate one-sided transactions.

The hook looks for transactions that:

- are on different configured accounts
- use the same currency
- have equal and opposite amounts
- occur within an acceptable date tolerance
- optionally contain a transfer-related wording in the description, e.g. `TRANSFER`, `FASTER PAYMENT`, `SEPA`

When a sufficiently confident match is found the two entries are replaced with a single Beancount transation containing both postings.

#### Example configuration

```python
from gullion_importers.hooks.transfers import (
    TransferMatcher,
)

transfer_matcher = TransferMatcher(
    transfer_accounts={
        "Assets:Bank:AIB:EUR",
        "Assets:Bank:Revolut:EUR",
        "Assets:Bank:Revolut:GBP",
        "Assets:Bank:Starling:EUR",
        "Assets:Bank:Starling:GBP",
    },
    date_tolerance_days=2,
    minimum_score=80,
)
```

Then add the hook to your Beangulp configuration:

```python
HOOKS = [transfer_matcher.hook]
```
Transfer matching should typically run before payee/narration cleanup and categorisation, so it can inspect the original importer metadata and transaction descriptions.

#### Example transfers

Given a source account transaction of:

```text
2026-09-01 * "Transfer to Revolut"
  Assets:Bank:AIB:EUR  -500.00 EUR
```

and recipient account transaction of:

```text
2026-09-02 * "Bank transfer received"
  Assets:Bank:Revolut:EUR  500.00 EUR
```
this hook will produce:

```text
2026-09-02 * "Transfer" "Transfer to Revolut / Bank transfer received"
  transfer-matched: true
  Assets:Bank:AIB:EUR       -500.00 EUR
  Assets:Bank:Revolut:EUR    500.00 EUR
```

### Foreign Exchange matching hook

---

The Foreign Exchange (FX) hook reconciles the two sides of a foreign-exchange transaciton when they are imported separately from the same or different currency accounts.

This is useful for platforms such as Revolut, where an exhcange will appear as two independent one-sided transactions:

```
# Listing from a Revolut EUR account import
2025-06-01 * "Exchanged to GBP"
  transaction-type: "exchange"
  Assets:Revolut:EUR    - 100.00 EUR
```

and

```
# Listing from a Revolut GBP account import
2025-06-01 * "Exchanged to GBP"
  transaciton-type: "exchange"
  Assets:Revolut:GBP    84.50 GBP
```

The matcher combines these into a single Beancount transaction, and adds an explicit price to the destination posting:

```
2025-06-01 * "FX" "EUR -> GBP"
  transaction-type: "exchange"
  fx-matched: true
  fx-rate: 1.1834
  Assets:Revolut:EUR    - 100.00 EUR
  Assets:Revolut:GBP      84.50 GBP @ 1.1834
```

#### Matching rules

The matcher is intentionally conservative. A pair of transactions is only merged when all of the following conditions are satisifed:

- both transactions contain exactly one posting
- both postings belong to accounts configured as FX accounts in the hook
- both transactions have `transaction-type: "exchange"`
- the narration identifies the target currency using a description such as `Exchanged to GBP`
- both transactions identifiy the same target currecncy
- the postings use different currencies
- one posting is positive, the other negative
- the posting dates are within a configured date tolerance
- exactly one ambiguous matching candidate exists

If multiple possible matches exist, the hook leaves the transactions unchanged rather than guessing. This is deliberate; false negatives can be manually reviewed, while an incorrectly merged FX transaction can be harder to detect and unmatch later.

### Transaction cleanup hook

---

The transaction clean up hook applies configurable regular-expression rules to imported transactions after they have been parsed by the individual importers.

It can be used to:
- normalise payees
- replace or simplify narrations
- categorise one-sided transactions by adding an expense or income account
- add tags
- add metadata
- preserve metadata and tags already added by importers or earlier hooks

Rules are loaded from a name CSV file, which keeps institution-specific cleanup and categorisation outside the importer code itself.

#### Configuration

Create a CSV file containing one cleanup rule per row. The file must contain
these columns:

| Column | Description |
|--------|-------------|
| `pattern` | A case-insensitive regular expression used to identify a transaction. Blank patterns are ignored. |
| `match_on` | The text to search: `payee`, `narration`, or `both`. If blank, `narration` is used. |
| `payee` | Replacement payee. Leave blank to preserve the imported payee. |
| `narration` | Replacement narration. Leave blank to preserve the imported narration. |
| `account` | Account to add as an unresolved balancing posting to a one-sided transaction. Leave blank to add no account. |
| `tags` | Tags to add, separated by semicolons, for example `food;groceries`. |
| `metadata` | Metadata to add as semicolon-separated `key=value` pairs, for example `merchant-type=supermarket;recurring=true`. The values `true` and `false` are parsed as booleans; other values remain strings. |

For example, save the following as `cleanup-rules.csv`:

```csv
pattern,match_on,payee,narration,account,tags,metadata
NETFLIX,both,Netflix,Subscription,Expenses:Entertainment:Subscriptions,subscription;recurring,service=netflix;recurring=true
TESCO,payee,Tesco,,Expenses:Food:Groceries,food;groceries,merchant-type=supermarket
AMAZON PRIME,both,Amazon Prime,Subscription,Expenses:Entertainment:Subscriptions,subscription,service=amazon-prime
AMAZON|AMZN,both,Amazon,,Expenses:Shopping:General,shopping,merchant=amazon
REVOLUT FX,narration,,,,,source=revolut;reviewed=true
```

The rules are evaluated from top to bottom and the first matching rule wins.
Put more specific patterns before broader patterns, such as `AMAZON PRIME`
before `AMAZON|AMZN`. Existing transaction metadata and tags are preserved;
metadata keys supplied by the matching rule replace existing values with the
same key. An `account` is only added when the transaction has one posting, so
already-balanced transfers and FX transactions are left unchanged.

Configure the hook with the path to the rules file and add its bound `hook`
method to the Beangulp hook list:

```python
from gullion_importers.hooks.cleanup import TransactionCleanup

transaction_cleanup = TransactionCleanup(
    rules_file="config/cleanup-rules.csv",
)

HOOKS = [
    transaction_cleanup.hook,
]
```

When combining it with the reconciliation hooks above, run transaction
cleanup after transfer and FX matching if the cleanup rules should operate on
the final merged transactions. Run it before categorisation rules that depend
on the payee or narration produced by this hook.
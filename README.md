# Gullion Beancount Importers

Beangulp/Beancount importers for some common UK & Ireland financial institutions.

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

Where possible, metadata uses common names across instituions for example:

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
- mathcing the two sides of foreign-exchange transactions
- cleaning payees and narrations
- deterministic categorisation using regular-expressions and defined ruleset
- optional categorisation using `smart_importer`

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

Running tests

```bash
pytest -v
```

## Usage

This library contains account importers, as well as hooks for use within the `beangulp` pipeline.

### Account importers

How to use in `beangulp` importer:

```python
from beangulp import ingest

from gullion_importers.importers import aib, amex, freetrade

IMPORTERS = [
    aib.AIBCurrentAccountImporter(account="Assets:AIB:Current", currency="EUR"),
    amex.AmericanExpressImporter(account="Liabilities:CreditCard:Amex", currency="GBP")
    freetrade.FreetradeImporter(
        account_root="Assets:Investments:Freetrade",
        cash_account="Assets:Investments:Freetrade:Cash",
        dividend_income_account="Income:Investments:Dividends",
        interest_income_account="Income:Investments:Interest",
        stamp_duty_account="Expenses:Investment:StampDuty",
        fx_fee_account="Expenses:Investment:FXFees",
    )
]

HOOKS = [
    # Future hooks listed here
]

if __name__ == "__main__";
    ingest.main(
        IMPORTERS,
        hooks=HOOKS
    )
```
### Transfer matching hook

This library includes an own account transfer matcher hook for reconciling same-currency transfers betweeen your own accounts.

This is useful for funds flowing such as:

```
AIB EUR -> Revolut EUR
Revolut GBP -> Starling GBP
```

where both institutions export their side of the transfer as separate one-sided transactions.

The hook looks for transactions that:

- are on different configured accounts
- use the same currency
- have equal and opposite amounts
- occur within an acceptable date tolerance
- optionally contain a transfer-related wording in the description, e.g. `TRANSFER`, `FASTER PAYMENT`, `SEPA`

When a sufficiently confident match is found the two entries are replaced with a single Beancount transation containing both postings.

### Example configuration

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
Transfer matching should typically run before payee/narration cleanup and categorisation, so it can inspec the original importer metadata and transaction descriptions.

### Example transfers

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



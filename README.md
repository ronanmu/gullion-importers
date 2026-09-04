# Gullion Beancount Importers

Beangulp/Beancount importers for some common UK & Ireland financial institutions. 

Currently supported:

- AIB current accounts
- Starling GBP & EUR current accounts
- Revolut multi-currency current accounts
- American Express UK credit cards
- Coinbase crypto asset accounts

## Features

- Beancount 3 / Beangulp compatible
- AIB current account CSV support
- Starling GBP and EUR CSV support
- Revolut EUR/GBP/AED and other currency CSV support
- Revolut reverted transactions ignored
- American Express UK card CSV support
- Coinbase CSV support
- Useful institution-specific metadata retained
- pytest test suite with sanitised fixtures

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
from gullion_importers.importers.aib import (
    AIBCurrentAccountImporter,
)

CONFIG = [
    AIBCurrentAccountImporter(
        account="Assets:AIB:Current",
    )
]
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



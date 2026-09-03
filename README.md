# Gullion Beancount Importers

Beangulp/Beancount importers for some common UK & Ireland financial institutions. 

Currently supported:

- AIB current accounts
- Starling GBP & EUR current accounts
- Revolut multi-currency current accounts

## Features

- Beancount 3 / Beangulp compatible
- AIB current account CSV support
- Starling GBP and EUR CSV support
- Revolut EUR/GBP/AED and other currency CSV support
- Revolut reverted transactions ignored
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

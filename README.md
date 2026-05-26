# ctrader-fixapi

Simple cTrader FIX demo scripts for:

- QUOTE market-data testing via `quote_script.py`
- TRADE positions and order testing via `trade_script.py`
- Multi-account TRADE runs via `multitrade.py`

## Config

The repo reads connection settings from `.env` for single-account runs and from
`accounts.csv` for multi-account runs.

Current example config is prepared for cTrader demo account `2228494`:

```env
FIX_USERNAME=2228494
FIX_PASSWORD=98814001
FIX_SENDER_COMP_ID=demo.deriv.2228494
FIX_TARGET_COMP_ID=cServer

QUOTE_HOST=demo-uk-eqx-01.p.ctrader.com
QUOTE_PORT=5211
QUOTE_SSL=true
QUOTE_SENDER_SUB_ID=QUOTE
QUOTE_TARGET_SUB_ID=QUOTE

TRADE_HOST=demo-uk-eqx-01.p.ctrader.com
TRADE_PORT=5202
TRADE_SSL=false
TRADE_SENDER_SUB_ID=TRADE
TRADE_TARGET_SUB_ID=TRADE
```

Alternative ports supported by the endpoint details you shared:

- QUOTE SSL: `5211`
- QUOTE plain text: `5201`
- TRADE SSL: `5212`
- TRADE plain text: `5202`

If you switch ports, keep `*_SSL=true` for SSL ports and `*_SSL=false` for
plain-text ports.

## Run

This repo currently uses bundled packages under `venv/lib/python3.12/site-packages`,
so the safest command is:

```bash
cd /home/vedant/ctrader-fixapi
PYTHONPATH=/home/vedant/ctrader-fixapi/venv/lib/python3.12/site-packages python3 quote_script.py
PYTHONPATH=/home/vedant/ctrader-fixapi/venv/lib/python3.12/site-packages python3 trade_script.py
PYTHONPATH=/home/vedant/ctrader-fixapi/venv/lib/python3.12/site-packages python3 multitrade.py
```

## Usage

Use `quote_script.py` to test prices first. It logs in to the QUOTE session,
subscribes to market data, and prints bid/ask updates.

Use `trade_script.py` for single-account TRADE actions. Start with:

```env
TRADE_ACTION=positions
TRADE_SYMBOL=BTCUSD
QUOTE_SYMBOL=BTCUSD
SYMBOL_BTCUSD_ID=101
```

After positions work, you can switch to:

- `TRADE_ACTION=buy`
- `TRADE_ACTION=sell`
- `TRADE_ACTION=close`

Use `multitrade.py` when you want the same TRADE flow driven from `accounts.csv`.

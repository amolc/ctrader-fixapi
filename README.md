# cTrader FIX API

Simple cTrader FIX API client using ejtraderCT library.

## Files

- **fixaccount.py** - Account wrapper with connect, positions, buy/sell
- **buy.py** - Place buy orders on all accounts
- **main.py** - Main script with positions and quotes
- **accounts.csv** - Account credentials

## Quick Start

1. Setup virtual environment:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Add accounts to `accounts.csv`:
```csv
ACCOUNT_NAME,FIX_USERNAME,FIX_PASSWORD,FIX_SENDER_COMP_ID,TRADE_HOST,TRADE_PORT
account_123456,123456,password,demo.deriv.123456,demo-uk-eqx-01.p.ctrader.com,5202
```

3. Run buy orders:
```bash
python buy.py
```

## Usage

### Get Positions
```python
from fixaccount import FixAccount
import pandas as pd

config = pd.read_csv('accounts.csv').iloc[0].to_dict()
account = FixAccount(config)

if account.connect():
    positions = account.get_positions()
    print(positions[['account', 'name', 'side', 'amount', 'price']])
    account.disconnect()
```

### Place Buy Order
```python
result = account.buy_market('BTCUSD', 0.01)
print(result)
# {'account': 'account_123456', 'trade_id': '...', 'executed': True, 'position_id': '...', 'fill_price': 77840.60}
```

## API Reference

### FixAccount
- `connect(wait_seconds=3)` - Connect to cTrader
- `disconnect()` - Logout
- `get_positions()` - Get positions DataFrame (with account column)
- `buy_market(symbol, volume)` - Place market buy order
- `sell_market(symbol, volume)` - Place market sell order

### buy.py
- `buy_market_single(account, symbol, volume)` - Buy on single account
- `buy_all_accounts(symbol, volume)` - Buy on all accounts

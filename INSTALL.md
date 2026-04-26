# Multi-Account FIX API Trading Client - Installation & Usage Guide

## Overview

The `multitrade.py` module provides functionality to execute trades across multiple cTrader accounts simultaneously using the FIX (Financial Information eXchange) protocol. It supports operations including querying positions, placing buy/sell orders, and closing positions.

## Key Components

- **load_env_file**: Load environment variables from .env file
- **get_env**: Retrieve environment variables with defaults and validation
- **str_to_bool**: Convert string values to boolean
- **value_at**: Safely access list elements by index
- **AccountSession**: Represents a single trading account session with FIX connection
- **MultiTradeManager**: Manages multiple account sessions and coordinates trading operations
- **load_accounts_from_csv**: Load account configurations from CSV file

## Installation

### Prerequisites

- Python 3.8+
- `ctrader_fix` module (FIX protocol implementation)
- Twisted reactor (for asynchronous I/O)

### Dependencies

```bash
pip install ctrader_fix
```

## Usage

### Basic Usage

```bash
# Set environment variable for CSV path
export MULTI_TRADE_CSV="accounts.csv"

# Run the trading client
python multitrade.py
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MULTI_TRADE_CSV` | Path to CSV file containing account configurations | `accounts.csv` |

### CSV Format

#### Required Columns

| Column | Description |
|--------|-------------|
| `FIX_USERNAME` | Account username for FIX authentication |
| `FIX_PASSWORD` | Account password for FIX authentication |
| `FIX_SENDER_COMP_ID` | Sender Comp ID for FIX protocol |
| `TRADE_HOST` | FIX server hostname or IP address |
| `TRADE_PORT` | FIX server port number |
| `TRADE_SENDER_SUB_ID` | Sender Sub ID for FIX protocol |
| `TRADE_TARGET_SUB_ID` | Target Sub ID for FIX protocol |

#### Optional Columns

| Column | Description | Default |
|--------|-------------|---------|
| `ACCOUNT_NAME` | Human-readable account name | `FIX_USERNAME` |
| `TRADE_ACTION` | Action to perform: `positions`, `buy`, `sell`, `close` | `positions` |
| `TRADE_SYMBOL` | Trading symbol | `BTCUSD` |
| `TRADE_QTY` | Trade quantity for buy/sell | `0.01` |
| `TRADE_TIMEOUT` | Session timeout in seconds | `20` |
| `FIX_RESET_SEQ_NUM` | Reset sequence numbers on logon | `true` |
| `TRADE_SSL` | Use SSL connection | `false` |
| `TRADE_POSITION_ID` | Specific position ID to close | - |
| `FIX_BEGIN_STRING` | FIX protocol version | `FIX.4.4` |
| `FIX_TARGET_COMP_ID` | Target Comp ID | `cServer` |
| `FIX_HEARTBEAT` | Heartbeat interval in seconds | `30` |

### CSV Example

```csv
FIX_USERNAME,FIX_PASSWORD,FIX_SENDER_COMP_ID,TRADE_HOST,TRADE_PORT,TRADE_SENDER_SUB_ID,TRADE_TARGET_SUB_ID,TRADE_ACTION,TRADE_SYMBOL,TRADE_QTY
user1,pass1,sender1,fix.ctrader.com,5001,sub1,target1,buy,BTCUSD,0.01
user2,pass2,sender2,fix.ctrader.com,5001,sub2,target2,positions,BTCUSD,0.01
```

## API Reference

### Module-Level Functions

#### `load_env_file(path: str) -> None`

Load environment variables from a .env file.

Parses a dotenv-style file and sets environment variables. Lines starting with '#' are treated as comments and ignored. Variables already set in the environment are not overwritten.

**Args:**
- `path`: Path to the .env file to load.

**Returns:**
- `None`

**Example:**
```python
>>> load_env_file(".env")
# Loads KEY=value pairs from .env into os.environ
```

---

#### `get_env(name: str, default: str | None = None, required: bool = False) -> str`

Retrieve environment variable with optional default value and validation.

Safely retrieves environment variables with support for default values and required field validation. Raises ValueError if a required variable is missing or empty.

**Args:**
- `name`: Name of the environment variable to retrieve.
- `default`: Default value if variable is not set. Defaults to `None`.
- `required`: If `True`, raises ValueError when variable is missing/empty. Defaults to `False`.

**Returns:**
- `str`: The environment variable value, default, or empty string.

**Raises:**
- `ValueError`: If `required=True` and the variable is missing or empty.

**Example:**
```python
>>> get_env("API_KEY", required=True)
'secret_key_value'
>>> get_env("OPTIONAL_VAR", "default_value")
'default_value'
```

---

#### `str_to_bool(value: str | bool) -> bool`

Convert a string or boolean value to boolean.

Converts various string representations to boolean values. Case-insensitive matching for: '1', 'true', 'yes', 'on', 'y'. All other values return False.

**Args:**
- `value`: Value to convert. Can be a string or boolean.

**Returns:**
- `bool`: True if value represents a truthy string/bool, False otherwise.

**Examples:**
```python
>>> str_to_bool("true")
True
>>> str_to_bool("FALSE")
False
>>> str_to_bool(True)
True
>>> str_to_bool("yes")
True
>>> str_to_bool("no")
False
```

---

#### `value_at(value, idx: int)`

Safely access an element from a list by index.

Provides safe list element access with bounds checking. Returns None if index is out of bounds or value is not a list.

**Args:**
- `value`: List to access. If not a list, returns None.
- `idx`: Zero-based index of the element to retrieve.

**Returns:**
- The element at the specified index, or None if out of bounds or if value is not a list.

**Examples:**
```python
>>> value_at(["a", "b", "c"], 1)
'b'
>>> value_at(["a", "b"], 5)
None
>>> value_at("not a list", 0)
None
```

---

#### `load_accounts_from_csv(csv_path: str) -> list[AccountSession]`

Load account configurations from a CSV file.

Reads account configurations from a CSV file, validates required columns, and creates AccountSession instances for each valid row.

**Args:**
- `csv_path`: Path to the CSV file containing account configurations.

**Returns:**
- `list[AccountSession]`: List of initialized AccountSession instances.

**Raises:**
- `ValueError`: If CSV file not found, required columns missing, or invalid TRADE_ACTION.

**Example:**
```python
>>> sessions = load_accounts_from_csv("accounts.csv")
>>> len(sessions)
3
```

---

#### `main() -> int`

Main entry point for the multi-account trading client.

Loads environment variables from .env file, reads account configurations from CSV, initializes the MultiTradeManager, and starts trading operations.

**Environment Variables:**
- `MULTI_TRADE_CSV`: Path to accounts CSV file (default: `accounts.csv`).

**Returns:**
- `int`: Exit code - 0 for success, 1 for error.

**Example:**
```python
>>> import sys
>>> sys.exit(main())
```

---

### Classes

#### `AccountSession`

Represents a single trading account session with FIX connection.

This class encapsulates all configuration and state for a cTrader account connection via the FIX protocol. It handles account identification, trade configuration, and session state management.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `row` | dict | Dictionary containing raw account configuration from CSV |
| `account_name` | str | Human-readable account identifier |
| `action` | str | Trading action to perform (`positions`, `buy`, `sell`, `close`) |
| `symbol_requested` | str | Original symbol string from configuration |
| `symbol` | str | Resolved symbol ID for trading |
| `quantity` | float | Trade quantity for buy/sell operations |
| `timeout_seconds` | int | Session timeout before auto-disconnect |
| `reset_seq_num` | bool | Whether to reset FIX sequence numbers on logon |
| `close_position_id` | str | Specific position ID to close (optional) |
| `trade_config` | dict | Dictionary of FIX connection parameters |
| `client` | Client | FIX protocol client instance |
| `logged_in` | bool | Whether the session has completed logon |
| `completed` | bool | Whether the session has finished all operations |
| `sent_id` | str | Most recently sent message ID for correlation |
| `position_reports_count` | int | Number of position reports received |
| `collected_positions` | list | List of collected position dictionaries |
| `timeout_call` | object | Twisted timeout call handle |
| `positions_finish_call` | object | Twisted delayed call for position operations |

**Example:**
```python
>>> row = {
...     "FIX_USERNAME": "user123",
...     "FIX_PASSWORD": "secret",
...     "FIX_SENDER_COMP_ID": "sender1",
...     "TRADE_HOST": "fix.ctrader.com",
...     "TRADE_PORT": "5001",
...     "TRADE_SENDER_SUB_ID": "sub1",
...     "TRADE_TARGET_SUB_ID": "target1",
...     "TRADE_ACTION": "buy",
...     "TRADE_SYMBOL": "BTCUSD",
...     "TRADE_QTY": "0.01",
... }
>>> session = AccountSession(row)
>>> session.account_name
'user123'
```

---

##### `AccountSession.__init__(row: dict)`

Initialize account session from CSV row data.

**Args:**
- `row`: Dictionary containing account configuration from CSV. Must include required FIX connection parameters.

---

##### `AccountSession.resolve_symbol_id(symbol: str) -> str`

Resolve symbol name to trading ID.

Checks if symbol is a numeric ID, then looks for environment variable mapping (SYMBOL_{SYMBOL}_ID), otherwise returns the symbol as-is.

**Args:**
- `symbol`: Symbol string to resolve.

**Returns:**
- `str`: Resolved symbol ID for trading.

**Examples:**
```python
>>> session.resolve_symbol_id("12345")
'12345'
>>> session.resolve_symbol_id("BTCUSD")
'BTCUSD'  # or value from SYMBOL_BTCUSD_ID env var
```

---

#### `MultiTradeManager`

Manages multiple account sessions and coordinates trading operations.

This class orchestrates trading operations across multiple cTrader accounts simultaneously. It handles connection management, message routing, and lifecycle management for all account sessions.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `sessions` | list[AccountSession] | List of AccountSession instances to manage |

**Example:**
```python
>>> sessions = load_accounts_from_csv("accounts.csv")
>>> manager = MultiTradeManager(sessions)
>>> manager.start()
```

---

##### `MultiTradeManager.__init__(sessions: list[AccountSession])`

Initialize the manager with a list of account sessions.

**Args:**
- `sessions`: List of AccountSession instances to coordinate.

---

##### `MultiTradeManager.start() -> None`

Start all account sessions and begin the FIX event loop.

Initializes connections for all configured accounts, sets up callbacks, and starts the Twisted reactor event loop. This method blocks until all sessions complete or timeout.

**Returns:**
- `None`

**Note:**
This method blocks and runs the Twisted reactor. It will not return until all trading operations complete or timeout.

---

##### `MultiTradeManager.on_connected(session: AccountSession, client: Client) -> None`

Handle FIX connection establishment for a session.

Called when the FIX client successfully establishes a TCP connection. Logs connection details and sends the FIX logon message.

**Args:**
- `session`: AccountSession that connected.
- `client`: FIX client instance.

**Returns:**
- `None`

---

##### `MultiTradeManager.on_disconnected(session: AccountSession, client: Client, reason) -> None`

Handle FIX disconnection for a session.

Called when the FIX client disconnects from the server. Marks the session as completed and triggers shutdown if all sessions are done.

**Args:**
- `session`: AccountSession that disconnected.
- `client`: FIX client instance.
- `reason`: Disconnection reason string.

**Returns:**
- `None`

---

## Trading Actions

The trading actions are specified via the `TRADE_ACTION` column in the CSV file. Each action has specific behavior and requirements.

---

### `positions`

Query all open positions for the account.

**Behavior:**
- Sends a `RequestForPositions` FIX message to retrieve all open positions
- Collects position reports including symbol, quantity, and settlement price
- Automatically completes after receiving all position reports or timeout

**Returns:**
List of position dictionaries with the following fields:
- `position_id`: Unique identifier for the position
- `symbol`: Trading symbol (e.g., BTCUSD)
- `long_qty`: Long position quantity
- `short_qty`: Short position quantity
- `settl_price`: Settlement price of the position

**CSV Example:**
```csv
FIX_USERNAME,FIX_PASSWORD,FIX_SENDER_COMP_ID,TRADE_HOST,TRADE_PORT,TRADE_SENDER_SUB_ID,TRADE_TARGET_SUB_ID,TRADE_ACTION,TRADE_SYMBOL
demo1,pass1,sender1,fix.ctrader.com,5001,sub1,target1,positions,BTCUSD
```

**Output Example:**
```
[Account 1] Positions request sent: PosReqID=POS-ABC123XYZ789
[Account 1] Position report count=3
```

---

### `buy`

Place a market buy order for the specified symbol and quantity.

**Behavior:**
- Sends a `NewOrderSingle` FIX message with side="1" (Buy)
- Uses market order type (OrdType="1")
- Order quantity is taken from `TRADE_QTY` column
- Symbol is resolved via `resolve_symbol_id()`

**Required CSV Columns:**
- `TRADE_ACTION`: Must be "buy"
- `TRADE_SYMBOL`: Symbol to buy (e.g., BTCUSD)
- `TRADE_QTY`: Quantity to purchase (e.g., 0.01)

**Returns:**
Execution report with the following fields:
- `exec_type`: Execution type (e.g., "0" for New, "2" for Filled)
- `ord_status`: Order status (e.g., "0" for New, "2" for Filled)
- `order_id`: Unique order identifier
- `symbol`: Executed symbol
- `side`: Side of order ("1" for Buy)
- `filled_qty`: Actually filled quantity
- `avg_px`: Average execution price
- `text`: Additional text information

**CSV Example:**
```csv
FIX_USERNAME,FIX_PASSWORD,FIX_SENDER_COMP_ID,TRADE_HOST,TRADE_PORT,TRADE_SENDER_SUB_ID,TRADE_TARGET_SUB_ID,TRADE_ACTION,TRADE_SYMBOL,TRADE_QTY
demo2,pass2,sender2,fix.ctrader.com,5001,sub2,target2,buy,BTCUSD,0.01
```

**Output Example:**
```
[Account 2] Connected
[Account 2] Order sent: ClOrdID=ORD-ABC123XYZ789, symbol=BTCUSD, side=1, qty=0.01
[Account 2] Order update: {'exec_type': '2', 'ord_status': '2', 'order_id': '12345', ...}
```

---

### `sell`

Place a market sell order for the specified symbol and quantity.

**Behavior:**
- Sends a `NewOrderSingle` FIX message with side="2" (Sell)
- Uses market order type (OrdType="1")
- Order quantity is taken from `TRADE_QTY` column
- Symbol is resolved via `resolve_symbol_id()`

**Required CSV Columns:**
- `TRADE_ACTION`: Must be "sell"
- `TRADE_SYMBOL`: Symbol to sell (e.g., BTCUSD)
- `TRADE_QTY`: Quantity to sell (e.g., 0.01)

**Returns:**
Execution report with the following fields:
- `exec_type`: Execution type (e.g., "0" for New, "2" for Filled)
- `ord_status`: Order status (e.g., "0" for New, "2" for Filled)
- `order_id`: Unique order identifier
- `symbol`: Executed symbol
- `side`: Side of order ("2" for Sell)
- `filled_qty`: Actually filled quantity
- `avg_px`: Average execution price
- `text`: Additional text information

**CSV Example:**
```csv
FIX_USERNAME,FIX_PASSWORD,FIX_SENDER_COMP_ID,TRADE_HOST,TRADE_PORT,TRADE_SENDER_SUB_ID,TRADE_TARGET_SUB_ID,TRADE_ACTION,TRADE_SYMBOL,TRADE_QTY
demo3,pass3,sender3,fix.ctrader.com,5001,sub3,target3,sell,BTCUSD,0.01
```

**Output Example:**
```
[Account 3] Connected
[Account 3] Order sent: ClOrdID=ORD-DEF456UVW012, symbol=BTCUSD, side=2, qty=0.01
[Account 3] Order update: {'exec_type': '2', 'ord_status': '2', 'order_id': '67890', ...}
```

---

### `close`

Close an existing position by sending an offsetting order.

**Behavior:**
1. First queries positions to find the target position
2. If `TRADE_POSITION_ID` is specified, closes that specific position
3. Otherwise, auto-closes the first position matching `TRADE_SYMBOL`
4. Determines close side (Sell for Long positions, Buy for Short positions)
5. Sends close order with the exact position quantity
6. Includes `PosMaintRptID` to link the close to the original position

**Required CSV Columns:**
- `TRADE_ACTION`: Must be "close"
- `TRADE_SYMBOL`: Symbol to close (e.g., BTCUSD)

**Optional CSV Columns:**
- `TRADE_POSITION_ID`: Specific position ID to close (if not provided, auto-closes first matching symbol)

**Returns:**
Close order execution report with position reference.

**Position Selection Logic:**
- If `TRADE_POSITION_ID` is provided: Closes position with matching ID
- If no position ID: Finds first position where `symbol == TRADE_SYMBOL` AND (`long_qty > 0` OR `short_qty > 0`)

**Side Determination:**
- If `long_qty > 0`: Sends Sell order (side="2")
- If `short_qty > 0`: Sends Buy order (side="1")

**Quantity:**
- Uses the full position quantity (`long_qty` or `short_qty`)

**CSV Examples:**

Close by specific position ID:
```csv
FIX_USERNAME,FIX_PASSWORD,FIX_SENDER_COMP_ID,TRADE_HOST,TRADE_PORT,TRADE_SENDER_SUB_ID,TRADE_TARGET_SUB_ID,TRADE_ACTION,TRADE_SYMBOL,TRADE_POSITION_ID
demo4,pass4,sender4,fix.ctrader.com,5001,sub4,target4,close,BTCUSD,123456789
```

Close by symbol (auto-select):
```csv
FIX_USERNAME,FIX_PASSWORD,FIX_SENDER_COMP_ID,TRADE_HOST,TRADE_PORT,TRADE_SENDER_SUB_ID,TRADE_TARGET_SUB_ID,TRADE_ACTION,TRADE_SYMBOL
demo5,pass5,sender5,fix.ctrader.com,5001,sub5,target5,close,BTCUSD
```

**Output Example:**
```
[Account 4] Connected
[Account 4] Close positions request sent: PosReqID=POS-GHI789JKL345
[Account 4] Close candidate count added=1
[Account 4] Close order sent: ClOrdID=CLS-MNO012PQR678, position_id=123456789, symbol=BTCUSD, side=2, qty=0.01
[Account 4] Order update: {'exec_type': '2', 'ord_status': '2', ...}
```

**Error Cases:**
- Position not found: "Close target not found for position_id={id} symbol={symbol}"
- Position has no quantity: "Target has no open qty: {position}"

---

## Trading Action Summary Table

| Action | Side | Requires QTY | Optional Position ID | Description |
|--------|------|--------------|---------------------|-------------|
| `positions` | N/A | No | No | Query all open positions |
| `buy` | 1 (Buy) | Yes | No | Open long position |
| `sell` | 2 (Sell) | Yes | No | Open short position |
| `close` | Auto | No | Yes | Close existing position |

## Example Workflow

### 1. Create accounts.csv

```csv
FIX_USERNAME,FIX_PASSWORD,FIX_SENDER_COMP_ID,TRADE_HOST,TRADE_PORT,TRADE_SENDER_SUB_ID,TRADE_TARGET_SUB_ID,ACCOUNT_NAME,TRADE_ACTION,TRADE_SYMBOL,TRADE_QTY
demo1,demo_pass,sender_demo1,fix.ctrader.com,5001,sub_demo1,target_demo1,Account 1,positions,BTCUSD,0.01
demo2,demo_pass,sender_demo2,fix.ctrader.com,5001,sub_demo2,target_demo2,Account 2,buy,BTCUSD,0.01
```

### 2. Create .env (optional)

```
MULTI_TRADE_CSV=accounts.csv
```

### 3. Run the client

```bash
python multitrade.py
```

## Error Handling

The module raises `ValueError` for:
- Missing CSV file
- Missing required columns in CSV
- Invalid `TRADE_ACTION` values
- Missing required environment variables

Connection errors and timeouts are logged but don't stop other sessions from processing.

## Author

QuantMachine Team

## Date

April 2026

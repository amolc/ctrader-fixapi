"""
Multi-Account FIX API Trading Client for cTrader.

This module provides functionality to execute trades across multiple cTrader accounts
simultaneously using the FIX (Financial Information eXchange) protocol. It supports
operations including querying positions, placing buy/sell orders, and closing positions.

Key Components:
    - load_env_file: Load environment variables from .env file
    - get_env: Retrieve environment variables with defaults and validation
    - str_to_bool: Convert string values to boolean
    - value_at: Safely access list elements by index
    - AccountSession: Represents a single trading account session with FIX connection
    - MultiTradeManager: Manages multiple account sessions and coordinates trading operations
    - load_accounts_from_csv: Load account configurations from CSV file

Usage:
    Set MULTI_TRADE_CSV environment variable to point to your accounts CSV file,
    then run: python multitrade.py

Environment Variables:
    MULTI_TRADE_CSV: Path to CSV file containing account configurations (default: accounts.csv)

CSV Format:
    Required columns: FIX_USERNAME, FIX_PASSWORD, FIX_SENDER_COMP_ID, TRADE_HOST,
                      TRADE_PORT, TRADE_SENDER_SUB_ID, TRADE_TARGET_SUB_ID
    Optional columns: ACCOUNT_NAME, TRADE_ACTION, TRADE_SYMBOL, TRADE_QTY,
                      TRADE_TIMEOUT, FIX_RESET_SEQ_NUM, TRADE_SSL, TRADE_POSITION_ID,
                      FIX_BEGIN_STRING, FIX_TARGET_COMP_ID, FIX_HEARTBEAT

Author: QuantMachine Team
Date: April 2026
"""

import csv
import importlib
import os
import sys
import uuid

# Import ctrader_fix module dynamically to handle potential import variations
trader_fix = importlib.import_module("ctrader_fix")
Client = ctrader_fix.Client
LogonRequest = ctrader_fix.LogonRequest
NewOrderSingle = ctrader_fix.NewOrderSingle
RequestForPositions = ctrader_fix.RequestForPositions
reactor = ctrader_fix.reactor


def load_env_file(path: str) -> None:
    """
    Load environment variables from a .env file.

    Parses a dotenv-style file and sets environment variables. Lines starting with
    '#' are treated as comments and ignored. Variables already set in the environment
    are not overwritten.

    Args:
        path: Path to the .env file to load.

    Returns:
        None

    Example:
        >>> load_env_file(".env")
        # Loads KEY=value pairs from .env into os.environ
    """
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def get_env(name: str, default: str | None = None, required: bool = False) -> str:
    """
    Retrieve environment variable with optional default value and validation.

    Safely retrieves environment variables with support for default values
    and required field validation. Raises ValueError if a required variable
    is missing or empty.

    Args:
        name: Name of the environment variable to retrieve.
        default: Default value if variable is not set. Defaults to None.
        required: If True, raises ValueError when variable is missing/empty.
                  Defaults to False.

    Returns:
        str: The environment variable value, default, or empty string.

    Raises:
        ValueError: If required=True and the variable is missing or empty.

    Example:
        >>> get_env("API_KEY", required=True)
        'secret_key_value'
        >>> get_env("OPTIONAL_VAR", "default_value")
        'default_value'
    """
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise ValueError(f"Missing required environment variable: {name}")
    return value or ""


def str_to_bool(value: str | bool) -> bool:
    """
    Convert a string or boolean value to boolean.

    Converts various string representations to boolean values.
    Case-insensitive matching for: '1', 'true', 'yes', 'on', 'y'.
    All other values return False.

    Args:
        value: Value to convert. Can be a string or boolean.

    Returns:
        bool: True if value represents a truthy string/bool, False otherwise.

    Examples:
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
    """
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on", "y"}


def value_at(value, idx: int):
    """
    Safely access an element from a list by index.

    Provides safe list element access with bounds checking.
    Returns None if index is out of bounds or value is not a list.

    Args:
        value: List to access. If not a list, returns None.
        idx: Zero-based index of the element to retrieve.

    Returns:
        The element at the specified index, or None if out of bounds
        or if value is not a list.

    Examples:
        >>> value_at(["a", "b", "c"], 1)
        'b'
        >>> value_at(["a", "b"], 5)
        None
        >>> value_at("not a list", 0)
        None
    """
    if isinstance(value, list):
        if idx < len(value):
            return value[idx]
        return None
    return value


class AccountSession:
    """
    Represents a single trading account session with FIX connection.

    This class encapsulates all configuration and state for a cTrader account
    connection via the FIX protocol. It handles account identification,
    trade configuration, and session state management.

    Attributes:
        row: Dictionary containing raw account configuration from CSV.
        account_name: Human-readable account identifier.
        action: Trading action to perform ("positions", "buy", "sell", "close").
        symbol_requested: Original symbol string from configuration.
        symbol: Resolved symbol ID for trading.
        quantity: Trade quantity for buy/sell operations.
        timeout_seconds: Session timeout before auto-disconnect.
        reset_seq_num: Whether to reset FIX sequence numbers on logon.
        close_position_id: Specific position ID to close (optional).
        trade_config: Dictionary of FIX connection parameters.
        client: FIX protocol client instance.
        logged_in: Whether the session has completed logon.
        completed: Whether the session has finished all operations.
        sent_id: Most recently sent message ID for correlation.
        position_reports_count: Number of position reports received.
        collected_positions: List of collected position dictionaries.
        timeout_call: Twisted timeout call handle.
        positions_finish_call: Twisted delayed call for position operations.

    Example:
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
    """

    def __init__(self, row: dict):
        """
        Initialize account session from CSV row data.

        Args:
            row: Dictionary containing account configuration from CSV.
                 Must include required FIX connection parameters.
        """
        self.row = {key.strip(): (value or "").strip() for key, value in row.items()}
        self.account_name = self.row.get("ACCOUNT_NAME") or self.row.get("FIX_USERNAME")
        self.action = (self.row.get("TRADE_ACTION") or "positions").lower()
        self.symbol_requested = self.row.get("TRADE_SYMBOL") or "BTCUSD"
        self.symbol = self.resolve_symbol_id(self.symbol_requested)
        self.quantity = float(self.row.get("TRADE_QTY") or "0.01")
        self.timeout_seconds = int(self.row.get("TRADE_TIMEOUT") or "20")
        self.reset_seq_num = str_to_bool(self.row.get("FIX_RESET_SEQ_NUM") or "true")
        self.close_position_id = self.row.get("TRADE_POSITION_ID") or ""
        self.trade_config = {
            "Host": self.row["TRADE_HOST"],
            "Port": int(self.row["TRADE_PORT"]),
            "SSL": str_to_bool(self.row.get("TRADE_SSL") or "false"),
            "Username": self.row["FIX_USERNAME"],
            "Password": self.row["FIX_PASSWORD"],
            "BeginString": self.row.get("FIX_BEGIN_STRING") or "FIX.4.4",
            "SenderCompID": self.row["FIX_SENDER_COMP_ID"],
            "SenderSubID": self.row["TRADE_SENDER_SUB_ID"],
            "TargetCompID": self.row.get("FIX_TARGET_COMP_ID") or "cServer",
            "TargetSubID": self.row["TRADE_TARGET_SUB_ID"],
            "HeartBeat": self.row.get("FIX_HEARTBEAT") or "30",
        }
        self.client = Client(
            self.trade_config["Host"],
            self.trade_config["Port"],
            ssl=self.trade_config["SSL"],
            delimiter="\x01",
        )
        self.logged_in = False
        self.completed = False
        self.sent_id = None
        self.position_reports_count = 0
        self.collected_positions = []
        self.timeout_call = None
        self.positions_finish_call = None

    def resolve_symbol_id(self, symbol: str) -> str:
        """
        Resolve symbol name to trading ID.

        Checks if symbol is a numeric ID, then looks for environment variable
        mapping (SYMBOL_{SYMBOL}_ID), otherwise returns the symbol as-is.

        Args:
            symbol: Symbol string to resolve.

        Returns:
            str: Resolved symbol ID for trading.

        Examples:
            >>> session.resolve_symbol_id("12345")
            '12345'
            >>> session.resolve_symbol_id("BTCUSD")
            'BTCUSD'  # or value from SYMBOL_BTCUSD_ID env var
        """
        if symbol.isdigit():
            return symbol
        env_key = f"SYMBOL_{symbol.upper()}_ID"
        if self.row.get(env_key):
            return self.row[env_key]
        return symbol


class MultiTradeManager:
    """
    Manages multiple account sessions and coordinates trading operations.

    This class orchestrates trading operations across multiple cTrader accounts
    simultaneously. It handles connection management, message routing, and
    lifecycle management for all account sessions.

    Attributes:
        sessions: List of AccountSession instances to manage.

    Example:
        >>> sessions = load_accounts_from_csv("accounts.csv")
        >>> manager = MultiTradeManager(sessions)
        >>> manager.start()
    """

    def __init__(self, sessions: list[AccountSession]):
        """
        Initialize the manager with a list of account sessions.

        Args:
            sessions: List of AccountSession instances to coordinate.
        """
        self.sessions = sessions

    def start(self) -> None:
        """
        Start all account sessions and begin the FIX event loop.

        Initializes connections for all configured accounts, sets up callbacks,
        and starts the Twisted reactor event loop. This method blocks until
        all sessions complete or timeout.

        Returns:
            None

        Note:
            This method blocks and runs the Twisted reactor. It will not
            return until all trading operations complete or timeout.
        """
        if not self.sessions:
            print("No account sessions found")
            return
        for session in self.sessions:
            session.client.setConnectedCallback(lambda client, s=session: self.on_connected(s, client))
            session.client.setDisconnectedCallback(lambda client, reason, s=session: self.on_disconnected(s, client, reason))
            session.client.setMessageReceivedCallback(lambda client, response, s=session: self.on_message(s, client, response))
            session.timeout_call = reactor.callLater(session.timeout_seconds, self.on_timeout, session)
            session.client.startService()
        reactor.run()

    def on_connected(self, session: AccountSession, client: Client) -> None:
        """
        Handle FIX connection establishment for a session.

        Called when the FIX client successfully establishes a TCP connection.
        Logs connection details and sends the FIX logon message.

        Args:
            session: AccountSession that connected.
            client: FIX client instance.

        Returns:
            None
        """
        print(f"[{session.account_name}] Connected")
        print(
            f"[{session.account_name}] "
            f"host={session.trade_config['Host']} port={session.trade_config['Port']} ssl={session.trade_config['SSL']} "
            f"action={session.action} symbol={session.symbol_requested}->{session.symbol} qty={session.quantity}"
        )
        logon = LogonRequest(session.trade_config)
        logon.ResetSeqNum = session.reset_seq_num
        client.send(logon)

    def on_disconnected(self, session: AccountSession, client: Client, reason) -> None:
        """
        Handle FIX disconnection for a session.

        Called when the FIX client disconnects from the server. Marks the session
        as completed and triggers shutdown if all sessions are done.

        Args:
            session: AccountSession that disconnected.
            client: FIX client instance.
            reason: Disconnection reason string.

        Returns:
            None
        """
        print(f"[{session.account_name}] Disconnected: {reason}")
        if not session.completed:
            session.completed = True
            if session.timeout_call and session.timeout_call.active():
                session.timeout_call.cancel()
            self.maybe_stop()

    def on_message(self, session: AccountSession, client: Client, response) -> None:
        msg_type = response.getFieldValue(35)
        print(f"[{session.account_name}] {response.getMessage()}")

        if msg_type == "A" and not session.logged_in:
            session.logged_in = True
            self.after_logon(session)
            return

        if session.action in {"positions", "close"} and self.has_message_type(msg_type, "AP"):
            added = self.collect_positions(session, response)
            if session.action == "positions":
                session.position_reports_count += added
                print(f"[{session.account_name}] Position report count={session.position_reports_count}")
            else:
                print(f"[{session.account_name}] Close candidate count added={added}")
            return

        if session.action in {"buy", "sell", "close"} and self.has_message_type(msg_type, "8"):
            cl_ord_id = response.getFieldValue(11)
            if self.id_matches(cl_ord_id, session.sent_id):
                result = {
                    "exec_type": response.getFieldValue(150),
                    "ord_status": response.getFieldValue(39),
                    "order_id": response.getFieldValue(37),
                    "symbol": response.getFieldValue(55),
                    "side": response.getFieldValue(54),
                    "filled_qty": response.getFieldValue(14),
                    "avg_px": response.getFieldValue(6),
                    "text": response.getFieldValue(58),
                }
                print(f"[{session.account_name}] Order update: {result}")
                self.finish_session(session)
                return

        if session.action in {"buy", "sell", "close"} and self.has_message_type(msg_type, "j"):
            reject_ref_id = response.getFieldValue(379)
            if self.id_matches(reject_ref_id, session.sent_id):
                reject = {
                    "ref_id": reject_ref_id,
                    "ref_seq_num": response.getFieldValue(45),
                    "reason": response.getFieldValue(58),
                    "reject_reason_code": response.getFieldValue(380),
                }
                print(f"[{session.account_name}] Business message reject: {reject}")
                self.finish_session(session)

    def collect_positions(self, session: AccountSession, response) -> int:
        position_ids = response.getFieldValue(721)
        symbols = response.getFieldValue(55)
        long_qtys = response.getFieldValue(704)
        short_qtys = response.getFieldValue(705)
        settl_prices = response.getFieldValue(730)
        if isinstance(position_ids, list):
            count = len(position_ids)
            for idx in range(count):
                position = {
                    "position_id": value_at(position_ids, idx),
                    "symbol": value_at(symbols, idx),
                    "long_qty": value_at(long_qtys, idx),
                    "short_qty": value_at(short_qtys, idx),
                    "settl_price": value_at(settl_prices, idx),
                }
                session.collected_positions.append(position)
            return count
        position = {
            "position_id": position_ids,
            "symbol": symbols,
            "long_qty": long_qtys,
            "short_qty": short_qtys,
            "settl_price": settl_prices,
        }
        session.collected_positions.append(position)
        return 1

    def has_message_type(self, msg_type, expected: str) -> bool:
        if isinstance(msg_type, list):
            return expected in msg_type
        return msg_type == expected

    def after_logon(self, session: AccountSession) -> None:
        if session.action == "positions":
            request = RequestForPositions(session.trade_config)
            session.sent_id = f"POS-{uuid.uuid4().hex[:12].upper()}"
            request.PosReqID = session.sent_id
            session.client.send(request)
            print(f"[{session.account_name}] Positions request sent: PosReqID={session.sent_id}")
            session.positions_finish_call = reactor.callLater(3, self.finish_session, session)
            return

        if session.action == "close":
            request = RequestForPositions(session.trade_config)
            session.sent_id = f"POS-{uuid.uuid4().hex[:12].upper()}"
            request.PosReqID = session.sent_id
            session.client.send(request)
            print(f"[{session.account_name}] Close positions request sent: PosReqID={session.sent_id}")
            session.positions_finish_call = reactor.callLater(3, self.execute_close_from_positions, session)
            return

        if session.action == "buy":
            self.send_market_order(session, side="1", quantity=session.quantity, symbol=session.symbol, prefix="ORD")
            return

        if session.action == "sell":
            self.send_market_order(session, side="2", quantity=session.quantity, symbol=session.symbol, prefix="ORD")
            return

        raise ValueError(f"Unsupported action for account {session.account_name}: {session.action}")

    def send_market_order(self, session: AccountSession, side: str, quantity: float, symbol: str, prefix: str) -> None:
        order = NewOrderSingle(session.trade_config)
        session.sent_id = f"{prefix}-{uuid.uuid4().hex[:12].upper()}"
        order.ClOrdID = session.sent_id
        order.Symbol = symbol
        order.Side = side
        order.OrderQty = quantity
        order.OrdType = "1"
        session.client.send(order)
        print(
            f"[{session.account_name}] Order sent: "
            f"ClOrdID={session.sent_id}, symbol={symbol}, side={side}, qty={quantity}"
        )

    def execute_close_from_positions(self, session: AccountSession) -> None:
        if session.completed:
            return
        target = None
        if session.close_position_id:
            for position in session.collected_positions:
                if str(position.get("position_id")) == session.close_position_id:
                    target = position
                    break
        else:
            for position in session.collected_positions:
                if str(position.get("symbol")) != session.symbol:
                    continue
                long_qty = float(position.get("long_qty") or 0)
                short_qty = float(position.get("short_qty") or 0)
                if long_qty > 0 or short_qty > 0:
                    target = position
                    break
        if target is None:
            print(
                f"[{session.account_name}] Close target not found for "
                f"position_id={session.close_position_id or 'auto'} symbol={session.symbol}"
            )
            self.finish_session(session)
            return
        long_qty = float(target.get("long_qty") or 0)
        short_qty = float(target.get("short_qty") or 0)
        if long_qty <= 0 and short_qty <= 0:
            print(f"[{session.account_name}] Target has no open qty: {target}")
            self.finish_session(session)
            return
        side = "2" if long_qty > 0 else "1"
        qty = long_qty if long_qty > 0 else short_qty
        symbol = str(target.get("symbol"))
        position_id = str(target.get("position_id"))
        order = NewOrderSingle(session.trade_config)
        session.sent_id = f"CLS-{uuid.uuid4().hex[:12].upper()}"
        order.ClOrdID = session.sent_id
        order.Symbol = symbol
        order.Side = side
        order.OrderQty = qty
        order.OrdType = "1"
        order.PosMaintRptID = position_id
        session.client.send(order)
        print(
            f"[{session.account_name}] Close order sent: "
            f"ClOrdID={session.sent_id}, position_id={position_id}, symbol={symbol}, side={side}, qty={qty}"
        )

    def on_timeout(self, session: AccountSession) -> None:
        if session.completed:
            return
        print(f"[{session.account_name}] Timeout after {session.timeout_seconds}s")
        self.finish_session(session)

    def finish_session(self, session: AccountSession) -> None:
        if session.completed:
            return
        session.completed = True
        if session.timeout_call and session.timeout_call.active():
            session.timeout_call.cancel()
        if session.positions_finish_call and session.positions_finish_call.active():
            session.positions_finish_call.cancel()
        try:
            session.client.stopService()
        except Exception:
            pass
        self.maybe_stop()

    def maybe_stop(self) -> None:
        if all(session.completed for session in self.sessions) and reactor.running:
            reactor.callLater(0.1, reactor.stop)

    @staticmethod
    def id_matches(response_id, request_id: str | None) -> bool:
        if request_id is None or response_id is None:
            return False
        if isinstance(response_id, list):
            return request_id in response_id
        return response_id == request_id


def load_accounts_from_csv(csv_path: str) -> list[AccountSession]:
    """
    Load account configurations from a CSV file.

    Reads account configurations from a CSV file, validates required columns,
    and creates AccountSession instances for each valid row.

    Required CSV columns:
        FIX_USERNAME: Account username for FIX authentication.
        FIX_PASSWORD: Account password for FIX authentication.
        FIX_SENDER_COMP_ID: Sender Comp ID for FIX protocol.
        TRADE_HOST: FIX server hostname or IP address.
        TRADE_PORT: FIX server port number.
        TRADE_SENDER_SUB_ID: Sender Sub ID for FIX protocol.
        TRADE_TARGET_SUB_ID: Target Sub ID for FIX protocol.

    Optional CSV columns:
        ACCOUNT_NAME: Human-readable account name (defaults to FIX_USERNAME).
        TRADE_ACTION: Action to perform - positions, buy, sell, close (default: positions).
        TRADE_SYMBOL: Trading symbol (default: BTCUSD).
        TRADE_QTY: Trade quantity for buy/sell (default: 0.01).
        TRADE_TIMEOUT: Session timeout in seconds (default: 20).
        FIX_RESET_SEQ_NUM: Reset sequence numbers on logon (default: true).
        TRADE_SSL: Use SSL connection (default: false).
        TRADE_POSITION_ID: Specific position ID to close.
        FIX_BEGIN_STRING: FIX protocol version (default: FIX.4.4).
        FIX_TARGET_COMP_ID: Target Comp ID (default: cServer).
        FIX_HEARTBEAT: Heartbeat interval in seconds (default: 30).

    Args:
        csv_path: Path to the CSV file containing account configurations.

    Returns:
        list[AccountSession]: List of initialized AccountSession instances.

    Raises:
        ValueError: If CSV file not found, required columns missing, or invalid TRADE_ACTION.

    Example:
        >>> sessions = load_accounts_from_csv("accounts.csv")
        >>> len(sessions)
        3
    """
    if not os.path.exists(csv_path):
        raise ValueError(f"CSV file not found: {csv_path}")
    with open(csv_path, "r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
    if not rows:
        return []
    required_columns = [
        "FIX_USERNAME",
        "FIX_PASSWORD",
        "FIX_SENDER_COMP_ID",
        "TRADE_HOST",
        "TRADE_PORT",
        "TRADE_SENDER_SUB_ID",
        "TRADE_TARGET_SUB_ID",
    ]
    sessions = []
    for index, row in enumerate(rows, start=1):
        for column in required_columns:
            if not (row.get(column) or "").strip():
                raise ValueError(f"Row {index} missing required column value: {column}")
        action = (row.get("TRADE_ACTION") or "positions").strip().lower()
        if action not in {"positions", "buy", "sell", "close"}:
            raise ValueError(f"Row {index} invalid TRADE_ACTION={action}")
        sessions.append(AccountSession(row))
    return sessions


def main() -> int:
    """
    Main entry point for the multi-account trading client.

    Loads environment variables from .env file, reads account configurations
    from CSV, initializes the MultiTradeManager, and starts trading operations.

    Environment Variables:
        MULTI_TRADE_CSV: Path to accounts CSV file (default: accounts.csv).

    Returns:
        int: Exit code - 0 for success, 1 for error.

    Example:
        >>> import sys
        >>> sys.exit(main())
    """
    load_env_file(".env")
    csv_path = get_env("MULTI_TRADE_CSV", "accounts.csv")
    try:
        sessions = load_accounts_from_csv(csv_path)
        manager = MultiTradeManager(sessions)
        manager.start()
        return 0
    except ValueError as error:
        print(error)
        return 1


if __name__ == "__main__":
    sys.exit(main())

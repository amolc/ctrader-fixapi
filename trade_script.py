import importlib
import os
import sys
import uuid
import threading

ctrader_fix = importlib.import_module("ctrader_fix")
Client = ctrader_fix.Client
LogonRequest = ctrader_fix.LogonRequest
MarketDataRequest = ctrader_fix.MarketDataRequest
NewOrderSingle = ctrader_fix.NewOrderSingle
RequestForPositions = ctrader_fix.RequestForPositions
OrderMassStatusRequest = ctrader_fix.OrderMassStatusRequest
reactor = ctrader_fix.reactor

_reactor_thread = None
_reactor_lock = threading.Lock()

def start_reactor_thread():
    global _reactor_thread
    with _reactor_lock:
        if _reactor_thread is None:
            _reactor_thread = threading.Thread(
                target=reactor.run,
                kwargs={"installSignalHandlers": False},
                daemon=True
            )
            _reactor_thread.start()


def load_env_file(path: str) -> None:
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
    value = os.getenv(name)
    if value is None and name.upper() != name:
        value = os.getenv(name.upper())
    if value is None and name.lower() != name:
        value = os.getenv(name.lower())
    if value is None:
        value = default
    if required and (value is None or value == ""):
        raise ValueError(f"Missing required environment variable: {name}")
    return value or ""


def str_to_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on", "y"}


def build_fix_config(prefix: str) -> dict:
    host = get_env(f"{prefix}_HOST", required=True)
    port = int(get_env(f"{prefix}_PORT", required=True))
    ssl = str_to_bool(get_env(f"{prefix}_SSL", "false"))
    username = get_env("FIX_USERNAME", required=True)
    password = get_env("FIX_PASSWORD", required=True)
    begin_string = get_env("FIX_BEGIN_STRING", "FIX.4.4")
    sender_comp_id = get_env("FIX_SENDER_COMP_ID", required=True)
    sender_sub_id = get_env(f"{prefix}_SENDER_SUB_ID", required=True)
    target_comp_id = get_env("FIX_TARGET_COMP_ID", "cServer")
    target_sub_id = get_env(f"{prefix}_TARGET_SUB_ID", required=True)
    heartbeat = get_env("FIX_HEARTBEAT", "30")
    return {
        "Host": host,
        "Port": int(port),
        "SSL": bool(ssl),
        "Username": username,
        "Password": password,
        "BeginString": begin_string,
        "SenderCompID": sender_comp_id,
        "SenderSubID": sender_sub_id,
        "TargetCompID": target_comp_id,
        "TargetSubID": target_sub_id,
        "HeartBeat": heartbeat,
    }


def resolve_symbol_id(symbol: str | None) -> str | None:
    if not symbol:
        return symbol
    if symbol.isdigit():
        return symbol
    env_symbol = get_env(f"SYMBOL_{symbol.upper()}_ID", "")
    if env_symbol:
        return env_symbol
    defaults = {"BTCUSD": "101"}
    return defaults.get(symbol.upper(), symbol)


def value_at(value, idx: int):
    if isinstance(value, list):
        if idx < len(value):
            return value[idx]
        return None
    if idx == 0:
        return value
    return None


def parse_optional_float(name: str) -> float | None:
    raw_value = get_env(name, "").strip()
    if raw_value == "":
        return None
    value = float(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0 when provided")
    return value


def format_terminal_table(rows: list[tuple[str, str]]) -> str:
    key_width = max(len("Field"), *(len(key) for key, _ in rows))
    value_width = max(len("Value"), *(len(value) for _, value in rows))
    border = f"+-{'-' * key_width}-+-{'-' * value_width}-+"
    header = f"| {'Field'.ljust(key_width)} | {'Value'.ljust(value_width)} |"
    body = [
        f"| {key.ljust(key_width)} | {value.ljust(value_width)} |"
        for key, value in rows
    ]
    return "\n".join([border, header, border, *body, border])


def read_output_settings() -> bool:
    return str_to_bool(get_env("MINIMAL_OUTPUT", "false"))


def apply_cli_action_override() -> None:
    if len(sys.argv) < 2:
        return
    cli_action = sys.argv[1].strip().lower()
    if cli_action in {"positions", "buy", "sell", "close", "transactions"}:
        os.environ["TRADE_ACTION"] = cli_action


def read_runtime_settings() -> tuple[str, str, float, int, bool, str, float | None, float | None]:
    close_position_id = get_env("TRADE_POSITION_ID", "").strip()
    action_default = "close" if close_position_id else "positions"
    action = get_env("TRADE_ACTION", action_default).lower()
    if close_position_id and action == "positions":
        action = "close"
    if action not in {"positions", "buy", "sell", "close", "transactions"}:
        raise ValueError("TRADE_ACTION must be one of: positions, buy, sell, close, transactions")
    symbol = get_env("TRADE_SYMBOL", "BTCUSD")
    quantity = float(get_env("TRADE_QTY", "0.01"))
    timeout_seconds = int(get_env("TRADE_TIMEOUT", "20"))
    reset_seq_num = str_to_bool(get_env("FIX_RESET_SEQ_NUM", "true"))
    take_profit_pct = parse_optional_float("EXIT_TAKE_PROFIT_PCT")
    stop_loss_pct = parse_optional_float("EXIT_STOP_LOSS_PCT")
    return (
        action,
        symbol,
        quantity,
        timeout_seconds,
        reset_seq_num,
        close_position_id,
        take_profit_pct,
        stop_loss_pct,
    )


class TradeRunner:
    def __init__(
        self,
        action: str,
        symbol: str,
        quantity: float,
        timeout_seconds: int,
        trade_config: dict,
        reset_seq_num: bool,
        close_position_id: str,
        quote_config: dict | None,
        take_profit_pct: float | None,
        stop_loss_pct: float | None,
        minimal_output: bool,
    ):
        self.action = action
        self.symbol = resolve_symbol_id(symbol)
        self.symbol_requested = symbol
        self.quantity = quantity
        self.timeout_seconds = timeout_seconds
        self.trade_config = trade_config
        self.reset_seq_num = reset_seq_num
        self.close_position_id = close_position_id
        self.quote_config = quote_config
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.minimal_output = minimal_output
        self.client = Client(
            self.trade_config["Host"],
            self.trade_config["Port"],
            ssl=self.trade_config["SSL"],
            delimiter="\x01",
        )
        self.client.setConnectedCallback(self.on_connected)
        self.client.setDisconnectedCallback(self.on_disconnected)
        self.client.setMessageReceivedCallback(self.on_trade_message)
        self.quote_client = None
        if self.should_monitor_exit():
            self.quote_client = Client(
                self.quote_config["Host"],
                self.quote_config["Port"],
                ssl=self.quote_config["SSL"],
                delimiter="\x01",
            )
            self.quote_client.setConnectedCallback(self.on_quote_connected)
            self.quote_client.setDisconnectedCallback(self.on_quote_disconnected)
            self.quote_client.setMessageReceivedCallback(self.on_quote_message)
        self.logged_in = False
        self.quote_logged_in = False
        self.completed = False
        self.sent_id = None
        self.position_reports_count = 0
        self.timeout_call = None
        self.collected_positions = []
        self.entry_order_id = None
        self.entry_side = None
        self.entry_position_id = None
        self.entry_avg_px = None
        self.entry_filled_qty = None
        self.exit_order_id = None
        self.exit_reason = None
        self.market_data_request_id = None
        self.last_bid = None
        self.last_ask = None
        self.exit_triggered = False
        self.done_event = threading.Event()
        self.collected_transactions = []

    def start(self) -> None:
        start_reactor_thread()
        reactor.callFromThread(self._start_on_reactor)
        self.done_event.wait()

    def _start_on_reactor(self) -> None:
        self.timeout_call = reactor.callLater(self.timeout_seconds, self.on_timeout)
        self.client.startService()

    def should_monitor_exit(self) -> bool:
        return self.action in {"buy", "sell"} and (
            self.take_profit_pct is not None or self.stop_loss_pct is not None
        )

    def log(self, message: str) -> None:
        if not self.minimal_output:
            print(message)

    @staticmethod
    def out(message: str) -> None:
        print(message)

    def on_connected(self, client: Client) -> None:
        self.log("Connected to cTrader TRADE FIX endpoint")
        self.log(
            "Logon config: "
            f"host={self.trade_config['Host']} port={self.trade_config['Port']} ssl={self.trade_config['SSL']} "
            f"username={self.trade_config['Username']} sender_comp={self.trade_config['SenderCompID']} "
            f"sender_sub={self.trade_config['SenderSubID']} target_comp={self.trade_config['TargetCompID']} "
            f"target_sub={self.trade_config['TargetSubID']} heartbeat={self.trade_config['HeartBeat']} "
            f"reset_seq_num={self.reset_seq_num}"
        )
        if self.symbol_requested != self.symbol:
            self.log(f"Symbol mapping: requested={self.symbol_requested} resolved={self.symbol}")
        logon = LogonRequest(self.trade_config)
        logon.ResetSeqNum = self.reset_seq_num
        client.send(logon)

    def on_quote_connected(self, client: Client) -> None:
        self.log("Connected to cTrader QUOTE FIX endpoint for exit monitoring")
        self.log(
            "Quote logon config: "
            f"host={self.quote_config['Host']} port={self.quote_config['Port']} ssl={self.quote_config['SSL']} "
            f"sender_comp={self.quote_config['SenderCompID']} sender_sub={self.quote_config['SenderSubID']} "
            f"target_comp={self.quote_config['TargetCompID']} target_sub={self.quote_config['TargetSubID']}"
        )
        logon = LogonRequest(self.quote_config)
        logon.ResetSeqNum = self.reset_seq_num
        client.send(logon)

    def on_disconnected(self, client: Client, reason) -> None:
        self.log(f"Disconnected: {reason}")
        self.finish()

    def on_quote_disconnected(self, client: Client, reason) -> None:
        self.log(f"Quote disconnected: {reason}")

    def on_trade_message(self, client: Client, response) -> None:
        msg_type = response.getFieldValue(35)
        self.log(response.getMessage())

        if msg_type == "A" and not self.logged_in:
            self.logged_in = True
            self.after_logon()
            return

        if self.action == "positions" and msg_type == "AP":
            self.position_reports_count += 1
            position = {
                "position_id": response.getFieldValue(721),
                "symbol": response.getFieldValue(55),
                "long_qty": response.getFieldValue(704),
                "short_qty": response.getFieldValue(705),
                "settl_price": response.getFieldValue(730),
                "position_type": response.getFieldValue(703),
            }
            self.collected_positions.append(position)
            self.log(f"Position report #{self.position_reports_count}: {position}")
            return

        if self.action == "close" and msg_type == "AP":
            position = {
                "position_id": response.getFieldValue(721),
                "symbol": response.getFieldValue(55),
                "long_qty": response.getFieldValue(704),
                "short_qty": response.getFieldValue(705),
                "settl_price": response.getFieldValue(730),
                "position_type": response.getFieldValue(703),
            }
            self.collected_positions.append(position)
            self.log(f"Close candidate: {position}")
            return

        if self.action == "positions" and isinstance(msg_type, list) and "AP" in msg_type:
            position_ids = response.getFieldValue(721)
            symbols = response.getFieldValue(55)
            long_qtys = response.getFieldValue(704)
            short_qtys = response.getFieldValue(705)
            settl_prices = response.getFieldValue(730)
            count = len(position_ids) if isinstance(position_ids, list) else msg_type.count("AP")
            self.position_reports_count += count
            self.log(f"Position reports received in batch: count={count}")
            if isinstance(position_ids, list) and isinstance(symbols, list):
                for idx in range(min(len(position_ids), len(symbols))):
                    long_qty = long_qtys[idx] if isinstance(long_qtys, list) and idx < len(long_qtys) else long_qtys
                    short_qty = short_qtys[idx] if isinstance(short_qtys, list) and idx < len(short_qtys) else short_qtys
                    settl_price = settl_prices[idx] if isinstance(settl_prices, list) and idx < len(settl_prices) else settl_prices
                    position = {
                        "position_id": position_ids[idx],
                        "symbol": symbols[idx],
                        "long_qty": long_qty,
                        "short_qty": short_qty,
                        "settl_price": settl_price,
                    }
                    self.collected_positions.append(position)
                    self.log(f"Position report(batch) #{idx + 1}: {position}")
            return

        if self.action == "close" and isinstance(msg_type, list) and "AP" in msg_type:
            position_ids = response.getFieldValue(721)
            symbols = response.getFieldValue(55)
            long_qtys = response.getFieldValue(704)
            short_qtys = response.getFieldValue(705)
            settl_prices = response.getFieldValue(730)
            count = len(position_ids) if isinstance(position_ids, list) else msg_type.count("AP")
            self.log(f"Close candidates received in batch: count={count}")
            if isinstance(position_ids, list) and isinstance(symbols, list):
                for idx in range(min(len(position_ids), len(symbols))):
                    long_qty = long_qtys[idx] if isinstance(long_qtys, list) and idx < len(long_qtys) else long_qtys
                    short_qty = short_qtys[idx] if isinstance(short_qtys, list) and idx < len(short_qtys) else short_qtys
                    settl_price = settl_prices[idx] if isinstance(settl_prices, list) and idx < len(settl_prices) else settl_prices
                    position = {
                        "position_id": position_ids[idx],
                        "symbol": symbols[idx],
                        "long_qty": long_qty,
                        "short_qty": short_qty,
                        "settl_price": settl_price,
                    }
                    self.collected_positions.append(position)
                    self.log(f"Close candidate(batch) #{idx + 1}: {position}")
            return

        if self.action == "transactions" and (msg_type == "8" or (isinstance(msg_type, list) and "8" in msg_type)):
            tx = {
                "order_id": response.getFieldValue(37),
                "cl_ord_id": response.getFieldValue(11),
                "symbol": response.getFieldValue(55),
                "side": response.getFieldValue(54),
                "qty": response.getFieldValue(38),
                "price": response.getFieldValue(44),
                "avg_px": response.getFieldValue(6),
                "cum_qty": response.getFieldValue(14),
                "status": response.getFieldValue(39),
                "exec_type": response.getFieldValue(150),
            }
            self.collected_transactions.append(tx)
            return

        if self.action in {"buy", "sell", "close"} and msg_type == "8":
            cl_ord_id = response.getFieldValue(11)
            if self.id_matches(cl_ord_id):
                self.handle_execution_report(response, "Order update")
                return

        if self.action in {"buy", "sell", "close"} and isinstance(msg_type, list) and "8" in msg_type:
            cl_ord_id = response.getFieldValue(11)
            if self.id_matches(cl_ord_id):
                self.handle_execution_report(response, "Order update(batch)")
                return

        if self.action in {"buy", "sell", "close"} and msg_type == "j":
            reject_ref_id = response.getFieldValue(379)
            if self.id_matches(reject_ref_id):
                reject = {
                    "ref_id": reject_ref_id,
                    "ref_seq_num": response.getFieldValue(45),
                    "reason": response.getFieldValue(58),
                    "reject_reason_code": response.getFieldValue(380),
                }
                self.log(f"Business message reject: {reject}")
                self.finish()
                return

        if self.action in {"buy", "sell", "close"} and isinstance(msg_type, list) and "j" in msg_type:
            reject_ref_id = response.getFieldValue(379)
            if self.id_matches(reject_ref_id):
                reject = {
                    "ref_id": reject_ref_id,
                    "ref_seq_num": response.getFieldValue(45),
                    "reason": response.getFieldValue(58),
                    "reject_reason_code": response.getFieldValue(380),
                }
                self.log(f"Business message reject(batch): {reject}")
                self.finish()

    def on_quote_message(self, client: Client, response) -> None:
        msg_type = response.getFieldValue(35)
        self.log(f"QUOTE {response.getMessage()}")

        if msg_type == "A" and not self.quote_logged_in:
            self.quote_logged_in = True
            self.start_quote_subscription()
            return

        if self.has_message_type(msg_type, "W") or self.has_message_type(msg_type, "X"):
            self.handle_market_data(response)
            return

        if self.has_message_type(msg_type, "j"):
            reject = {
                "ref_id": response.getFieldValue(379),
                "ref_seq_num": response.getFieldValue(45),
                "reason": response.getFieldValue(58),
                "reject_reason_code": response.getFieldValue(380),
            }
            self.log(f"Quote business message reject: {reject}")
            self.finish()

    def after_logon(self) -> None:
        if self.action == "transactions":
            request = OrderMassStatusRequest(self.trade_config)
            self.sent_id = f"MAS-{uuid.uuid4().hex[:12].upper()}"
            request.MassStatusReqID = self.sent_id
            request.MassStatusReqType = "7"
            self.client.send(request)
            self.log(f"Mass status request sent: MassStatusReqID={self.sent_id}")
            reactor.callLater(3, self.finish_transactions)
            return

        if self.action == "positions":
            request = RequestForPositions(self.trade_config)
            self.sent_id = f"POS-{uuid.uuid4().hex[:12].upper()}"
            request.PosReqID = self.sent_id
            self.client.send(request)
            self.log(f"Positions request sent: PosReqID={self.sent_id}")
            reactor.callLater(3, self.finish_positions)
            return

        if self.action == "close":
            request = RequestForPositions(self.trade_config)
            self.sent_id = f"POS-{uuid.uuid4().hex[:12].upper()}"
            request.PosReqID = self.sent_id
            self.client.send(request)
            self.log(f"Close flow positions request sent: PosReqID={self.sent_id}")
            reactor.callLater(3, self.execute_close_from_positions)
            return

        order = NewOrderSingle(self.trade_config)
        self.entry_order_id = f"ORD-{uuid.uuid4().hex[:12].upper()}"
        self.sent_id = self.entry_order_id
        self.entry_side = "1" if self.action == "buy" else "2"
        order.ClOrdID = self.entry_order_id
        order.Symbol = self.symbol
        order.Side = self.entry_side
        order.OrderQty = self.quantity
        order.OrdType = "1"
        self.client.send(order)
        self.log(
            f"{self.action.upper()} order sent: ClOrdID={self.entry_order_id}, "
            f"symbol={self.symbol}, qty={self.quantity}"
        )

    def handle_execution_report(self, response, label: str) -> None:
        result = {
            "exec_type": response.getFieldValue(150),
            "ord_status": response.getFieldValue(39),
            "order_id": response.getFieldValue(37),
            "position_id": response.getFieldValue(721),
            "symbol": response.getFieldValue(55),
            "side": response.getFieldValue(54),
            "filled_qty": response.getFieldValue(14),
            "avg_px": response.getFieldValue(6),
            "text": response.getFieldValue(58),
        }
        self.log(f"{label}: {result}")

        if self.exit_order_id and self.id_matches(response.getFieldValue(11), self.exit_order_id):
            if self.report_has_terminal_status(response):
                self.emit_result_table("EXIT", result, reason=self.exit_reason)
                self.log(f"Exit order completed via {self.exit_reason or 'manual exit'}")
                self.finish()
            return

        if self.entry_order_id and self.id_matches(response.getFieldValue(11), self.entry_order_id):
            if self.should_monitor_exit() and self.report_has_fill(response):
                avg_px = self.pick_last_value(response.getFieldValue(6))
                self.entry_avg_px = float(avg_px) if avg_px is not None else None
                self.entry_filled_qty = float(self.pick_last_value(response.getFieldValue(14)) or 0)
                self.entry_position_id = self.pick_last_value(response.getFieldValue(721))
                if not self.entry_avg_px or not self.entry_position_id or self.entry_filled_qty <= 0:
                    self.log("Filled entry missing avg_px, position_id, or qty; cannot start exit monitoring")
                    self.finish()
                    return
                self.log(
                    "Entry filled, starting exit monitoring: "
                    f"entry_px={self.entry_avg_px} qty={self.entry_filled_qty} "
                    f"position_id={self.entry_position_id} "
                    f"tp={self.take_profit_price()} sl={self.stop_loss_price()}"
                )
                self.start_quote_monitoring()
                return

            if not self.should_monitor_exit() and self.report_has_terminal_status(response):
                self.emit_result_table(self.action.upper(), result)
                self.finish()
                return

            if self.should_monitor_exit() and self.report_is_rejected(response):
                self.finish()

        if self.action == "close" and self.report_has_terminal_status(response):
            self.emit_result_table("CLOSE", result)
            self.finish()

    def start_quote_monitoring(self) -> None:
        if self.quote_client is None:
            self.log("Exit monitoring requested but QUOTE client is not configured")
            self.finish()
            return
        if self.quote_client.running:
            return
        self.quote_client.startService()

    def start_quote_subscription(self) -> None:
        request = MarketDataRequest(self.quote_config)
        self.market_data_request_id = f"MD-{uuid.uuid4().hex[:12].upper()}"
        request.MDReqID = self.market_data_request_id
        request.SubscriptionRequestType = "1"
        request.MarketDepth = 1
        request.MDUpdateType = 0
        request.NoMDEntryTypes = 1
        request.MDEntryType = "0"
        request.NoRelatedSym = 1
        request.Symbol = self.symbol
        self.quote_client.send(request)
        self.log(
            "Quote market data request sent: "
            f"MDReqID={self.market_data_request_id} symbol={self.symbol}"
        )

    def handle_market_data(self, response) -> None:
        entry_types = response.getFieldValue(269)
        prices = response.getFieldValue(270)
        if isinstance(entry_types, list):
            for idx, entry_type in enumerate(entry_types):
                price = value_at(prices, idx)
                self.record_market_price(entry_type, price)
        else:
            self.record_market_price(entry_types, prices)

        self.log(
            f"Exit monitor prices: bid={self.last_bid} ask={self.last_ask} "
            f"tp={self.take_profit_price()} sl={self.stop_loss_price()}"
        )
        self.evaluate_exit()

    def record_market_price(self, entry_type, price) -> None:
        if price is None:
            return
        if entry_type == "0":
            self.last_bid = float(price)
        elif entry_type == "1":
            self.last_ask = float(price)

    def evaluate_exit(self) -> None:
        if self.exit_triggered or self.entry_avg_px is None or self.entry_position_id is None:
            return

        tp_price = self.take_profit_price()
        sl_price = self.stop_loss_price()

        if self.entry_side == "1":
            if tp_price is not None and self.last_bid is not None and self.last_bid >= tp_price:
                self.send_exit_order("take-profit")
                return
            if sl_price is not None and self.last_bid is not None and self.last_bid <= sl_price:
                self.send_exit_order("stop-loss")
                return
        elif self.entry_side == "2":
            if tp_price is not None and self.last_ask is not None and self.last_ask <= tp_price:
                self.send_exit_order("take-profit")
                return
            if sl_price is not None and self.last_ask is not None and self.last_ask >= sl_price:
                self.send_exit_order("stop-loss")

    def send_exit_order(self, reason: str) -> None:
        if self.exit_triggered:
            return
        self.exit_triggered = True
        self.exit_reason = reason
        order = NewOrderSingle(self.trade_config)
        self.exit_order_id = f"EXT-{uuid.uuid4().hex[:12].upper()}"
        self.sent_id = self.exit_order_id
        order.ClOrdID = self.exit_order_id
        order.Symbol = self.symbol
        order.Side = "2" if self.entry_side == "1" else "1"
        order.OrderQty = self.entry_filled_qty
        order.OrdType = "1"
        order.PosMaintRptID = self.entry_position_id
        self.client.send(order)
        self.log(
            "Exit order sent: "
            f"reason={reason} ClOrdID={self.exit_order_id} position_id={self.entry_position_id} "
            f"side={order.Side} qty={self.entry_filled_qty}"
        )

    def take_profit_price(self) -> float | None:
        if self.take_profit_pct is None or self.entry_avg_px is None:
            return None
        if self.entry_side == "1":
            return self.entry_avg_px * (1 + self.take_profit_pct / 100)
        return self.entry_avg_px * (1 - self.take_profit_pct / 100)

    def stop_loss_price(self) -> float | None:
        if self.stop_loss_pct is None or self.entry_avg_px is None:
            return None
        if self.entry_side == "1":
            return self.entry_avg_px * (1 - self.stop_loss_pct / 100)
        return self.entry_avg_px * (1 + self.stop_loss_pct / 100)

    def execute_close_from_positions(self) -> None:
        if self.completed:
            return

        target = None
        if self.close_position_id:
            for position in self.collected_positions:
                if str(position.get("position_id")) == self.close_position_id:
                    target = position
                    break
        else:
            for position in self.collected_positions:
                if str(position.get("symbol")) == self.symbol:
                    target = position
                    break

        if target is None:
            self.out(
                "Close target not found. "
                f"position_id_filter={self.close_position_id or 'auto-by-symbol'} "
                f"symbol={self.symbol}"
            )
            self.finish()
            return

        long_qty = float(target.get("long_qty") or 0)
        short_qty = float(target.get("short_qty") or 0)
        if long_qty <= 0 and short_qty <= 0:
            self.out(f"Target position has no open quantity: {target}")
            self.finish()
            return

        close_side = "2" if long_qty > 0 else "1"
        close_qty = long_qty if long_qty > 0 else short_qty
        position_id = str(target.get("position_id"))
        symbol = str(target.get("symbol"))

        order = NewOrderSingle(self.trade_config)
        self.sent_id = f"CLS-{uuid.uuid4().hex[:12].upper()}"
        order.ClOrdID = self.sent_id
        order.Symbol = symbol
        order.Side = close_side
        order.OrderQty = close_qty
        order.OrdType = "1"
        order.PosMaintRptID = position_id
        self.client.send(order)
        self.log(
            "CLOSE order sent: "
            f"ClOrdID={self.sent_id}, position_id={position_id}, symbol={symbol}, "
            f"side={close_side}, qty={close_qty}"
        )

    def finish_positions(self) -> None:
        if self.completed:
            return
        if self.position_reports_count == 0:
            self.log("No open positions returned")
        self.finish()

    def finish_transactions(self) -> None:
        if self.completed:
            return
        if not self.collected_transactions:
            print("No transactions found")
        else:
            print(f"Transactions list ({len(self.collected_transactions)} total):")
            headers = ["Order ID", "Symbol", "Side", "Qty", "Avg Price", "Cum Qty", "Status"]
            rows = []
            for tx in self.collected_transactions:
                order_id = self.pick_last_value(tx["order_id"]) or ""
                symbol_id = self.pick_last_value(tx["symbol"]) or ""
                symbol = next((k for k, v in {"BTCUSD": "101"}.items() if v == symbol_id), symbol_id)
                side = self.describe_side(self.pick_last_value(tx["side"]))
                qty = self.pick_last_value(tx["qty"]) or ""
                avg_px = self.pick_last_value(tx["avg_px"]) or ""
                cum_qty = self.pick_last_value(tx["cum_qty"]) or ""
                status = self.describe_status(tx)
                
                rows.append([order_id, symbol, side, str(qty), str(avg_px), str(cum_qty), status])
            
            col_widths = [len(h) for h in headers]
            for row in rows:
                for idx, val in enumerate(row):
                    col_widths[idx] = max(col_widths[idx], len(val))
            
            border = "+" + "+".join(f"-{'-' * w}-" for w in col_widths) + "+"
            header_str = "|" + "|".join(f" {headers[idx].ljust(w)} " for idx, w in enumerate(col_widths)) + "|"
            print(border)
            print(header_str)
            print(border)
            for row in rows:
                row_str = "|" + "|".join(f" {row[idx].ljust(w)} " for idx, w in enumerate(col_widths)) + "|"
                print(row_str)
            print(border)
            
        self.finish()

    def emit_result_table(self, action_label: str, result: dict, reason: str | None = None) -> None:
        rows = [
            ("Account", self.trade_config["Username"]),
            ("Action", action_label),
            ("Symbol", self.symbol_requested),
            ("Side", self.describe_side(self.pick_last_value(result.get("side")))),
            ("Qty", str(self.pick_last_value(result.get("filled_qty")) or self.quantity)),
            ("Order ID", str(self.pick_last_value(result.get("order_id")) or "")),
            ("Position ID", str(self.pick_last_value(result.get("position_id")) or self.entry_position_id or self.close_position_id or "")),
            ("Avg Price", str(self.pick_last_value(result.get("avg_px")) or "")),
            ("Status", self.describe_status(result)),
        ]
        if reason:
            rows.append(("Reason", reason))
        print(format_terminal_table(rows))

    @staticmethod
    def pick_last_value(value):
        if isinstance(value, list):
            if value:
                return value[-1]
            return None
        return value

    @staticmethod
    def describe_side(side: str | None) -> str:
        mapping = {"1": "BUY", "2": "SELL"}
        return mapping.get(side or "", side or "")

    def describe_status(self, result: dict) -> str:
        exec_type = self.pick_last_value(result.get("exec_type"))
        ord_status = self.pick_last_value(result.get("ord_status"))
        if exec_type in {"F", "2"} or ord_status == "2":
            return "FILLED"
        if exec_type == "8" or ord_status == "8":
            return "REJECTED"
        if exec_type == "0" or ord_status == "0":
            return "NEW"
        return str(exec_type or ord_status or "")

    @staticmethod
    def has_message_type(msg_type, expected: str) -> bool:
        if isinstance(msg_type, list):
            return expected in msg_type
        return msg_type == expected

    @staticmethod
    def report_has_terminal_status(response) -> bool:
        exec_type = response.getFieldValue(150)
        ord_status = response.getFieldValue(39)
        exec_values = exec_type if isinstance(exec_type, list) else [exec_type]
        status_values = ord_status if isinstance(ord_status, list) else [ord_status]
        return any(value in {"2", "4", "8", "C", "F"} for value in exec_values + status_values if value is not None)

    @staticmethod
    def report_has_fill(response) -> bool:
        exec_type = response.getFieldValue(150)
        ord_status = response.getFieldValue(39)
        filled_qty = response.getFieldValue(14)
        exec_values = exec_type if isinstance(exec_type, list) else [exec_type]
        status_values = ord_status if isinstance(ord_status, list) else [ord_status]
        fill_values = filled_qty if isinstance(filled_qty, list) else [filled_qty]
        has_fill_status = any(value in {"1", "2", "F"} for value in exec_values + status_values if value is not None)
        has_filled_qty = any(float(value or 0) > 0 for value in fill_values)
        return has_fill_status and has_filled_qty

    @staticmethod
    def report_is_rejected(response) -> bool:
        exec_type = response.getFieldValue(150)
        ord_status = response.getFieldValue(39)
        exec_values = exec_type if isinstance(exec_type, list) else [exec_type]
        status_values = ord_status if isinstance(ord_status, list) else [ord_status]
        return any(value in {"8"} for value in exec_values + status_values if value is not None)

    def id_matches(self, response_id, expected_id=None) -> bool:
        expected_id = expected_id or self.sent_id
        if expected_id is None:
            return False
        if response_id is None:
            return False
        if isinstance(response_id, list):
            return expected_id in response_id
        return response_id == expected_id

    def on_timeout(self) -> None:
        if self.completed:
            return
        self.out(f"Timeout after {self.timeout_seconds}s")
        self.finish()

    def finish(self) -> None:
        if self.completed:
            return
        self.completed = True
        if self.timeout_call and self.timeout_call.active():
            self.timeout_call.cancel()
        self.client.stopService()
        if self.quote_client is not None:
            self.quote_client.stopService()
        self.done_event.set()


def sell() -> int:
    load_env_file(".env")
    try:
        action = "sell"
        symbol = "BTCUSD"
        quantity = 0.01
        timeout_seconds = 30
        reset_seq_num = True
        close_position_id = None
        take_profit_pct = None
        stop_loss_pct = None
        minimal_output = True
        trade_config = build_fix_config("TRADE")
        quote_config = build_fix_config("QUOTE") if action in {"buy", "sell"} and (
            take_profit_pct is not None or stop_loss_pct is not None
        ) else None
        runner = TradeRunner(
            action=action,
            symbol=symbol,
            quantity=quantity,
            timeout_seconds=timeout_seconds,
            trade_config=trade_config,
            reset_seq_num=reset_seq_num,
            close_position_id=close_position_id,
            quote_config=quote_config,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            minimal_output=minimal_output,
        )
    except ValueError as error:
        print(error)
        return 1

    runner.start()
    return 0



def buy() -> int:
    load_env_file(".env")
    try:
        action = "buy"
        symbol = "BTCUSD"
        quantity = 0.01
        timeout_seconds = 30
        reset_seq_num = True
        close_position_id = None
        take_profit_pct = None
        stop_loss_pct = None
        minimal_output = True
        trade_config = build_fix_config("TRADE")
        quote_config = build_fix_config("QUOTE") if action in {"buy", "sell"} and (
            take_profit_pct is not None or stop_loss_pct is not None
        ) else None
        runner = TradeRunner(
            action=action,
            symbol=symbol,
            quantity=quantity,
            timeout_seconds=timeout_seconds,
            trade_config=trade_config,
            reset_seq_num=reset_seq_num,
            close_position_id=close_position_id,
            quote_config=quote_config,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            minimal_output=minimal_output,
        )
    except ValueError as error:
        print(error)
        return 1

    runner.start()
    return 0


def positions() -> int:
    load_env_file(".env")
    try:
        action = "positions"
        timeout_seconds = 30
        reset_seq_num = True
        trade_config = build_fix_config("TRADE")
        runner = TradeRunner(
            action=action,
            symbol=None,
            quantity=None,
            timeout_seconds=timeout_seconds,
            trade_config=trade_config,
            reset_seq_num=reset_seq_num,
            close_position_id=None,
            quote_config=None,
            take_profit_pct=None,
            stop_loss_pct=None,
            minimal_output=True,
        )
    except ValueError as error:
        print(error)
        return 1

    runner.start()
    return 0


def main() -> int:
    load_env_file(".env")
    apply_cli_action_override()
    try:
        (
            action,
            symbol,
            quantity,
            timeout_seconds,
            reset_seq_num,
            close_position_id,
            take_profit_pct,
            stop_loss_pct,
        ) = read_runtime_settings()
        minimal_output = read_output_settings()
        trade_config = build_fix_config("TRADE")
        quote_config = build_fix_config("QUOTE") if action in {"buy", "sell"} and (
            take_profit_pct is not None or stop_loss_pct is not None
        ) else None
        runner = TradeRunner(
            action=action,
            symbol=symbol,
            quantity=quantity,
            timeout_seconds=timeout_seconds,
            trade_config=trade_config,
            reset_seq_num=reset_seq_num,
            close_position_id=close_position_id,
            quote_config=quote_config,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            minimal_output=minimal_output,
        )
    except ValueError as error:
        print(error)
        return 1

    runner.start()
    return 0


def transactions() -> int:
    load_env_file(".env")
    try:
        action = "transactions"
        timeout_seconds = 30
        reset_seq_num = True
        trade_config = build_fix_config("TRADE")
        runner = TradeRunner(
            action=action,
            symbol=None,
            quantity=None,
            timeout_seconds=timeout_seconds,
            trade_config=trade_config,
            reset_seq_num=reset_seq_num,
            close_position_id=None,
            quote_config=None,
            take_profit_pct=None,
            stop_loss_pct=None,
            minimal_output=True,
        )
    except ValueError as error:
        print(error)
        return 1

    runner.start()
    return 0


def closeposition(position_id: str) -> int:
    load_env_file(".env")
    try:
        action = "close"
        symbol = "BTCUSD"
        quantity = 0.01
        timeout_seconds = 30
        reset_seq_num = True
        close_position_id = str(position_id)
        minimal_output = True
        trade_config = build_fix_config("TRADE")
        runner = TradeRunner(
            action=action,
            symbol=symbol,
            quantity=quantity,
            timeout_seconds=timeout_seconds,
            trade_config=trade_config,
            reset_seq_num=reset_seq_num,
            close_position_id=close_position_id,
            quote_config=None,
            take_profit_pct=None,
            stop_loss_pct=None,
            minimal_output=minimal_output,
        )
    except ValueError as error:
        print(error)
        return 1

    runner.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())

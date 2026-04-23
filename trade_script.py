import importlib
import os
import sys
import uuid

ctrader_fix = importlib.import_module("ctrader_fix")
Client = ctrader_fix.Client
LogonRequest = ctrader_fix.LogonRequest
NewOrderSingle = ctrader_fix.NewOrderSingle
RequestForPositions = ctrader_fix.RequestForPositions
reactor = ctrader_fix.reactor


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
    value = os.getenv(name, default)
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


def resolve_symbol_id(symbol: str) -> str:
    if symbol.isdigit():
        return symbol
    env_symbol = get_env(f"SYMBOL_{symbol.upper()}_ID", "")
    if env_symbol:
        return env_symbol
    defaults = {"BTCUSD": "101"}
    return defaults.get(symbol.upper(), symbol)


def read_runtime_settings() -> tuple[str, str, float, int, bool, str]:
    action = get_env("TRADE_ACTION", "positions").lower()
    if action not in {"positions", "buy", "sell", "close"}:
        raise ValueError("TRADE_ACTION must be one of: positions, buy, sell, close")
    symbol = get_env("TRADE_SYMBOL", "BTCUSD")
    quantity = float(get_env("TRADE_QTY", "0.01"))
    timeout_seconds = int(get_env("TRADE_TIMEOUT", "20"))
    reset_seq_num = str_to_bool(get_env("FIX_RESET_SEQ_NUM", "true"))
    close_position_id = get_env("TRADE_POSITION_ID", "")
    return action, symbol, quantity, timeout_seconds, reset_seq_num, close_position_id


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
    ):
        self.action = action
        self.symbol = resolve_symbol_id(symbol)
        self.symbol_requested = symbol
        self.quantity = quantity
        self.timeout_seconds = timeout_seconds
        self.trade_config = trade_config
        self.reset_seq_num = reset_seq_num
        self.close_position_id = close_position_id
        self.client = Client(
            self.trade_config["Host"],
            self.trade_config["Port"],
            ssl=self.trade_config["SSL"],
            delimiter="\x01",
        )
        self.client.setConnectedCallback(self.on_connected)
        self.client.setDisconnectedCallback(self.on_disconnected)
        self.client.setMessageReceivedCallback(self.on_message)
        self.logged_in = False
        self.completed = False
        self.sent_id = None
        self.position_reports_count = 0
        self.timeout_call = None
        self.collected_positions = []

    def start(self) -> None:
        self.timeout_call = reactor.callLater(self.timeout_seconds, self.on_timeout)
        self.client.startService()
        reactor.run()

    def on_connected(self, client: Client) -> None:
        print("Connected to cTrader TRADE FIX endpoint")
        print(
            "Logon config: "
            f"host={self.trade_config['Host']} port={self.trade_config['Port']} ssl={self.trade_config['SSL']} "
            f"username={self.trade_config['Username']} sender_comp={self.trade_config['SenderCompID']} "
            f"sender_sub={self.trade_config['SenderSubID']} target_comp={self.trade_config['TargetCompID']} "
            f"target_sub={self.trade_config['TargetSubID']} heartbeat={self.trade_config['HeartBeat']} "
            f"reset_seq_num={self.reset_seq_num}"
        )
        if self.symbol_requested != self.symbol:
            print(f"Symbol mapping: requested={self.symbol_requested} resolved={self.symbol}")
        logon = LogonRequest(self.trade_config)
        logon.ResetSeqNum = self.reset_seq_num
        client.send(logon)

    def on_disconnected(self, client: Client, reason) -> None:
        print(f"Disconnected: {reason}")
        if reactor.running:
            reactor.stop()

    def on_message(self, client: Client, response) -> None:
        msg_type = response.getFieldValue(35)
        print(response.getMessage())

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
            print(f"Position report #{self.position_reports_count}: {position}")
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
            print(f"Close candidate: {position}")
            return

        if self.action == "positions" and isinstance(msg_type, list) and "AP" in msg_type:
            position_ids = response.getFieldValue(721)
            symbols = response.getFieldValue(55)
            long_qtys = response.getFieldValue(704)
            short_qtys = response.getFieldValue(705)
            settl_prices = response.getFieldValue(730)
            count = len(position_ids) if isinstance(position_ids, list) else msg_type.count("AP")
            self.position_reports_count += count
            print(f"Position reports received in batch: count={count}")
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
                    print(f"Position report(batch) #{idx + 1}: {position}")
            return

        if self.action == "close" and isinstance(msg_type, list) and "AP" in msg_type:
            position_ids = response.getFieldValue(721)
            symbols = response.getFieldValue(55)
            long_qtys = response.getFieldValue(704)
            short_qtys = response.getFieldValue(705)
            settl_prices = response.getFieldValue(730)
            count = len(position_ids) if isinstance(position_ids, list) else msg_type.count("AP")
            print(f"Close candidates received in batch: count={count}")
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
                    print(f"Close candidate(batch) #{idx + 1}: {position}")
            return

        if self.action in {"buy", "sell", "close"} and msg_type == "8":
            cl_ord_id = response.getFieldValue(11)
            if self.id_matches(cl_ord_id):
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
                print(f"Order update: {result}")
                self.finish()
                return

        if self.action in {"buy", "sell", "close"} and isinstance(msg_type, list) and "8" in msg_type:
            cl_ord_id = response.getFieldValue(11)
            if self.id_matches(cl_ord_id):
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
                print(f"Order update(batch): {result}")
                self.finish()
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
                print(f"Business message reject: {reject}")
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
                print(f"Business message reject(batch): {reject}")
                self.finish()

    def after_logon(self) -> None:
        if self.action == "positions":
            request = RequestForPositions(self.trade_config)
            self.sent_id = f"POS-{uuid.uuid4().hex[:12].upper()}"
            request.PosReqID = self.sent_id
            self.client.send(request)
            print(f"Positions request sent: PosReqID={self.sent_id}")
            reactor.callLater(3, self.finish_positions)
            return

        if self.action == "close":
            request = RequestForPositions(self.trade_config)
            self.sent_id = f"POS-{uuid.uuid4().hex[:12].upper()}"
            request.PosReqID = self.sent_id
            self.client.send(request)
            print(f"Close flow positions request sent: PosReqID={self.sent_id}")
            reactor.callLater(3, self.execute_close_from_positions)
            return

        order = NewOrderSingle(self.trade_config)
        self.sent_id = f"ORD-{uuid.uuid4().hex[:12].upper()}"
        order.ClOrdID = self.sent_id
        order.Symbol = self.symbol
        order.Side = "1" if self.action == "buy" else "2"
        order.OrderQty = self.quantity
        order.OrdType = "1"
        self.client.send(order)
        print(
            f"{self.action.upper()} order sent: ClOrdID={self.sent_id}, "
            f"symbol={self.symbol}, qty={self.quantity}"
        )

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
            print(
                "Close target not found. "
                f"position_id_filter={self.close_position_id or 'auto-by-symbol'} "
                f"symbol={self.symbol}"
            )
            self.finish()
            return

        long_qty = float(target.get("long_qty") or 0)
        short_qty = float(target.get("short_qty") or 0)
        if long_qty <= 0 and short_qty <= 0:
            print(f"Target position has no open quantity: {target}")
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
        print(
            "CLOSE order sent: "
            f"ClOrdID={self.sent_id}, position_id={position_id}, symbol={symbol}, "
            f"side={close_side}, qty={close_qty}"
        )

    def finish_positions(self) -> None:
        if self.completed:
            return
        if self.position_reports_count == 0:
            print("No open positions returned")
        self.finish()

    def id_matches(self, response_id) -> bool:
        if response_id is None:
            return False
        if isinstance(response_id, list):
            return self.sent_id in response_id
        return response_id == self.sent_id

    def on_timeout(self) -> None:
        if self.completed:
            return
        print(f"Timeout after {self.timeout_seconds}s")
        self.finish()

    def finish(self) -> None:
        if self.completed:
            return
        self.completed = True
        if self.timeout_call and self.timeout_call.active():
            self.timeout_call.cancel()
        self.client.stopService()
        if reactor.running:
            reactor.callLater(0.1, reactor.stop)


def main() -> int:
    load_env_file(".env")
    try:
        action, symbol, quantity, timeout_seconds, reset_seq_num, close_position_id = read_runtime_settings()
        trade_config = build_fix_config("TRADE")
        runner = TradeRunner(
            action=action,
            symbol=symbol,
            quantity=quantity,
            timeout_seconds=timeout_seconds,
            trade_config=trade_config,
            reset_seq_num=reset_seq_num,
            close_position_id=close_position_id,
        )
    except ValueError as error:
        print(error)
        return 1

    runner.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())

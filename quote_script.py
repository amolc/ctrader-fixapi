import importlib
import os
import sys
import uuid

ctrader_fix = importlib.import_module("ctrader_fix")
Client = ctrader_fix.Client
LogonRequest = ctrader_fix.LogonRequest
MarketDataRequest = ctrader_fix.MarketDataRequest
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


def str_to_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on", "y"}


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
        "Port": port,
        "SSL": ssl,
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


def value_at(value, idx: int):
    if isinstance(value, list):
        if idx < len(value):
            return value[idx]
        return None
    if idx == 0:
        return value
    return None


def read_runtime_settings() -> tuple[str, int, bool]:
    symbol = get_env("QUOTE_SYMBOL", get_env("TRADE_SYMBOL", "BTCUSD"))
    timeout_seconds = int(get_env("QUOTE_TIMEOUT", "10"))
    reset_seq_num = str_to_bool(get_env("FIX_RESET_SEQ_NUM", "true"))
    return symbol, timeout_seconds, reset_seq_num


class QuoteRunner:
    def __init__(self, symbol: str, timeout_seconds: int, quote_config: dict, reset_seq_num: bool):
        self.symbol_requested = symbol
        self.symbol = resolve_symbol_id(symbol)
        self.timeout_seconds = timeout_seconds
        self.quote_config = quote_config
        self.reset_seq_num = reset_seq_num
        self.client = Client(
            self.quote_config["Host"],
            self.quote_config["Port"],
            ssl=self.quote_config["SSL"],
            delimiter="\x01",
        )
        self.client.setConnectedCallback(self.on_connected)
        self.client.setDisconnectedCallback(self.on_disconnected)
        self.client.setMessageReceivedCallback(self.on_message)
        self.logged_in = False
        self.completed = False
        self.timeout_call = None
        self.finish_call = None
        self.market_data_messages = 0
        self.request_ids = []

    def start(self) -> None:
        self.timeout_call = reactor.callLater(self.timeout_seconds, self.on_timeout)
        self.client.startService()
        reactor.run()

    def on_connected(self, client: Client) -> None:
        print("Connected to cTrader QUOTE FIX endpoint")
        print(
            "Logon config: "
            f"host={self.quote_config['Host']} port={self.quote_config['Port']} ssl={self.quote_config['SSL']} "
            f"username={self.quote_config['Username']} sender_comp={self.quote_config['SenderCompID']} "
            f"sender_sub={self.quote_config['SenderSubID']} target_comp={self.quote_config['TargetCompID']} "
            f"target_sub={self.quote_config['TargetSubID']} heartbeat={self.quote_config['HeartBeat']} "
            f"reset_seq_num={self.reset_seq_num}"
        )
        if self.symbol_requested != self.symbol:
            print(f"Symbol mapping: requested={self.symbol_requested} resolved={self.symbol}")
        logon = LogonRequest(self.quote_config)
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

        if self.has_message_type(msg_type, "W") or self.has_message_type(msg_type, "X"):
            self.market_data_messages += 1
            self.print_market_data(response)
            if self.finish_call is None:
                self.finish_call = reactor.callLater(2, self.finish)
            return

        if self.has_message_type(msg_type, "j"):
            reject = {
                "ref_id": response.getFieldValue(379),
                "ref_seq_num": response.getFieldValue(45),
                "reason": response.getFieldValue(58),
                "reject_reason_code": response.getFieldValue(380),
            }
            print(f"Business message reject: {reject}")
            self.finish()

    def after_logon(self) -> None:
        self.send_market_data_request()

    def send_market_data_request(self) -> None:
        request = MarketDataRequest(self.quote_config)
        request_id = f"MD-{uuid.uuid4().hex[:12].upper()}"
        request.MDReqID = request_id
        request.SubscriptionRequestType = "1"
        request.MarketDepth = 1
        request.MDUpdateType = 0
        request.NoMDEntryTypes = 1
        request.MDEntryType = "0"
        request.NoRelatedSym = 1
        request.Symbol = self.symbol
        self.request_ids.append(request_id)
        self.client.send(request)
        print(
            f"Market data request sent: MDReqID={request_id}, "
            f"symbol={self.symbol}"
        )

    def print_market_data(self, response) -> None:
        entry_types = response.getFieldValue(269)
        prices = response.getFieldValue(270)
        sizes = response.getFieldValue(271)
        md_req_ids = response.getFieldValue(262)
        symbols = response.getFieldValue(55)

        if isinstance(entry_types, list):
            print(f"Market data update count={len(entry_types)}")
            for idx, entry_type in enumerate(entry_types):
                print(
                    "Market data entry: "
                    f"md_req_id={value_at(md_req_ids, idx)} "
                    f"symbol={value_at(symbols, idx) or self.symbol} "
                    f"entry_type={self.entry_type_name(entry_type)} "
                    f"price={value_at(prices, idx)} "
                    f"size={value_at(sizes, idx)}"
                )
            return

        print(
            "Market data entry: "
            f"md_req_id={md_req_ids} "
            f"symbol={symbols or self.symbol} "
            f"entry_type={self.entry_type_name(entry_types)} "
            f"price={prices} "
            f"size={sizes}"
        )

    @staticmethod
    def has_message_type(msg_type, expected: str) -> bool:
        if isinstance(msg_type, list):
            return expected in msg_type
        return msg_type == expected

    @staticmethod
    def entry_type_name(entry_type) -> str:
        mapping = {
            "0": "BID",
            "1": "ASK",
            "2": "TRADE",
            "4": "OPEN",
            "5": "CLOSE",
            "7": "HIGH",
            "8": "LOW",
        }
        if isinstance(entry_type, list):
            return ",".join(mapping.get(value, str(value)) for value in entry_type)
        return mapping.get(entry_type, str(entry_type))

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
        if self.finish_call and self.finish_call.active():
            self.finish_call.cancel()
        self.client.stopService()
        if reactor.running:
            reactor.callLater(0.1, reactor.stop)


def main() -> int:
    load_env_file(".env")
    try:
        symbol, timeout_seconds, reset_seq_num = read_runtime_settings()
        quote_config = build_fix_config("QUOTE")
        runner = QuoteRunner(
            symbol=symbol,
            timeout_seconds=timeout_seconds,
            quote_config=quote_config,
            reset_seq_num=reset_seq_num,
        )
    except ValueError as error:
        print(error)
        return 1

    runner.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())

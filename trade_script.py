#!/usr/bin/env python
import os
import time
import logging
from fixaccount import FixAccount

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def load_single_account():
    df = __import__('pandas').read_csv('accounts.csv')
    if df.empty:
        return None
    row = df.iloc[0].to_dict()
    return FixAccount(row)


def format_trade_table(fields: dict) -> str:
    lines = ["| Field | Value |", "| --- | --- |"]
    for key, value in fields.items():
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


def format_positions_table(positions) -> str:
    if not positions:
        return "No open positions"
    lines = ["| Account | PosID | Symbol | Side | Amount | Price |"]
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for pos in positions:
        lines.append(f"| {pos.get('account', '')} | {pos.get('pos_id', '')} | {pos.get('name', '')} | {pos.get('side', '')} | {pos.get('amount', '')} | {pos.get('price', '')} |")
    return "\n".join(lines)


def main():
    action = os.environ.get("TRADE_ACTION", "").lower()
    symbol = os.environ.get("TRADE_SYMBOL", "BTCUSD")
    qty = float(os.environ.get("TRADE_QTY", "0.01")) if os.environ.get("TRADE_QTY") else 0.01

    account = load_single_account()
    if not account:
        print("No accounts found in accounts.csv")
        return 1

    if action == "positions":
        if not account.connect(wait_seconds=3):
            print("Connection failed")
            return 1
        try:
            positions = account.get_positions()
            if positions.empty:
                print("No open positions")
            else:
                print(format_positions_table(positions.to_dict('records')))
        finally:
            account.disconnect()
        return 0

    if not account.connect(wait_seconds=3):
        print("Connection failed")
        return 1

    try:
        if action == "buy":
            result = account.buy_market(symbol, qty)
            fields = {
                "Symbol": symbol, "Action": "BUY",
                "Status": "EXECUTED" if result.get("executed") else "PENDING",
                "Account": account.name, "Qty": str(qty),
                "Avg Price": str(result.get("fill_price", "")),
                "Order ID": str(result.get("trade_id", "")),
                "Position ID": str(result.get("position_id", "")),
                "Side": "Buy"
            }
            print(format_trade_table(fields))
            return 0 if result.get("executed") else 1

        elif action == "sell":
            result = account.sell_market(symbol, qty)
            fields = {
                "Symbol": symbol, "Action": "SELL",
                "Status": "EXECUTED" if result.get("executed") else "PENDING",
                "Account": account.name, "Qty": str(qty),
                "Avg Price": str(result.get("fill_price", "")),
                "Order ID": str(result.get("trade_id", "")),
                "Position ID": str(result.get("position_id", "")),
                "Side": "Sell"
            }
            print(format_trade_table(fields))
            return 0 if result.get("executed") else 1

        elif action == "close":
            position_id = os.environ.get("TRADE_POSITION_ID")
            if not position_id:
                print("TRADE_POSITION_ID required")
                return 1
            positions = account.api.positions()
            side = None
            for pos in positions:
                if str(pos.get("pos_id")) == str(position_id):
                    side = pos.get("side")
                    break
            if side == "Buy":
                result = account.closebuy(position_id=position_id)
            else:
                result = account.closesell(position_id=position_id)
            fields = {
                "Symbol": symbol, "Action": "CLOSE",
                "Status": "CLOSED" if result.get("closed") else "FAILED",
                "Account": account.name,
                "Position ID": position_id
            }
            print(format_trade_table(fields))
            return 0 if result.get("closed") else 1

        else:
            print(f"Unknown action: {action}")
            return 1
    finally:
        account.disconnect()


if __name__ == "__main__":
    exit(main())
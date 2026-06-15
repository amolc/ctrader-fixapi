#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
TRADE_SCRIPT = PROJECT_ROOT / "trade_script.py"


def load_env_file(path: Path, env: dict[str, str]) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in env:
            env[key] = value


def build_runtime_env() -> dict[str, str]:
    env = dict(os.environ)
    load_env_file(PROJECT_ROOT / ".env", env)
    return env


def run_action(action: str, symbol: str, qty: str, dry_run: bool) -> int:
    env = build_runtime_env()
    env["TRADE_ACTION"] = action
    env["TRADE_SYMBOL"] = symbol
    if qty:
        env["TRADE_QTY"] = qty

    if dry_run:
        print(f"{action.upper()} {symbol} {qty or '0.01'}")
        return 0

    result = subprocess.run(
        [sys.executable, str(TRADE_SCRIPT)],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    print(result.stdout.strip() or result.stderr.strip(), file=sys.stderr if result.stderr else sys.stdout)
    return result.returncode


def view_positions() -> int:
    env = build_runtime_env()
    env["TRADE_ACTION"] = "positions"

    result = subprocess.run(
        [sys.executable, str(TRADE_SCRIPT)],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    print(result.stdout.strip() or "No positions", file=sys.stderr if result.stderr else sys.stdout)
    return result.returncode


def run_prompt() -> int:
    while True:
        print("\n┌─ cTrader Terminal ─────────────────────────┐")
        print("│ 1) buy  - Place buy order                │")
        print("│ 2) sell - Place sell order               │")
        print("│ 3) view - Show open positions              │")
        print("│ q) quit - Exit                             │")
        print("└──────────────────────────────────────────┘")
        choice = input("Select> ").strip().lower()

        if choice in {"q", "quit", "exit"}:
            break
        if choice in {"1", "buy", "b"}:
            qty = input("Qty [0.01]: ").strip() or "0.01"
            run_action("buy", "BTCUSD", qty, False)
        elif choice in {"2", "sell", "s"}:
            qty = input("Qty [0.01]: ").strip() or "0.01"
            run_action("sell", "BTCUSD", qty, False)
        elif choice in {"3", "view", "v"}:
            view_positions()
        else:
            print("Unknown: 1=buy, 2=sell, 3=view, q=quit")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simple cTrader terminal.")
    parser.add_argument("action", nargs="?", choices=["buy", "sell", "view"])
    parser.add_argument("qty", nargs="?", default="0.01")
    parser.add_argument("--dry-run", "-n", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.action:
        return run_prompt()
    if args.action == "view":
        return view_positions()
    return run_action(args.action, "BTCUSD", args.qty, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
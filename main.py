#!/usr/bin/env python
"""Main script using FixAccount from fixaccount.py."""

import pandas as pd
import time
import logging
from fixaccount import FixAccount

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    # Load accounts
    df = pd.read_csv('accounts.csv')
    
    for _, row in df.iterrows():
        config = row.to_dict()
        account = FixAccount(config)
        
        # Connect
        if not account.connect(wait_seconds=3):
            logger.error(f"[{account.name}] Failed to connect")
            continue
        
        try:
            # Example: Place a buy order
            # result = account.buy_market('BTCUSD', 0.01)
            # logger.info(f"[{account.name}] Buy result: {result}")

            # # Example: Place a sell order
            # result = account.sell_market('BTCUSD', 0.01)
            # logger.info(f"[{account.name}] Sell result: {result}")
            
            # Get positions with open times
            # Note: open_time comes from ExecutionReports (35=8) captured when trades occur
            # cTrader doesn't support TradeCaptureReportRequest (35=AD)
            positions = account.get_positions()
            if not positions.empty:
                logger.info(f"[{account.name}] {len(positions)} positions")
                cols = ['account', 'pos_id', 'name', 'side', 'amount', 'price', 'open_time']
                print(positions[cols].to_string(index=False))
            else:
                logger.info(f"[{account.name}] No positions")
            
            # Get trade history
            logger.info(f"[{account.name}] Getting trade history...")
            trade_history = account.get_trade_history(days=7)
            if not trade_history.empty:
                logger.info(f"[{account.name}] {len(trade_history)} trades")
                print(trade_history.to_string(index=False))
            else:
                logger.info(f"[{account.name}] No trades")
        
            # # Example: Close all BTCUSD positions
            # result = account.closeall('BTCUSD')
            # logger.info(f"[{account.name}] Closeall result: {result['closed']}/{result['total_positions']} closed")
            account.disconnect()
            exit()
        except Exception as e:
            logger.error(f"[{account.name}] Error: {e}")
        finally:
            account.disconnect()


if __name__ == "__main__":
    main()

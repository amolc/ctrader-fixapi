#!/usr/bin/env python
"""Buy script - places market buy orders on all accounts using ejtraderCT."""

import pandas as pd
import time
import logging
from ejtraderCT.api.ctrader import Ctrader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_accounts(csv_path: str) -> list:
    """Load accounts from CSV."""
    df = pd.read_csv(csv_path)
    accounts = []
    for _, row in df.iterrows():
        accounts.append({
            'name': row['ACCOUNT_NAME'],
            'server': row['TRADE_HOST'],
            'password': row['FIX_PASSWORD'],
            'sender_comp_id': row['FIX_SENDER_COMP_ID'],
        })
    return accounts


def buy_market_single(account: dict, symbol: str, volume: float, confirm: bool = True) -> dict:
    """Connect to account and place market buy order with confirmation.
    
    Returns:
        dict with execution details
    """
    name = account['name']
    result = {
        'account': name,
        'symbol': symbol,
        'volume': volume,
        'trade_id': None,
        'executed': False,
        'position_id': None,
        'fill_price': None,
        'error': None
    }
    
    logger.info(f"[{name}] Connecting...")
    
    try:
        api = Ctrader(account['server'], account['sender_comp_id'], account['password'], debug=False)
        time.sleep(3)
        
        if not api.isconnected():
            result['error'] = 'Connection failed'
            logger.error(f"[{name}] Connection failed")
            return result
        
        logger.info(f"[{name}] Connected, subscribing to {symbol}...")
        api.subscribe(symbol)
        time.sleep(1)
        
        quote = api.quote(symbol)
        if quote:
            logger.info(f"[{name}] {symbol} bid={quote.get('bid')}, ask={quote.get('ask')}")
        
        # Place buy order
        logger.info(f"[{name}] Buying {volume} {symbol}...")
        trade_id = api.buy(symbol, volume, 0, 0)
        
        if not trade_id:
            result['error'] = 'Order placement failed'
            logger.error(f"[{name}] Order failed")
            api.logout()
            return result
        
        result['trade_id'] = trade_id
        logger.info(f"[{name}] Order placed: {trade_id}")
        
        if confirm:
            # Wait for confirmation
            time.sleep(3)
            positions = api.positions()
            for pos in positions:
                if pos.get('clid') == trade_id:
                    result['executed'] = True
                    result['position_id'] = pos.get('pos_id')
                    result['fill_price'] = pos.get('price')
                    logger.info(f"[{name}] EXECUTED: pos_id={pos.get('pos_id')}, price={pos.get('price')}")
                    break
            
            if not result['executed']:
                result['error'] = 'Order not found in positions'
                logger.warning(f"[{name}] Order status unclear")
        
        api.logout()
        logger.info(f"[{name}] Disconnected")
        
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"[{name}] Error: {e}")
    
    return result


def buy_all_accounts(symbol: str = "BTCUSD", volume: float = 0.01):
    """Place buy orders on all accounts."""
    accounts = load_accounts('accounts.csv')
    
    print(f"\n{'='*60}")
    print(f"PLACING BUY ORDERS: {symbol} x {volume}")
    print(f"Accounts: {len(accounts)}")
    print(f"{'='*60}\n")
    
    start = time.time()
    results = []
    
    for account in accounts:
        result = buy_market_single(account, symbol, volume)
        results.append(result)
    
    elapsed = time.time() - start
    
    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY - Completed in {elapsed:.1f}s")
    print(f"{'='*60}")
    for r in results:
        status = 'EXECUTED' if r['executed'] else 'FAILED'
        price = r.get('fill_price', 'N/A') if r['executed'] else 'N/A'
        print(f"  {r['account']}: {status} | pos_id={r.get('position_id', 'N/A')}, price={price}")
    print(f"{'='*60}\n")
    
    return results


if __name__ == "__main__":
    buy_all_accounts(symbol="BTCUSD", volume=0.01)

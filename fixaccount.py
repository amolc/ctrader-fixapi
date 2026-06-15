#!/usr/bin/env python
"""FixAccount - Clean wrapper around ejtraderCT for cTrader FIX API."""

import pandas as pd
import time
import logging
import json
import os
from ejtraderCT.api.ctrader import Ctrader

logger = logging.getLogger(__name__)


def str_to_bool(value):
    """Convert string value to boolean."""
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on", "y"}


def normalize_config(config: dict) -> dict:
    """Normalize input config from CSV format."""
    row = {k.strip(): (v or "").strip() if isinstance(v, str) else v
           for k, v in config.items()}
    return {
        'name': row.get('ACCOUNT_NAME', 'unknown'),
        'server': row.get('TRADE_HOST') or row.get('Host'),
        'sender_comp_id': row.get('FIX_SENDER_COMP_ID') or row.get('SenderCompID'),
        'password': row.get('FIX_PASSWORD') or row.get('Password'),
        'quote_port': int(row.get('QUOTE_PORT', 5201)),
        'trade_port': int(row.get('TRADE_PORT', 5202)),
    }


class FixAccount:
    """A single cTrader FIX trading session using ejtraderCT."""

    def __init__(self, config: dict):
        if 'sender_comp_id' in config:
            self.config = config
        else:
            self.config = normalize_config(config)
        self.name = self.config['name']
        self.api = None
        self.connected = False
        self.position_open_times = {}  # Track when positions were opened: {pos_id: timestamp}
        self._position_times_file = f".position_times_{self.name}.json"
        self._load_position_times()

    def _load_position_times(self):
        """Load position times from file."""
        try:
            if os.path.exists(self._position_times_file):
                with open(self._position_times_file, 'r') as f:
                    self.position_open_times = json.load(f)
                logger.info(f"[{self.name}] Loaded {len(self.position_open_times)} position times")
        except Exception as e:
            logger.warning(f"[{self.name}] Could not load position times: {e}")

    def _save_position_times(self):
        """Save position times to file."""
        try:
            with open(self._position_times_file, 'w') as f:
                json.dump(self.position_open_times, f)
        except Exception as e:
            logger.warning(f"[{self.name}] Could not save position times: {e}")

    def connect(self, wait_seconds: int = 3) -> bool:
        """Connect to cTrader."""
        try:
            logger.info(f"[{self.name}] Connecting...")
            self.api = Ctrader(
                self.config['server'],
                self.config['sender_comp_id'],
                self.config['password'],
                debug=False,
                quote_port=self.config.get('quote_port', 5201),
                trade_port=self.config.get('trade_port', 5202)
            )
            time.sleep(wait_seconds)
            self.connected = self.api.isconnected()
            logger.info(f"[{self.name}] Connected: {self.connected}")
            return self.connected
        except Exception as e:
            logger.error(f"[{self.name}] Connection error: {e}")
            return False

    def disconnect(self):
        """Logout and disconnect."""
        if self.api:
            self.api.logout()
            self.connected = False
            self._save_position_times()
            logger.info(f"[{self.name}] Disconnected")

    def get_positions(self) -> pd.DataFrame:
        """Get current positions as DataFrame with account column."""
        if not self.connected:
            return pd.DataFrame()
        positions = self.api.positions()
        df = pd.DataFrame(positions)
        if not df.empty:
            df.insert(0, 'account', self.name)
            # Sync times from FIX object's execution report tracking
            if hasattr(self.api.fix, 'position_open_times'):
                for pos_id, transact_time in self.api.fix.position_open_times.items():
                    if transact_time and pos_id not in self.position_open_times:
                        self.position_open_times[pos_id] = transact_time
            # Add open_time from captured ExecutionReports
            # NOTE: cTrader only sends ExecutionReports (35=8) with TransactTime for NEW trades
            # during the current session. For positions opened before connecting, we cannot
            # get the actual trade time since TradeCaptureReportRequest (35=AD) is not supported.
            def get_open_time(row):
                pos_id = str(row.get('pos_id', ''))
                # Try captured TransactTime from ExecutionReports
                tracked_time = self.position_open_times.get(pos_id, '')
                if tracked_time:
                    return tracked_time
                # No time available - position was opened before this session
                return ''
            df['open_time'] = df.apply(get_open_time, axis=1)
        return df

    def get_position_by_id(self, pos_id: str) -> dict:
        """Get details for a specific position by ID.
        
        Args:
            pos_id: Position ID (e.g., '40684619')
            
        Returns:
            dict: Position details or empty dict if not found
        """
        if not self.connected:
            return {}
        positions = self.api.positions()
        for pos in positions:
            if str(pos.get('pos_id', '')) == str(pos_id):
                # Add open_time from tracking
                pos['open_time'] = self.position_open_times.get(str(pos_id), '')
                return pos
        return {}

    def refresh_position_times(self) -> dict:
        """Sync position open times from ExecutionReports.
        
        Note: cTrader doesn't support TradeCaptureReportRequest (35=AD).
        We rely on ExecutionReports (35=8) which capture TransactTime when trades occur.
        
        Returns:
            dict: Mapping of pos_id to transact_time
        """
        if not self.connected:
            return {}
        # Sync from FIX object's position_open_times (populated by ExecutionReports)
        if hasattr(self.api.fix, 'position_open_times'):
            for pos_id, transact_time in self.api.fix.position_open_times.items():
                if transact_time and pos_id:
                    self.position_open_times[str(pos_id)] = transact_time
            self._save_position_times()
        return self.position_open_times

    def get_trade_history(self, days: int = 7) -> pd.DataFrame:
        """Get trade history from captured ExecutionReports.
        
        Note: cTrader doesn't support TradeCaptureReportRequest (35=AD).
        We use ExecutionReports (35=8) which are captured when trades occur.
        
        Args:
            days: Number of days to look back (default 7)
            
        Returns:
            DataFrame with trade history including transaction times
        """
        import logging
        if not self.connected:
            logging.info("get_trade_history: not connected")
            return pd.DataFrame()
        # Check FIX object's position_open_times
        if not hasattr(self.api.fix, 'position_open_times'):
            logging.info("get_trade_history: no position_open_times attribute")
            return pd.DataFrame()
        if not self.api.fix.position_open_times:
            logging.info("get_trade_history: position_open_times is empty (no ExecutionReports received)")
            return pd.DataFrame()
        logging.info(f"get_trade_history: found {len(self.api.fix.position_open_times)} entries")
        df = pd.DataFrame([
            {'pos_id': pos_id, 'transact_time': time}
            for pos_id, time in self.api.fix.position_open_times.items()
        ])
        df.insert(0, 'account', self.name)
        return df

    def buy_market(self, symbol: str, volume: float) -> dict:
        """Place market buy order with account info."""
        if not self.connected:
            return {'account': self.name, 'error': 'Not connected'}
        self.api.subscribe(symbol)
        time.sleep(1)
        trade_id = self.api.buy(symbol, volume, 0, 0)
        
        # Wait longer and retry to find the position
        max_retries = 10
        for attempt in range(max_retries):
            time.sleep(1)
            positions = self.api.positions()
            for pos in positions:
                if pos.get('clid') == trade_id:
                    pos_id = pos.get('pos_id')
                    # Record open time
                    open_time = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
                    self.position_open_times[pos_id] = open_time
                    return {
                        'account': self.name,
                        'trade_id': trade_id,
                        'executed': True,
                        'position_id': pos_id,
                        'fill_price': pos.get('price'),
                        'symbol': symbol,
                        'volume': volume,
                        'open_time': open_time
                    }
        
        return {'account': self.name, 'trade_id': trade_id, 'executed': False, 'symbol': symbol, 'volume': volume}

    def closebuy(self, position_id: str = None, trade_id: str = None) -> dict:
        """Close a specific buy position.
        
        Args:
            position_id: Position ID to close (pos_id)
            trade_id: Alternative - close position by trade ID (clid)
            
        Returns:
            dict with close result:
            - account: Account name
            - position_id: Closed position ID
            - trade_id: Trade ID if found
            - closed: True if successfully closed
            - error: Error message if any
        """
        result = {
            'account': self.name,
            'position_id': position_id,
            'trade_id': trade_id,
            'closed': False,
            'error': None
        }
        
        if not self.connected:
            result['error'] = 'Not connected'
            return result
        
        try:
            # If trade_id provided, find the position_id
            if trade_id and not position_id:
                positions = self.api.positions()
                for pos in positions:
                    if pos.get('clid') == trade_id and pos.get('side') == 'Buy':
                        position_id = pos.get('pos_id')
                        result['position_id'] = position_id
                        result['symbol'] = pos.get('name')
                        result['volume'] = pos.get('amount')
                        break
                if not position_id:
                    result['error'] = f'Buy position with trade_id {trade_id} not found'
                    return result
            
            if not position_id:
                result['error'] = 'No position_id or valid trade_id provided'
                return result
        
            # If we still don't have volume, get it from the position
            if not result.get('volume'):
                positions = self.api.positions()
                for pos in positions:
                    if pos.get('pos_id') == position_id:
                        result['volume'] = pos.get('amount')
                        result['symbol'] = pos.get('name')
                        break
        
            # Close the position (need amount for the API)
            position_amount = result.get('volume', 0)
            self.api.positionCloseById(position_id, position_amount)
            result['closed'] = True
            logger.info(f"[{self.name}] Closed buy position {position_id}")
            
            # Verify closure by checking positions again
            time.sleep(1)
            positions = self.api.positions()
            for pos in positions:
                if pos.get('pos_id') == position_id:
                    result['error'] = 'Position still exists after close command'
                    result['closed'] = False
                    return result
            
            result['verified'] = True
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"[{self.name}] Error closing position: {e}")
        
        return result

    def closesell(self, position_id: str = None, trade_id: str = None) -> dict:
        """Close a specific sell position.
        
        Args:
            position_id: Position ID to close (pos_id)
            trade_id: Alternative - close position by trade ID (clid)
            
        Returns:
            dict with close result:
            - account: Account name
            - position_id: Closed position ID
            - trade_id: Trade ID if found
            - closed: True if successfully closed
            - error: Error message if any
        """
        result = {
            'account': self.name,
            'position_id': position_id,
            'trade_id': trade_id,
            'closed': False,
            'error': None
        }
        
        if not self.connected:
            result['error'] = 'Not connected'
            return result
        
        try:
            # If trade_id provided, find the position_id
            if trade_id and not position_id:
                positions = self.api.positions()
                for pos in positions:
                    if pos.get('clid') == trade_id and pos.get('side') == 'Sell':
                        position_id = pos.get('pos_id')
                        result['position_id'] = position_id
                        result['symbol'] = pos.get('name')
                        result['volume'] = pos.get('amount')
                        break
                if not position_id:
                    result['error'] = f'Sell position with trade_id {trade_id} not found'
                    return result
            
            if not position_id:
                result['error'] = 'No position_id or valid trade_id provided'
                return result
            
            # If we still don't have volume, get it from the position
            if not result.get('volume'):
                positions = self.api.positions()
                for pos in positions:
                    if pos.get('pos_id') == position_id:
                        result['volume'] = pos.get('amount')
                        result['symbol'] = pos.get('name')
                        break
            
            # Close the position (need amount for the API)
            position_amount = result.get('volume', 0)
            self.api.positionCloseById(position_id, position_amount)
            result['closed'] = True
            logger.info(f"[{self.name}] Closed sell position {position_id}")
            
            # Verify closure by checking positions again
            time.sleep(1)
            positions = self.api.positions()
            for pos in positions:
                if pos.get('pos_id') == position_id:
                    result['error'] = 'Position still exists after close command'
                    result['closed'] = False
                    return result
            
            result['verified'] = True
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"[{self.name}] Error closing position: {e}")
        
        return result

    def sell_market(self, symbol: str, volume: float) -> dict:
        """Place market sell order with account info."""
        if not self.connected:
            return {'account': self.name, 'error': 'Not connected'}
        self.api.subscribe(symbol)
        time.sleep(1)
        trade_id = self.api.sell(symbol, volume, 0, 0)
        time.sleep(2)
        positions = self.api.positions()
        for pos in positions:
            if pos.get('clid') == trade_id:
                return {
                    'account': self.name,
                    'trade_id': trade_id,
                    'executed': True,
                    'position_id': pos.get('pos_id'),
                    'fill_price': pos.get('price'),
                    'symbol': symbol,
                    'volume': volume
                }
        return {'account': self.name, 'trade_id': trade_id, 'executed': False, 'symbol': symbol, 'volume': volume}

    def closeall(self, symbol: str) -> dict:
        """Close all positions (buy and sell) for a specific symbol.
        
        Args:
            symbol: Symbol to close all positions for (e.g., 'BTCUSD')
            
        Returns:
            dict with close summary:
            - account: Account name
            - symbol: Symbol closed
            - total_positions: Total positions found
            - closed: Number of positions successfully closed
            - failed: Number of positions that failed to close
            - details: List of individual close results
        """
        result = {
            'account': self.name,
            'symbol': symbol,
            'total_positions': 0,
            'closed': 0,
            'failed': 0,
            'details': []
        }
        
        if not self.connected:
            result['error'] = 'Not connected'
            return result
        
        try:
            # Get all positions for this symbol
            positions = self.api.positions()
            symbol_positions = [p for p in positions if p.get('name') == symbol]
            
            result['total_positions'] = len(symbol_positions)
            
            if not symbol_positions:
                logger.info(f"[{self.name}] No positions found for {symbol}")
                return result
            
            logger.info(f"[{self.name}] Closing {len(symbol_positions)} positions for {symbol}...")
            
            # Close each position
            for pos in symbol_positions:
                position_id = pos.get('pos_id')
                side = pos.get('side')
                amount = pos.get('amount', 0)
                
                try:
                    self.api.positionCloseById(position_id, amount)
                    result['closed'] += 1
                    result['details'].append({
                        'position_id': position_id,
                        'side': side,
                        'amount': amount,
                        'closed': True
                    })
                    logger.info(f"[{self.name}] Closed {side} position {position_id} ({amount} {symbol})")
                    time.sleep(0.5)  # Small delay between closes
                except Exception as e:
                    result['failed'] += 1
                    result['details'].append({
                        'position_id': position_id,
                        'side': side,
                        'amount': amount,
                        'closed': False,
                        'error': str(e)
                    })
                    logger.error(f"[{self.name}] Failed to close position {position_id}: {e}")
            
            # Verify all positions are closed
            time.sleep(1)
            remaining = [p for p in self.api.positions() if p.get('name') == symbol]
            if remaining:
                result['warning'] = f'{len(remaining)} positions still open'
                logger.warning(f"[{self.name}] {len(remaining)} positions still open for {symbol}")
            else:
                result['verified'] = True
                logger.info(f"[{self.name}] All {symbol} positions closed successfully")
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"[{self.name}] Error in closeall: {e}")
        
        return result

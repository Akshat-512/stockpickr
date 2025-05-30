#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Breeze API Client Module - Complete Implementation
Handles all API interactions and data fetching with all original functionality
"""

import datetime
import time
import logging
import json
import pandas as pd
import numpy as np
import yfinance as yf
from breeze_connect import BreezeConnect
from stock_utils import stock_mapper
from typing import Optional, Tuple, Dict, Any


class BreezeAPIClient:
    """Handles all Breeze API interactions - Complete Implementation"""

    def __init__(self, config):
        self.config = config
        self.breeze = None

        # API credentials
        self.API_KEY = config.get("APICredentials", "api_key", fallback="")
        self.API_SECRET = config.get("APICredentials", "api_secret", fallback="")
        self.SESSION_TOKEN = config.get("APICredentials", "session_token", fallback="")

        # Trading settings
        self.PAPER_TRADING = config.getboolean(
            "Strategy", "paper_trading_mode", fallback=True
        )
        self.MAX_WAIT_TIME = 60

    def initialize(self) -> bool:
        """Initialize API connection"""
        try:
            logging.info("Initializing Breeze API connection")

            self.breeze = BreezeConnect(api_key=self.API_KEY)
            self.breeze.generate_session(
                api_secret=self.API_SECRET, session_token=self.SESSION_TOKEN
            )

            # Validate connection
            user_profile = self.breeze.get_customer_details(
                api_session=self.SESSION_TOKEN
            )

            if user_profile and "Success" in user_profile:
                user_name = user_profile["Success"].get("name", "Unknown")
                logging.info(f"API connected successfully. User: {user_name}")
                return True
            else:
                logging.error(f"API validation failed: {user_profile}")
                return False

        except Exception as e:
            logging.error(f"Failed to initialize API: {e}")
            return False

    def get_current_price(
        self, stock_code: str, exchange_code: str = "NSE", max_retries: int = 3
    ) -> Optional[float]:
        """Get current market price with retry logic"""

        if self.breeze is None:
            logging.error("API not initialized")
            return None

        # Convert to Breeze symbol
        breeze_symbol = stock_mapper.get_breeze_symbol(stock_code)
        if breeze_symbol != stock_code:
            logging.debug(f"Converted {stock_code} to {breeze_symbol}")

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    wait_time = 2 ** (attempt - 1)
                    logging.debug(
                        f"Retry {attempt}/{max_retries} for {stock_code} - waiting {wait_time}s"
                    )
                    time.sleep(wait_time)

                # Get quote
                quote = self.breeze.get_quotes(
                    stock_code=breeze_symbol,
                    exchange_code=exchange_code,
                    expiry_date="",
                    product_type="cash",
                    right="",
                    strike_price="",
                )

                if not quote:
                    continue

                # Extract price using multiple strategies
                price = self._extract_price_from_quote(quote, stock_code)

                if price and price > 0:
                    return float(price)

            except Exception as e:
                logging.warning(
                    f"Error getting price for {stock_code} (attempt {attempt + 1}): {e}"
                )

        logging.error(
            f"Failed to get price for {stock_code} after {max_retries + 1} attempts"
        )
        return None

    def _extract_price_from_quote(
        self, quote: Dict, stock_code: str
    ) -> Optional[float]:
        """Extract price from quote response using multiple strategies"""
        try:
            # Strategy 1: Success list format
            if (
                isinstance(quote, dict)
                and "Success" in quote
                and isinstance(quote["Success"], list)
            ):
                for item in quote["Success"]:
                    if isinstance(item, dict):
                        for field in ["ltp", "last_price", "last", "close", "price"]:
                            if field in item and item[field] is not None:
                                try:
                                    price = float(item[field])
                                    if price > 0:
                                        return price
                                except (ValueError, TypeError):
                                    continue

            # Strategy 2: Direct fields
            if isinstance(quote, dict):
                for field in ["ltp", "last_price", "last", "close", "price"]:
                    if field in quote and quote[field] is not None:
                        try:
                            price = float(quote[field])
                            if price > 0:
                                return price
                        except (ValueError, TypeError):
                            continue

            # Strategy 3: Recursive search
            return self._find_price_recursively(quote)

        except Exception as e:
            logging.error(f"Error extracting price from quote: {e}")
            return None

    def _find_price_recursively(
        self, data: Any, depth: int = 0, max_depth: int = 3
    ) -> Optional[float]:
        """Recursively search for price in nested data"""
        if depth > max_depth or data is None:
            return None

        # Check if it's a reasonable price
        if isinstance(data, (int, float)) and 1 <= data <= 100000:
            return float(data)

        # Check string conversion
        if isinstance(data, str):
            try:
                price = float(data)
                if 1 <= price <= 100000:
                    return price
            except (ValueError, TypeError):
                pass

        # Search dictionaries
        if isinstance(data, dict):
            # Check price fields first
            for field in ["ltp", "last_price", "last", "close", "price"]:
                if field in data:
                    result = self._find_price_recursively(
                        data[field], depth + 1, max_depth
                    )
                    if result:
                        return result

        # Search lists
        if isinstance(data, list):
            for item in data:
                result = self._find_price_recursively(item, depth + 1, max_depth)
                if result:
                    return result

        return None

    def get_historical_data(
        self,
        stock_code: str,
        exchange_code: str = "NSE",
        interval: str = "1day",
        days: int = 300,
    ) -> Optional[pd.DataFrame]:
        """Get historical data for a stock"""
        try:
            # Convert to Breeze symbol
            breeze_symbol = stock_mapper.get_breeze_symbol(stock_code)

            # Calculate date range
            to_date = datetime.datetime.now()
            from_date = to_date - datetime.timedelta(days=days)

            from_date_str = from_date.strftime("%Y-%m-%dT00:00:00.000Z")
            to_date_str = to_date.strftime("%Y-%m-%dT23:59:59.000Z")

            logging.debug(f"Fetching historical data for {breeze_symbol}")

            # Fetch data
            hist_data = self.breeze.get_historical_data(
                interval=interval,
                from_date=from_date_str,
                to_date=to_date_str,
                stock_code=breeze_symbol,
                exchange_code=exchange_code,
                product_type="cash",
            )

            if hist_data and hist_data.get("Success") and len(hist_data["Success"]) > 0:
                df = pd.DataFrame(hist_data["Success"])

                # Convert data types
                numeric_cols = ["open", "high", "low", "close", "volume"]
                for col in numeric_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")

                if "datetime" in df.columns:
                    df["datetime"] = pd.to_datetime(df["datetime"])

                df = df.sort_values("datetime")
                logging.info(f"Retrieved {len(df)} data points for {stock_code}")
                return df
            else:
                logging.warning(f"No historical data for {stock_code}")
                return None

        except Exception as e:
            logging.error(f"Error fetching historical data for {stock_code}: {e}")
            return None

    def get_historical_data_index(self, stock_code, interval="1day", days=200):
        """Get historical data for an index using Yahoo Finance.
        Args:
            stock_code (str): Stock or index symbol (e.g., "NIFTY").
            interval (str): Time interval (e.g., "1day", "1hour").
            days (int): Number of days of historical data to fetch.

        Returns:
            pandas.DataFrame: Historical data with columns like datetime, open, high, low, close, volume.
                            Returns an empty DataFrame on error.
        """
        if not isinstance(stock_code, str):
            logging.error(f"Invalid stock_code type: {type(stock_code)}. Expected string.")
            return pd.DataFrame()
        try:
            # Map to Yahoo Finance symbols
            yahoo_symbol = {
                "NIFTY": "^NSEI",
                "SENSEX": "^BSESN",
                "BANKNIFTY": "^NSEBANK",
            }.get(stock_code, f"{stock_code}.NS")

            # Calculate date range
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=days)

            logging.info(f"Fetching data from Yahoo Finance for {yahoo_symbol}")

            # Get the data
            hist_data = yf.download(
                yahoo_symbol,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d",
                progress=False,
                auto_adjust=True,
            )

            if hist_data.empty:
                logging.warning(
                    f"No data returned from Yahoo Finance for {yahoo_symbol}"
                )
                return pd.DataFrame()

            # Convert to expected format
            hist_data = hist_data.reset_index()

            # Handle multi-level columns if present
            if isinstance(hist_data.columns, pd.MultiIndex):
                # Flatten multi-level columns
                hist_data.columns = [
                    " ".join(col).strip().lower() for col in hist_data.columns
                ]
            else:
                # Convert to lowercase
                hist_data.columns = [col.lower() for col in hist_data.columns]

            # Create mapping for Yahoo Finance columns
            column_mapping = {
                "close ^nsei": "close",
                "open ^nsei": "open",
                "high ^nsei": "high",
                "low ^nsei": "low",
                "volume ^nsei": "volume",
            }

            # Rename columns using the mapping
            hist_data = hist_data.rename(columns=column_mapping)

            # Log available columns for debugging
            logging.info(f"Available columns after mapping: {list(hist_data.columns)}")

            # Rename specific columns
            hist_data.rename(
                columns={"date": "datetime", "adj close": "close"}, inplace=True
            )

            # Create any missing columns
            required_cols = ["datetime", "open", "high", "low", "close", "volume"]
            for col in required_cols:
                if col not in hist_data.columns:
                    if col == "volume":
                        hist_data[col] = 0
                    else:
                        logging.warning(
                            f"Missing required column {col} in Yahoo Finance data. Available columns: {list(hist_data.columns)}"
                        )
                        return pd.DataFrame()

            logging.info(
                f"Successfully retrieved {len(hist_data)} rows for {yahoo_symbol}"
            )
            return hist_data[required_cols]

        except Exception as e:
            logging.error(
                f"Error fetching data from Yahoo Finance for {stock_code}: {str(e)}"
            )
            return pd.DataFrame()

    def calculate_indicators(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Calculate technical indicators"""
        try:
            if "close" not in df.columns:
                logging.error("Missing 'close' column for indicators")
                return None

            # RSI
            RSI_PERIOD = 14
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            avg_gain = gain.rolling(window=RSI_PERIOD).mean()
            avg_loss = loss.rolling(window=RSI_PERIOD).mean()
            rs = avg_gain / avg_loss
            df["rsi"] = 100 - (100 / (1 + rs))

            # Moving averages
            df["sma_20"] = df["close"].rolling(window=20).mean()
            df["sma_50"] = df["close"].rolling(window=50).mean()
            df["sma_200"] = df["close"].rolling(window=200).mean()

            # ATR
            high_low = df["high"] - df["low"]
            high_close = np.abs(df["high"] - df["close"].shift())
            low_close = np.abs(df["low"] - df["close"].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = np.max(ranges, axis=1)
            df["atr"] = true_range.rolling(14).mean()

            # MACD
            ema_12 = df["close"].ewm(span=12, adjust=False).mean()
            ema_26 = df["close"].ewm(span=26, adjust=False).mean()
            df["macd"] = ema_12 - ema_26
            df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
            df["macd_hist"] = df["macd"] - df["macd_signal"]

            # Bollinger Bands
            df["bollinger_mid"] = df["close"].rolling(window=20).mean()
            df["bollinger_std"] = df["close"].rolling(window=20).std()
            df["bollinger_upper"] = df["bollinger_mid"] + (df["bollinger_std"] * 2)
            df["bollinger_lower"] = df["bollinger_mid"] - (df["bollinger_std"] * 2)

            # Stochastic Oscillator
            window = 14
            min_low = df["low"].rolling(window=window).min()
            max_high = df["high"].rolling(window=window).max()
            df["stoch_k"] = 100 * ((df["close"] - min_low) / (max_high - min_low))
            df["stoch_d"] = df["stoch_k"].rolling(window=3).mean()

            # ADX (Average Directional Index) for trend strength
            plus_dm = df["high"].diff()
            minus_dm = df["low"].diff().multiply(-1)
            plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
            minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

            tr = true_range  # Already calculated for ATR
            plus_di = 100 * (
                plus_dm.rolling(window=14).mean() / tr.rolling(window=14).mean()
            )
            minus_di = 100 * (
                minus_dm.rolling(window=14).mean() / tr.rolling(window=14).mean()
            )
            dx = 100 * np.abs((plus_di - minus_di) / (plus_di + minus_di))
            df["adx"] = dx.rolling(window=14).mean()

            # Rate of Change (ROC)
            df["roc"] = df["close"].pct_change(periods=10) * 100

            # On-Balance Volume (OBV)
            df["obv"] = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()

            return df

        except Exception as e:
            logging.error(f"Error calculating indicators: {e}")
            return None

    def place_order(
        self,
        stock_code: str,
        exchange_code: str,
        action: str,
        quantity: int,
        order_type: str = "market",
    ) -> Optional[str]:
        """Place order (with paper trading support)"""

        breeze_symbol = stock_mapper.get_breeze_symbol(stock_code)

        if self.PAPER_TRADING:
            logging.info(f"PAPER TRADING: {action} {quantity} {stock_code} at market")
            return "PAPER_ORDER_123"  # Fake order ID

        try:
            response = self.breeze.place_order(
                stock_code=breeze_symbol,
                exchange_code=exchange_code,
                product="cash",
                action=action,
                quantity=str(quantity),
                order_type=order_type,
                validity="day",
            )

            if response and "Success" in response:
                order_id = response["Success"]["order_id"]
                logging.info(
                    f"{action.upper()} order placed for {stock_code}: {order_id}"
                )
                return order_id
            else:
                logging.error(f"Order failed for {stock_code}: {response}")
                return None

        except Exception as e:
            logging.error(f"Error placing order for {stock_code}: {e}")
            return None

    def get_order_status(self, order_id: str, exchange_code: str) -> Optional[Dict]:
        """Get order status - Missing method added"""
        if self.PAPER_TRADING:
            # Return fake executed status for paper trading
            return {
                "Success": [
                    {
                        "order_id": order_id,
                        "status": "Executed",
                        "quantity": "10",
                        "pending_quantity": "0",
                        "average_price": "100.0",
                    }
                ]
            }

        try:
            order_status = self.breeze.get_order_detail(
                order_id=order_id, exchange_code=exchange_code or "NSE"
            )
            return order_status

        except Exception as e:
            logging.error(f"Error getting order status for {order_id}: {e}")
            return None

    def cancel_order(self, order_id: str) -> Optional[Dict]:
        """Cancel order - Missing method added"""
        if self.PAPER_TRADING:
            logging.info(f"PAPER TRADING: Would cancel order {order_id}")
            return {"Success": "Order cancelled"}

        try:
            cancel_response = self.breeze.cancel_order(order_id=order_id)
            logging.info(f"Cancel order response for {order_id}: {cancel_response}")
            return cancel_response

        except Exception as e:
            logging.error(f"Error cancelling order {order_id}: {e}")
            return None

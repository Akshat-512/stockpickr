#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Trading System for ICICI Direct Breeze API
"""

import datetime
import time
import logging
import json
import os
import configparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
import numpy as np
from breeze_connect import BreezeConnect
import pytz
import yfinance as yf
from Technical import NSE
from stock_utils import stock_mapper
from typing import Any, Dict, Optional, Union


# tech = NSE() // Use when you want fundamental data
# Configure logging
logging.basicConfig(
    level=logging.WARNING,  # Changed from INFO to DEBUG
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("trader.log"), logging.StreamHandler()],
    force=True,
)

# Load configuration
config = configparser.ConfigParser()
config.read("config.ini")

# API credentials
API_KEY = config.get("APICredentials", "api_key", fallback="")
API_SECRET = config.get("APICredentials", "api_secret", fallback="")
SESSION_TOKEN = config.get("APICredentials", "session_token", fallback="")

# Strategy parameters
INITIAL_CAPITAL = config.getfloat("Basic", "capital", fallback=5000)
RSI_PERIOD = config.getint("Strategy", "rsi_period", fallback=14)
RSI_OVERBOUGHT = config.getfloat("Strategy", "rsi_overbought", fallback=70)
RSI_OVERSOLD = config.getfloat("Strategy", "rsi_oversold", fallback=30)
RISK_PER_TRADE_PERCENT = config.getfloat("Strategy", "risk_percent", fallback=2.0)
MAX_POSITIONS = config.getint("Strategy", "max_positions", fallback=2)

# Paper trading mode - when True, no actual orders will be placed
PAPER_TRADING_MODE = config.getboolean("Strategy", "paper_trading_mode", fallback=True)

# Email settings
EMAIL_ENABLED = config.getboolean("Notifications", "enable_email", fallback=True)
EMAIL_SERVER = config.get("Notifications", "smtp_server", fallback="smtp.gmail.com")
EMAIL_PORT = config.getint("Notifications", "smtp_port", fallback=587)
EMAIL_USERNAME = config.get("Notifications", "smtp_username", fallback="")
EMAIL_PASSWORD = config.get("Notifications", "smtp_password", fallback="")
EMAIL_RECIPIENT = config.get("Notifications", "notification_email", fallback="")

# Market scanning parameters
MIN_PRICE = config.getfloat("Screening", "min_price", fallback=100)
MAX_PRICE = config.getfloat(
    "Screening", "max_price", fallback=15000
)  # Increased from 5000 to 15000
MIN_VOLUME = config.getint("Screening", "min_volume", fallback=100000)
INDEX_FOR_STOCKS = config.get("Screening", "index_name", fallback="NIFTY 50")


MAX_WAIT_TIME_ORDER = 60
INDEX_DIR = "index_csv"

# Global variables for tracking
breeze = None  # API connection
positions = {}  # Current positions
today_trades = []  # Trades executed today


def initialize_api():
    """Connect to the ICICI Direct Breeze API"""
    global breeze

    try:
        logging.info("Initializing API connection")

        # Create instance and generate session
        breeze = BreezeConnect(api_key=API_KEY)
        logging.info("Using provided session token")
        breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)

        # Check connection by making an API call
        try:
            user_profile = breeze.get_customer_details(api_session=SESSION_TOKEN)

            if user_profile and "Success" in user_profile:
                logging.info(
                    f"API connection successful. User: {user_profile['Success'].get('name', 'Unknown')}"
                )
                return True
            else:
                logging.error(f"API session validation failed: {user_profile}")
                return False

        except Exception as e:
            logging.error(f"Error validating session: {e}")
            return False

    except Exception as e:
        logging.error(f"Failed to initialize API: {e}")
        return False


def send_email(subject, message_body):
    """Send email notification

    Args:
        subject (str): Email subject
        message_body (str): Email body

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    if (
        not EMAIL_ENABLED
        or not EMAIL_USERNAME
        or not EMAIL_PASSWORD
        or not EMAIL_RECIPIENT
    ):
        logging.info("Email notifications not configured or disabled")
        return False

    try:
        # Create message
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USERNAME
        msg["To"] = EMAIL_RECIPIENT
        msg["Subject"] = subject

        # Attach message body
        msg.attach(MIMEText(message_body, "plain"))

        # Connect to server and send
        server = smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()

        logging.info(f"Email notification sent: {subject}")
        return True

    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        return False


def get_historical_data_index(stock_code, interval="1day", days=200):
    """Get historical data for an index using Yahoo Finance.
    Args:
        stock_code (str): Stock or index symbol (e.g., "NIFTY").
        interval (str): Time interval (e.g., "1day", "1hour").
        days (int): Number of days of historical data to fetch.

    Returns:
        pandas.DataFrame: Historical data with columns like datetime, open, high, low, close, volume.
                          Returns an empty DataFrame on error.
    """
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
            logging.warning(f"No data returned from Yahoo Finance for {yahoo_symbol}")
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

        logging.info(f"Successfully retrieved {len(hist_data)} rows for {yahoo_symbol}")
        return hist_data[required_cols]

    except Exception as e:
        logging.error(
            f"Error fetching data from Yahoo Finance for {stock_code}: {str(e)}"
        )
        return pd.DataFrame()


# Minimum number of data points required based on interval
MIN_DATA_POINTS = {
    "1day": 20,  # For daily data, we need at least 20 days
    "1hour": 200,  # For hourly data, we need more points
    "5min": 500,  # For 5-minute data, we need even more points
}


def get_historical_data(stock_code, exchange_code, interval="1day", days=300):
    """Get historical data for a stock or index.

    Args:
        stock_code (str): Stock code/symbol (e.g., "NIFTY" for NIFTY 50).
        exchange_code (str): Exchange code (e.g., "NSE").
        interval (str): Candle interval (e.g., "1day").
        days (int): Number of days of data to fetch.

    Returns:
        pandas.DataFrame: Historical price data or empty DataFrame on error.
    """
    try:
        # Track the final outcome
        final_outcome = "Failed"

        # Convert to Breeze-compatible symbol for non-index symbols
        if not stock_code.startswith(("NIFTY", "SENSEX", "BANKNIFTY")):
            breeze_symbol = stock_mapper.get_breeze_symbol(stock_code)

            # Log the conversion for debugging
            if breeze_symbol != stock_code:
                logging.debug(
                    f"Converted NSE symbol {stock_code} to Breeze symbol {breeze_symbol}"
                )
        else:
            breeze_symbol = stock_code

        # Calculate date range
        to_date = datetime.datetime.now()
        from_date = to_date - datetime.timedelta(days=days)

        # Format dates in ISO8601 with UTC timezone
        from_date_str = from_date.strftime("%Y-%m-%dT00:00:00.000Z")
        to_date_str = to_date.strftime("%Y-%m-%dT23:59:59.000Z")

        logging.debug(
            f"Fetching historical data for {breeze_symbol} ({exchange_code}), "
            f"interval: {interval}, from: {from_date_str}, to: {to_date_str}"
        )

        # Fetch historical data
        hist_data = breeze.get_historical_data(
            interval=interval,
            from_date=from_date_str,
            to_date=to_date_str,
            stock_code=breeze_symbol,  # Use the mapped symbol
            exchange_code=exchange_code,
            product_type="cash",  # Use "cash" for indices like NIFTY
        )

        # Check API response
        logging.debug(f"Raw hist_data response: {json.dumps(hist_data, indent=2)}")

        if hist_data and hist_data.get("Success"):
            # Check if we have data points
            if len(hist_data["Success"]):
                # Convert status code to string for logging
                status = hist_data.get("Status", "Unknown")
                logging.info(f"Successfully received historical data for {stock_code}")
                logging.debug(f"Status: {status}")
                logging.debug(
                    f"Number of data points: {len(hist_data.get('Success', []))}"
                )

                df = pd.DataFrame(hist_data["Success"])
                logging.debug(f"DataFrame columns: {df.columns.tolist()}")

                # Convert columns to appropriate types
                numeric_columns = ["open", "high", "low", "close", "volume"]
                for col in numeric_columns:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                if "datetime" in df.columns:
                    df["datetime"] = pd.to_datetime(df["datetime"])

                df = df.sort_values("datetime")
                logging.info(
                    f"Retrieved {len(df)} historical data points for {stock_code}"
                )
                logging.debug(
                    f"First data point datetime: {df['datetime'].iloc[0] if len(df) > 0 else 'None'}"
                )
                logging.debug(
                    f"Last data point datetime: {df['datetime'].iloc[-1] if len(df) > 0 else 'None'}"
                )
                return df
            else:
                logging.warning(f"No data points returned for {stock_code}")
                return pd.DataFrame()
        else:
            error_msg = hist_data.get("Error", "Unknown error") if hist_data else "None"
            logging.error(f"Failed to get historical data for {stock_code}")
            if isinstance(error_msg, dict):
                error_msg = json.dumps(error_msg, indent=2)
            logging.error(f"Error message: {error_msg}")
            logging.error(
                f"Full response: {json.dumps(hist_data, indent=2) if hist_data else 'None'}"
            )
            return pd.DataFrame()

    except Exception as e:
        logging.error(f"Error fetching historical data for {stock_code}: {str(e)}")
        logging.exception("Stack trace:")
        return pd.DataFrame()


def _find_price_in_dict(data: Dict[str, Any]) -> Optional[float]:
    """Recursively search for a price value in a nested dictionary.

    Args:
        data: Dictionary to search in

    Returns:
        float or None: First numeric price found, or None if not found
    """
    price_fields = [
        "ltp",
        "last",
        "close",
        "price",
        "last_price",
        "lastPrice",
        "lt",
        "lasttradeprice",
    ]

    # Check if current level has any price fields
    for field in price_fields:
        if field in data and isinstance(data[field], (int, float)) and data[field] > 0:
            return float(data[field])

    # Recursively check nested dictionaries and lists
    for key, value in data.items():
        if isinstance(value, dict):
            result = _find_price_in_dict(value)
            if result is not None:
                return result
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    result = _find_price_in_dict(item)
                    if result is not None:
                        return result

    return None


def get_current_price(stock_code, exchange_code="NSE", max_retries=3):
    """Get current market price for a stock with retry logic

    Args:
        stock_code (str): Stock code/symbol
        exchange_code (str): Exchange code (NSE/BSE)
        max_retries (int): Maximum number of retry attempts

    Returns:
        float: Current price or None if error after retries
    """
    # Convert to Breeze-compatible symbol
    breeze_symbol = stock_mapper.get_breeze_symbol(stock_code)

    # Log the conversion for debugging
    if breeze_symbol != stock_code:
        logging.debug(
            f"Converted NSE symbol {stock_code} to Breeze symbol {breeze_symbol}"
        )

    retry_count = 0
    base_delay = 1  # Start with 1 second delay

    while retry_count <= max_retries:
        try:
            # Add delay between retries (exponential backoff)
            if retry_count > 0:
                wait_time = base_delay * (2 ** (retry_count - 1))
                logging.debug(
                    f"Retry {retry_count}/{max_retries} for {breeze_symbol} - Waiting {wait_time} seconds..."
                )
                time.sleep(wait_time)

            # Get latest quote for equity using the Breeze symbol
            quote = breeze.get_quotes(
                stock_code=breeze_symbol,  # Use the mapped symbol
                exchange_code=exchange_code,
                expiry_date="",
                product_type="cash",
                right="",
                strike_price="",
            )

            # Debug: Log the complete response
            logging.debug(
                f"API Response for {stock_code} (attempt {retry_count + 1}): {quote}"
            )
            if isinstance(quote, dict):
                logging.debug(f"Response keys: {list(quote.keys())}")
                if (
                    "Success" in quote
                    and isinstance(quote["Success"], list)
                    and len(quote["Success"]) > 0
                ):
                    logging.debug(
                        f"First Success item keys: {list(quote['Success'][0].keys()) if isinstance(quote['Success'][0], dict) else 'Not a dict'}"
                    )

            # Check if we got a valid response
            if not quote:
                logging.warning(f"Empty response for {stock_code}")
                retry_count += 1
                continue

            # Handle different response formats
            price = None

            # Debug: Log the structure of the response
            logging.debug(f"Response type: {type(quote)}")
            if isinstance(quote, dict):
                logging.debug(f"Response keys: {list(quote.keys())}")

            # Format 1: Success key with list of quotes (new format with ltp)
            if (
                isinstance(quote, dict)
                and "Success" in quote
                and isinstance(quote["Success"], list)
            ):
                logging.debug("Processing Format 1: Success key with list of quotes")
                for item in quote["Success"]:
                    if not isinstance(item, dict):
                        continue
                    # Try to get the price from various possible fields
                    price = item.get("ltp")  # Last Traded Price
                    if price is None or price == 0:
                        price = item.get("last")
                    if price is None or price == 0:
                        price = item.get("close")
                    if price is not None and price != 0:
                        logging.debug(f"Found price {price} in item: {item}")
                        break
                else:
                    logging.warning(
                        f"No valid price found in Success items for {stock_code}"
                    )
                    price = None

            # Format 2: stat and values keys (legacy format)
            elif (
                isinstance(quote, dict)
                and quote.get("stat") == "Ok"
                and "values" in quote
            ):
                logging.debug("Processing Format 2: stat and values keys")
                values = quote["values"]
                if values and isinstance(values, list) and len(values) > 0:
                    logging.debug(f"First value item: {values[0]}")
                    price = values[0].get("last")
                    logging.debug(f"Extracted price from values: {price}")

            # Format 3: Direct price in the response (legacy format)
            elif isinstance(quote, dict) and "last" in quote:
                logging.debug("Processing Format 3: Direct price in response")
                price = quote["last"]
                logging.debug(f"Extracted direct price: {price}")

            # If we still don't have a price, try to find any numeric price in the response
            if price is None and isinstance(quote, dict):
                logging.debug("Searching for any price field in the response")
                price = _find_price_in_dict(quote)

            # If still no price, try to get the first non-zero ltp from any exchange
            if (
                (price is None or price == 0)
                and isinstance(quote, dict)
                and "Success" in quote
                and isinstance(quote["Success"], list)
            ):
                for item in quote["Success"]:
                    if not isinstance(item, dict):
                        continue
                    ltp = item.get("ltp")
                    if ltp and ltp > 0:
                        price = ltp
                        logging.debug(
                            f"Found non-zero ltp in alternative exchange: {price}"
                        )
                        break

            if price is not None:
                try:
                    float_price = float(price)
                    logging.debug(
                        f"Successfully converted price to float: {float_price}"
                    )
                    return float_price
                except (ValueError, TypeError) as e:
                    logging.warning(
                        f"Invalid price format for {stock_code}: {price} (type: {type(price)})"
                    )
            else:
                logging.warning(f"No valid price found in response for {stock_code}")
                logging.debug(f"Full response that couldn't be parsed: {quote}")

            retry_count += 1

        except Exception as e:
            error_msg = str(e)
            if any(
                err in error_msg.lower()
                for err in ["error_exception", "nonetype", "503", "timeout"]
            ):
                logging.debug(
                    f"Temporary error for {stock_code} (attempt {retry_count + 1}/{max_retries}): {error_msg}"
                )
                retry_count += 1
            else:
                logging.error(
                    f"Unexpected error getting price for {stock_code}: {error_msg}"
                )
                logging.exception("Error details:")
                return None

    logging.error(f"Failed to get price for {stock_code} after {max_retries} attempts")
    return None


def calculate_indicators(df):
    """Calculate technical indicators

    Args:
        df (pandas.DataFrame): Historical price data

    Returns:
        pandas.DataFrame: DataFrame with indicators added
    """
    try:
        # Check if required columns exist
        if "close" not in df.columns:
            logging.error("Price data is missing 'close' column")
            return None

        # Calculate RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(window=RSI_PERIOD).mean()
        avg_loss = loss.rolling(window=RSI_PERIOD).mean()

        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # Calculate 20-day simple moving average
        df["sma_20"] = df["close"].rolling(window=20).mean()

        # Calculate 50-day simple moving average
        df["sma_50"] = df["close"].rolling(window=50).mean()

        # Calculate 200-day simple moving average (for trend identification)
        df["sma_200"] = df["close"].rolling(window=200).mean()

        # Calculate Average True Range (ATR)
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())

        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df["atr"] = true_range.rolling(14).mean()

        # Calculate MACD (Moving Average Convergence Divergence)
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # Calculate Bollinger Bands
        df["bollinger_mid"] = df["close"].rolling(window=20).mean()
        df["bollinger_std"] = df["close"].rolling(window=20).std()
        df["bollinger_upper"] = df["bollinger_mid"] + (df["bollinger_std"] * 2)
        df["bollinger_lower"] = df["bollinger_mid"] - (df["bollinger_std"] * 2)

        # Calculate Stochastic Oscillator
        window = 14
        min_low = df["low"].rolling(window=window).min()
        max_high = df["high"].rolling(window=window).max()
        df["stoch_k"] = 100 * ((df["close"] - min_low) / (max_high - min_low))
        df["stoch_d"] = df["stoch_k"].rolling(window=3).mean()

        # Calculate ADX (Average Directional Index) for trend strength
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

        # Calculate Rate of Change (ROC)
        df["roc"] = df["close"].pct_change(periods=10) * 100

        # Calculate On-Balance Volume (OBV)
        df["obv"] = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()

        return df

    except Exception as e:
        logging.error(f"Error calculating indicators: {e}")
        return None


def analyze_market_condition(index_data):
    """
    Analyze overall market condition based on index data.
    Completely standalone implementation without any calls to other functions.

    Args:
        index_data (pandas.DataFrame): Historical data for market index

    Returns:
        dict: Market condition analysis
    """
    # Check if we have enough data for meaningful analysis
    if index_data is None or len(index_data) < 30:
        logging.warning(
            f"Insufficient index data for market analysis: {0 if index_data is None else len(index_data)} points"
        )
        return {
            "trend": "unknown",
            "volatility": "unknown",
            "strength": "unknown",
            "above_200_sma": False,
        }

    # Calculate indicators directly
    # Calculate SMAs if not already present
    if "sma_20" not in index_data.columns:
        index_data["sma_20"] = index_data["close"].rolling(window=20).mean()

    if "sma_50" not in index_data.columns:
        index_data["sma_50"] = index_data["close"].rolling(window=50).mean()

    if "sma_200" not in index_data.columns:
        index_data["sma_200"] = index_data["close"].rolling(window=200).mean()

    # Calculate ATR if not already present
    if "atr" not in index_data.columns:
        high_low = index_data["high"] - index_data["low"]
        high_close = np.abs(index_data["high"] - index_data["close"].shift())
        low_close = np.abs(index_data["low"] - index_data["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        index_data["atr"] = true_range.rolling(14).mean()

    # Get the latest values
    latest = index_data.iloc[-1]

    # Determine market trend
    if len(index_data) >= 200 and not pd.isna(latest.get("sma_200", None)):
        if latest["close"] > latest["sma_200"] and latest["sma_50"] > latest["sma_200"]:
            trend = "bullish"
        elif (
            latest["close"] < latest["sma_200"] and latest["sma_50"] < latest["sma_200"]
        ):
            trend = "bearish"
        else:
            trend = "neutral"
    elif len(index_data) >= 50 and not pd.isna(latest.get("sma_50", None)):
        if latest["close"] > latest["sma_50"]:
            trend = "bullish"
        else:
            trend = "bearish"
    else:
        # Very simplified if limited data
        recent_prices = index_data["close"].tail(5)
        if latest["close"] > recent_prices.mean():
            trend = "bullish"
        else:
            trend = "bearish"

    # Determine market volatility
    if "atr" in index_data.columns and not index_data["atr"].tail(20).isna().any():
        recent_atr = index_data["atr"].iloc[-5:].mean()
        long_atr = index_data["atr"].iloc[-20:].mean()
        volatility_ratio = recent_atr / long_atr if long_atr > 0 else 1

        if volatility_ratio > 1.3:
            volatility = "high"
        elif volatility_ratio < 0.7:
            volatility = "low"
        else:
            volatility = "normal"
    else:
        # Use price volatility as a simpler alternative
        recent_volatility = index_data["close"].pct_change().abs().tail(5).mean() * 100
        if recent_volatility > 1.5:  # 1.5% average daily change
            volatility = "high"
        elif recent_volatility < 0.5:  # 0.5% average daily change
            volatility = "low"
        else:
            volatility = "normal"

    # Determine trend strength (simple method)
    last_5_changes = index_data["close"].diff().tail(5)
    if trend == "bullish":
        consec_ups = sum(1 for x in last_5_changes if x > 0)
        strength = (
            "strong" if consec_ups >= 4 else "moderate" if consec_ups >= 2 else "weak"
        )
    else:
        consec_downs = sum(1 for x in last_5_changes if x < 0)
        strength = (
            "strong"
            if consec_downs >= 4
            else "moderate" if consec_downs >= 2 else "weak"
        )

    # Check if market is above 200-day SMA
    above_200_sma = False
    close_vs_sma200 = 0

    if "sma_200" in index_data.columns and not pd.isna(latest.get("sma_200", None)):
        above_200_sma = latest["close"] > latest["sma_200"]
        close_vs_sma200 = ((latest["close"] / latest["sma_200"]) - 1) * 100

    # Overall mid-term trend assessment
    if above_200_sma and trend == "bullish":
        mid_term_trend = "strongly bullish"
    elif above_200_sma:
        mid_term_trend = "bullish"
    elif trend == "bearish":
        mid_term_trend = "strongly bearish"
    else:
        mid_term_trend = "cautious"

    # Prepare the return dictionary
    result = {
        "trend": trend,
        "volatility": volatility,
        "strength": strength,
        "above_200_sma": above_200_sma,
        "close_vs_sma200": close_vs_sma200,
        "mid_term_trend": mid_term_trend,
    }

    # Add RSI if available
    if "rsi" in latest and not pd.isna(latest["rsi"]):
        result["rsi"] = latest["rsi"]

    # Add ADX if available
    if "adx" in latest and not pd.isna(latest["adx"]):
        result["adx"] = latest["adx"]

    return result


def check_buy_signal(df, market_condition, min_points=30):
    """Enhanced version of your existing buy signal"""
    if df is None or df.empty:
        return False, "No data available"

    available_points = len(df)
    if available_points < min_points:
        return (
            False,
            f"Insufficient data ({available_points} points available, need {min_points})",
        )

    try:
        latest = df.iloc[-1]
        previous = df.iloc[-2]

        signal_reasons = []
        score = 0

        # Check for multiple timeframe momentum
        price_3d = (
            ((latest["close"] / df["close"].iloc[-4]) - 1) * 100 if len(df) >= 4 else 0
        )
        price_5d = (
            ((latest["close"] / df["close"].iloc[-6]) - 1) * 100 if len(df) >= 6 else 0
        )

        # Strong recent momentum (key for 1-month trades)
        if price_3d >= 2:  # 2% in 3 days
            signal_reasons.append(f"Strong 3-day momentum: {price_3d:.1f}%")
            score += 2
        elif price_5d >= 3:  # 3% in 5 days
            signal_reasons.append(f"Good 5-day momentum: {price_5d:.1f}%")
            score += 1

        # Volume surge check (critical for quick moves)
        avg_volume_20 = df["volume"].tail(20).mean()
        recent_volume = df["volume"].tail(3).mean()
        if recent_volume > (avg_volume_20 * 1.5):  # 50% above average
            signal_reasons.append("Volume surge detected")
            score += 2

        # Keep your existing RSI, MACD, SMA logic here...
        # RSI oversold signal
        if previous["rsi"] < RSI_OVERSOLD and latest["rsi"] > RSI_OVERSOLD:
            signal_reasons.append(f"RSI crossed above oversold ({latest['rsi']:.1f})")
            score += 2

        # Price above key moving averages
        if latest["close"] > latest["sma_20"]:
            signal_reasons.append("Price above 20-day SMA")
            score += 1

        if latest["close"] > latest["sma_50"]:
            signal_reasons.append("Price above 50-day SMA")
            score += 1

        # MACD signals
        macd_cross = (
            previous["macd"] < previous["macd_signal"]
            and latest["macd"] > latest["macd_signal"]
        )
        hist_increase = (
            latest["macd_hist"] > 0 and latest["macd_hist"] > previous["macd_hist"]
        )

        if macd_cross:
            signal_reasons.append("MACD crossed above signal line")
            score += 2
        if hist_increase:
            signal_reasons.append("MACD histogram increasing")
            score += 1

        # NEW: Minimum score adjustment for active trading
        min_score = 4  # Lowered for more opportunities
        if market_condition.get("trend", "neutral") == "bullish":
            min_score = 3
        elif market_condition.get("trend", "neutral") == "bearish":
            min_score = 5

        if score >= min_score:
            return True, f"Buy signals detected: {', '.join(signal_reasons)}"
        else:
            return (
                False,
                f"Insufficient signal strength (score: {score}, min: {min_score})",
            )

    except Exception as e:
        logging.error(f"Error checking buy signal: {str(e)}")
        return False, f"Error: {str(e)}"


def store_entry_context(stock_code, signal_reason):
    """Store why we entered this position"""
    if stock_code in positions:
        positions[stock_code]["entry_reason"] = signal_reason
        positions[stock_code]["entry_date"] = datetime.datetime.now().isoformat()

        # Set expected timeframe based on entry reason
        if (
            "momentum" in signal_reason.lower()
            or "volume surge" in signal_reason.lower()
        ):
            positions[stock_code]["expected_duration"] = "1-3_weeks"
        else:
            positions[stock_code]["expected_duration"] = "2-4_weeks"


def update_trailing_stops():
    """Update trailing stops for all positions based on current prices and ATR"""
    updated_count = 0

    for stock_code, position in positions.items():
        try:
            # Get current data
            exchange_code = position["exchange"]
            entry_price = position["entry_price"]
            current_stop = position.get("stop_loss", 0)

            # Get current price
            current_price = get_current_price(stock_code, exchange_code)
            if current_price is None:
                continue

            # Get historical data for ATR
            hist_data = get_historical_data(stock_code, exchange_code)
            if hist_data is None or hist_data.empty:
                continue

            # Calculate indicators
            with_indicators = calculate_indicators(hist_data)
            if with_indicators is None:
                continue

            # Get latest ATR
            latest_atr = with_indicators["atr"].iloc[-1]

            # Calculate profit percentage
            profit_percent = ((current_price / entry_price) - 1) * 100
            logging.warning(
                f"Profit percentage for {stock_code}: {profit_percent:.2f}%"
            )

            # Update stop loss based on profit level
            new_stop_loss = current_stop

            if profit_percent >= 8:
                # Tighter trail at higher profit
                trail_distance = 1.0 * latest_atr
                potential_stop = current_price - trail_distance
                new_stop_loss = max(current_stop, potential_stop)
            elif profit_percent >= 4:
                # Standard trail
                trail_distance = 1.5 * latest_atr
                potential_stop = current_price - trail_distance
                new_stop_loss = max(current_stop, potential_stop)

            # Update if we have a higher stop loss
            if new_stop_loss > current_stop:
                positions[stock_code]["stop_loss"] = new_stop_loss
                logging.warning(
                    f"Updated trailing stop for {stock_code}: {current_stop:.2f} -> {new_stop_loss:.2f}"
                )
                updated_count += 1

        except Exception as e:
            logging.error(f"Error updating trailing stop for {stock_code}: {e}")

    # Save positions if any stops were updated
    if updated_count > 0:
        save_positions()

    return updated_count


def check_sell_signal(df, entry_price, days_held=0, market_condition=None):
    """
    CONSOLIDATED sell signal function with ALL exit logic
    - Technical analysis
    - Time-based rules
    - Market condition overrides

    Args:
        df (pandas.DataFrame): Historical data with indicators
        entry_price (float): Entry price for position
        days_held (int): Days position has been held
        market_condition (dict): Current market condition

    Returns:
        tuple: (bool, str) - Signal and reason
    """
    if df is None or df.empty:
        return False, "Insufficient data"

    try:
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        current_price = latest["close"]
        profit_percent = ((current_price / entry_price) - 1) * 100

        # ============================================
        # 1. TIME-BASED EXIT RULES (Week by Week)
        # ============================================

        # WEEK 1 (Days 1-7): Quick profit taking and early loss control
        if days_held <= 7:
            # Take quick profits
            if profit_percent >= 8:
                return (
                    True,
                    f"Week 1 quick profit: {profit_percent:.1f}% in {days_held} days",
                )

            # Early loss control
            if profit_percent <= -3 and days_held >= 3:
                return (
                    True,
                    f"Week 1 loss control: {profit_percent:.1f}% after {days_held} days",
                )

            # End of week 1 checkpoint
            if days_held == 7 and profit_percent < 1:
                return True, f"Week 1 checkpoint failed: {profit_percent:.1f}%"

        # WEEK 2 (Days 8-14): Standard performance expectations
        elif days_held <= 14:
            # Good profit target
            if profit_percent >= 10:
                return (
                    True,
                    f"Week 2 target achieved: {profit_percent:.1f}% in {days_held} days",
                )

            # Underperformance check
            if profit_percent < 2 and days_held >= 10:
                return (
                    True,
                    f"Week 2 underperformance: {profit_percent:.1f}% after {days_held} days",
                )

            # Week 2 checkpoint
            if days_held == 14 and profit_percent < 3:
                return True, f"Week 2 checkpoint failed: {profit_percent:.1f}%"

        # WEEK 3 (Days 15-21): Higher expectations
        elif days_held <= 21:
            # Higher profit target
            if profit_percent >= 12:
                return (
                    True,
                    f"Week 3 strong performance: {profit_percent:.1f}% in {days_held} days",
                )

            # Week 3 underperformance
            if profit_percent < 4 and days_held >= 18:
                return (
                    True,
                    f"Week 3 underperformance: {profit_percent:.1f}% after {days_held} days",
                )

            # Week 3 checkpoint
            if days_held == 21 and profit_percent < 5:
                return True, f"Week 3 checkpoint failed: {profit_percent:.1f}%"

        # WEEK 4+ (Days 22-30): Final stretch
        elif days_held <= 30:
            # Take decent profits in final week
            if profit_percent >= 8:
                return (
                    True,
                    f"Week 4 profit taking: {profit_percent:.1f}% after {days_held} days",
                )

            # Limit losses in final week
            if profit_percent <= -2:
                return (
                    True,
                    f"Week 4 loss limitation: {profit_percent:.1f}% after {days_held} days",
                )

            # Approaching maximum
            if days_held >= 28:
                return (
                    True,
                    f"Approaching max holding: {profit_percent:.1f}% after {days_held} days",
                )

        # MAXIMUM HOLDING PERIOD (30+ days): Forced exit
        else:  # days_held > 30
            if profit_percent > 0:
                return (
                    True,
                    f"Max holding period with profit: {profit_percent:.1f}% after {days_held} days",
                )
            else:
                return (
                    True,
                    f"Max holding period reached: {profit_percent:.1f}% after {days_held} days",
                )

        # ============================================
        # 2. TECHNICAL ANALYSIS EXIT RULES
        # ============================================

        # Only check technical rules if time-based rules didn't trigger

        # A) PROFIT TARGETS (if time rules didn't catch them)
        if profit_percent >= 15:  # Very high profit - always take
            return True, f"Excellent profit target: {profit_percent:.2f}%"

        # B) STOP LOSS (Dynamic based on time held)
        if days_held <= 7:
            stop_threshold = -4.0  # Wider stop early
        elif days_held <= 14:
            stop_threshold = -3.5  # Medium stop
        else:
            stop_threshold = -3.0  # Tighter stop later

        if profit_percent <= stop_threshold:
            return True, f"Technical stop loss: {profit_percent:.2f}%"

        # C) MOMENTUM BREAKDOWN
        momentum_broken = (
            previous["macd"] > previous["macd_signal"]
            and latest["macd"] < latest["macd_signal"]
            and latest["macd_hist"] < -0.2  # Significant negative
            and latest["rsi"] < 40  # RSI weak too
        )

        if momentum_broken and profit_percent < 6:
            return True, f"Technical momentum breakdown after {days_held} days"

        # D) VOLUME MOMENTUM FADING
        if days_held >= 5:  # Only check after 5 days
            avg_volume_20 = df["volume"].tail(20).mean()
            recent_volume = df["volume"].tail(3).mean()
            volume_dried = recent_volume < (avg_volume_20 * 0.7)

            if volume_dried and profit_percent < 5:
                return True, f"Volume momentum fading after {days_held} days"

        # E) RSI EXTREME OVERBOUGHT (with profit)
        if latest["rsi"] > 78 and profit_percent >= 8:
            return True, f"RSI extreme overbought with profit: {profit_percent:.2f}%"

        # F) PRICE BELOW KEY SUPPORT
        if days_held >= 7:  # Only after week 1
            # Check if price broke below 20-day SMA significantly
            if (
                previous["close"] > previous["sma_20"]
                and latest["close"] < latest["sma_20"] * 0.97
            ):  # 3% below SMA
                return True, f"Broke key support after {days_held} days"

        # ============================================
        # 3. MARKET CONDITION OVERRIDES
        # ============================================

        if market_condition:
            market_trend = market_condition.get("trend", "neutral")
            market_vs_sma200 = market_condition.get("close_vs_sma200", 0)

            # Market crash protection
            if (
                market_trend == "bearish"
                and market_vs_sma200 < -8  # Market down 8%+ from 200-day SMA
                and profit_percent > -3
            ):  # Preserve capital
                return (
                    True,
                    f"Market crash protection: {profit_percent:.1f}% after {days_held} days",
                )

            # Market turning bearish - be more aggressive
            if market_trend == "bearish" and days_held >= 14:
                if profit_percent >= 5:  # Take smaller profits
                    return (
                        True,
                        f"Market bearish - taking {profit_percent:.1f}% profit after {days_held} days",
                    )

        # ============================================
        # 4. NO EXIT SIGNAL
        # ============================================

        return False, f"Hold: {profit_percent:.1f}% profit after {days_held} days"

    except Exception as e:
        logging.error(f"Error in sell signal analysis: {e}")
        return False, f"Error: {str(e)}"


def enter_position(stock_code, exchange_code="NSE"):
    """Enter a new position

    Args:
        stock_code (str): Stock code/symbol
        exchange_code (str): Exchange code (NSE/BSE)

    Returns:
        bool: True if successful, False otherwise
    """
    global positions, today_trades

    # Validate stock symbol
    if stock_code.startswith(("NIFTY", "SENSEX", "BANKNIFTY")):
        logging.warning(f"Cannot enter position in index: {stock_code}")
        return False

    # Convert to Breeze-compatible symbol
    breeze_symbol = stock_mapper.get_breeze_symbol(stock_code)

    # Enhanced position check to prevent duplicate entries
    if stock_code in positions:
        logging.warning(f"Position already exists for {stock_code}, skipping new entry")
        return False

    if PAPER_TRADING_MODE:
        logging.info(
            f"PAPER TRADING MODE: Would enter position in {stock_code} (Breeze: {breeze_symbol})"
        )
        return True

    try:
        # Get current price
        current_price = get_current_price(stock_code, exchange_code)
        if current_price is None:
            return False

        # Get historical data with indicators
        hist_data = get_historical_data(stock_code, exchange_code)
        if hist_data is None:
            return False

        # Calculate indicators
        with_indicators = calculate_indicators(hist_data)
        if with_indicators is None:
            return False

        # Get latest ATR for stop loss calculation
        latest_atr = with_indicators["atr"].iloc[-1]

        # Calculate stop loss price (2 ATR below current price)
        stop_loss_price = current_price - (2 * latest_atr)
        stop_loss_price = round(stop_loss_price, 1)  # Round to 1 decimal place

        # Calculate position size
        quantity, total_cost = calculate_position_size(
            current_price, stop_loss_price, stock_code
        )

        if quantity <= 0:
            logging.warning(f"Calculated quantity is zero or negative for {stock_code}")
            return False

        logging.warning(
            f"Entering position for {stock_code} at {current_price:.2f}, stop loss: {stop_loss_price:.2f}, quantity: {quantity}"
        )

        # Place buy order using Breeze symbol with "cash" product for mid-term holding
        buy_response = breeze.place_order(
            stock_code=breeze_symbol,
            exchange_code=exchange_code,
            product="cash",
            action="buy",
            quantity=str(quantity),
            order_type="market",
            validity="day",
        )

        if not buy_response or "Success" not in buy_response:
            logging.error(f"Failed to place buy order for {stock_code}: {buy_response}")
            return False

        order_id = buy_response["Success"]["order_id"]
        logging.warning(f"Buy order placed for {stock_code}, order ID: {order_id}")

        positions[stock_code] = {
            "exchange": exchange_code,
            "quantity": quantity,
            "entry_price": current_price,
            "entry_time": datetime.datetime.now().isoformat(),
            "stop_loss": stop_loss_price,
            "position_value": current_price * quantity,
        }
        save_positions()

        # Wait for execution
        success, executed_price, filled_qty, order_status_history = (
            wait_for_order_execution(order_id, stock_code, exchange_code, current_price)
        )

        if not success or executed_price == 0:
            # Order failed - clean up
            if stock_code in positions:
                del positions[stock_code]
                save_positions()
            return False

        # Store entry context for better exit decisions
        store_entry_context(stock_code, "Technical entry signal")

        # Send email notification
        email_subject = f"New Position: {stock_code}"
        email_body = f"""
        ENTRY ALERT: {stock_code}

        Details:
        --------
        Entry Price: ₹{executed_price:.2f}
        Quantity: {quantity}
        Position Value: ₹{executed_price * quantity:.2f}
        Stop Loss: ₹{stop_loss_price:.2f}
        Entry Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

        This position represents {(executed_price * quantity / INITIAL_CAPITAL) * 100:.1f}% of your trading capital.
        """
        send_email(email_subject, email_body)

        return True

    except Exception as e:
        logging.error(f"Exception in enter_position for {stock_code}: {e}")
        return False


def wait_for_order_execution(
    order_id,
    stock_code,
    exchange_code,
    current_price,
    max_wait_time=MAX_WAIT_TIME_ORDER,
    wait_interval=2,
):
    """
    Wait for order execution and return execution details.

    Returns:
        tuple: (success: bool, executed_price: float, filled_quantity: int, order_status_history: list)
    """
    start_time = time.time()
    order_status_history = []
    last_order_status = None

    while time.time() - start_time < max_wait_time:
        try:
            # Get order status
            order_status = breeze.get_order_detail(
                order_id=order_id, exchange_code=exchange_code or "NSE"
            )
            last_order_status = order_status  # Keep track of last status

            # Validate response structure
            if not (
                order_status
                and isinstance(order_status.get("Success"), list)
                and order_status["Success"]
            ):
                logging.warning(f"Invalid order response: {order_status}")
                time.sleep(wait_interval)
                continue

            # Extract order info
            order_info = order_status["Success"][0]
            status = order_info.get("status", "Unknown")

            # Track status history for debugging
            order_status_history.append((datetime.datetime.now(), status))

            # Parse quantities and price safely
            try:
                quantity = int(order_info.get("quantity", 0))
                pending_qty = int(order_info.get("pending_quantity", 0))
                filled_qty = quantity - pending_qty
                avg_price = float(order_info.get("average_price", 0))
                executed_price = avg_price if avg_price > 0 else current_price
            except (ValueError, TypeError) as e:
                logging.error(f"Error parsing order data: {e}")
                time.sleep(wait_interval)
                continue

            logging.info(
                f"Order {order_id} for {stock_code}: Status={status}, "
                f"Filled={filled_qty}/{quantity}, Price={executed_price:.2f}"
            )

            # Check order status
            if status == "Executed":
                logging.info(f"Order executed at price: {executed_price}")
                return True, executed_price, filled_qty, order_status_history

            elif status in ["Cancelled", "Rejected", "Expired"]:
                logging.warning(f"Order {order_id} {status} for {stock_code}")
                return False, 0, 0, order_status_history

            # Order still pending - continue waiting
            time.sleep(wait_interval)

        except Exception as e:
            logging.error(f"Error checking order {order_id}: {e}")
            time.sleep(wait_interval)

    # Timeout reached - log history for debugging
    logging.error(f"Order for {stock_code} did not execute within expected time")
    logging.error("Order status history:")
    for timestamp, status in order_status_history:
        logging.error(f"{timestamp}: {status}")

    # Try to cancel pending order - check last known status
    if last_order_status:
        # Check if the last status indicates pending
        # Note: You were checking order_status.get("Status") but based on the code,
        # the status is inside Success[0].get("status"), not at the top level
        try:
            if (
                last_order_status.get("Success")
                and len(last_order_status["Success"]) > 0
            ):
                last_status = last_order_status["Success"][0].get("status")
                if last_status == "Pending":
                    cancel_response = breeze.cancel_order(order_id=order_id)
                    logging.info(
                        f"Attempted to cancel pending order: {cancel_response}"
                    )
        except Exception as e:
            logging.error(f"Error cancelling order: {e}")

    return False, 0, 0, order_status_history


def calculate_position_size(current_price, stop_loss_price, stock_code):
    """Calculate position size based on risk parameters

    Args:
        current_price (float): Current market price
        stop_loss_price (float): Stop loss price
        stock_code (str): Stock code/symbol for logging

    Returns:
        tuple: (quantity, total_cost)
    """
    # Calculate risk amount in rupees
    risk_amount = INITIAL_CAPITAL * (RISK_PER_TRADE_PERCENT / 100)

    # Calculate risk per share
    risk_per_share = current_price - stop_loss_price

    if risk_per_share <= 0:
        logging.warning(
            f"Invalid stop loss for {stock_code} - must be below current price"
        )
        return 0, 0

    # Calculate quantity based on risk
    quantity = int(risk_amount / risk_per_share)

    # Ensure minimum quantity of 1
    quantity = max(1, quantity)

    # Calculate total position cost
    total_cost = quantity * current_price

    # Check if position is too large (> 50% of capital)
    max_position = INITIAL_CAPITAL * 0.5
    if total_cost > max_position:
        # Adjust quantity to fit max position size
        quantity = int(max_position / current_price)
        total_cost = quantity * current_price

    logging.info(
        f"Position size calculation for {stock_code}: Price={current_price}, Stop={stop_loss_price}, Quantity={quantity}, Cost={total_cost}"
    )
    return quantity, total_cost


def exit_position(stock_code, exit_reason="Manual"):
    """Exit an existing position

    Args:
        stock_code (str): Stock code/symbol
        exit_reason (str): Reason for exit (default: "Manual")

    Returns:
        bool: True if successful, False otherwise
    """
    global positions, today_trades

    # Get Breeze symbol for the stock
    breeze_symbol = stock_mapper.get_breeze_symbol(stock_code)

    # Log the conversion for debugging
    if breeze_symbol != stock_code:
        logging.info(f"Using Breeze symbol {breeze_symbol} for {stock_code}")

    if PAPER_TRADING_MODE:
        logging.info(
            f"PAPER TRADING MODE: Would exit position in {stock_code} (Breeze: {breeze_symbol}, Reason: {exit_reason})"
        )
        return True

    try:
        # Check if we have an open position for this stock
        if stock_code not in positions:
            logging.warning(f"No open position found for {stock_code}")
            return False

        position = positions[stock_code]
        exchange_code = position["exchange"]
        quantity = position["quantity"]
        entry_price = position["entry_price"]
        entry_time = position["entry_time"]

        # Get current price
        current_price = get_current_price(stock_code, exchange_code)
        if current_price is None:
            return False

        logging.warning(
            f"Exiting position for {stock_code} at {current_price:.2f}, reason: {exit_reason}"
        )

        # Place sell order using Breeze symbol with "cash" product for mid-term position
        sell_response = breeze.place_order(
            stock_code=breeze_symbol,
            exchange_code=exchange_code,
            product="cash",
            action="sell",
            quantity=str(quantity),
            order_type="market",
            validity="day",
        )

        if not sell_response or "Success" not in sell_response:
            logging.error(
                f"Failed to place sell order for {stock_code}: {sell_response}"
            )
            return False

        order_id = sell_response["Success"]["order_id"]
        logging.warning(f"Sell order placed for {stock_code}, order ID: {order_id}")

        # Wait for order execution (poll order status)
        max_wait_time = MAX_WAIT_TIME_ORDER  # seconds
        wait_interval = 2  # seconds
        waited_time = 0
        executed_price = 0
        order_status = None
        order_status_history = []

        while waited_time < max_wait_time:
            try:
                # Get order status
                order_status = breeze.get_order_detail(
                    order_id=order_id, exchange_code=exchange_code or "NSE"
                )
                logging.info(f"Order details: {order_status}")

                # Check if we got a valid response with Success list
                if (
                    not order_status.get("Success")
                    or not isinstance(order_status["Success"], list)
                    or len(order_status["Success"]) == 0
                ):
                    logging.warning(
                        f"Unexpected order status response format: {order_status}"
                    )
                    time.sleep(wait_interval)
                    waited_time += wait_interval
                    continue

                # Get the first order in the Success list
                order_info = order_status["Success"][0]
                status = order_info.get("status", "Unknown")

                # Calculate filled quantity
                try:
                    filled_qty = int(order_info.get("quantity", 0)) - int(
                        order_info.get("pending_quantity", 0)
                    )
                except (ValueError, TypeError):
                    filled_qty = 0

                logging.info(
                    f"Sell order status for {stock_code} (ID: {order_id}): {status}, "
                    f"Filled: {filled_qty}/{order_info.get('quantity')}"
                )

                # Track status history
                order_status_history.append((datetime.datetime.now(), status))

                # Handle different order statuses
                if status == "Executed":
                    try:
                        executed_price = float(
                            order_info.get("average_price", current_price)
                        )
                        logging.warning(
                            f"Sell order executed for {stock_code} at {executed_price}  - (ID: {order_id})"
                        )
                        break
                    except (ValueError, TypeError):
                        logging.error(f"Invalid price in order response: {order_info}")
                        return False

                elif status in ["Cancelled", "Rejected", "Expired"]:
                    logging.warning(
                        f"Sell order {status} for {stock_code} - (ID: {order_id})"
                    )
                    return False

                # If order is still pending, wait and check again
                time.sleep(wait_interval)
                waited_time += wait_interval

            except Exception as e:
                logging.error(f"Error checking order status: {e}")
                time.sleep(wait_interval)

        if executed_price == 0:
            # Log the status history for debugging
            logging.error(
                f"Sell order for {stock_code} did not execute within expected time"
            )
            logging.error("Order status history:")
            for timestamp, status in order_status_history:
                logging.error(f"{timestamp}: {status}")

            # Try to cancel the order if it's still pending
            if (
                order_status
                and order_status.get("Success")
                and len(order_status["Success"]) > 0
            ):
                order_info = order_status["Success"][0]
                if order_info.get("status") == "Pending":
                    try:
                        cancel_response = breeze.cancel_order(order_id=order_id)
                        logging.info(
                            f"Attempted to cancel pending order: {cancel_response}"
                        )
                    except Exception as e:
                        logging.error(f"Error cancelling order: {e}")

                return False

        # Calculate profit/loss
        profit_loss = (executed_price - entry_price) * quantity
        profit_loss_percent = ((executed_price / entry_price) - 1) * 100

        logging.warning(
            f"Closed position for {stock_code}: P&L = ₹{profit_loss:.2f} ({profit_loss_percent:.2f}%)"
        )

        # Record trade
        exit_time = datetime.datetime.now()
        trade = {
            "stock_code": stock_code,
            "exchange": exchange_code,
            "entry_price": entry_price,
            "exit_price": executed_price,
            "quantity": quantity,
            "entry_time": entry_time,
            "exit_time": exit_time.isoformat(),
            "profit_loss": profit_loss,
            "profit_loss_percent": profit_loss_percent,
            "exit_type": exit_reason,
        }

        today_trades.append(trade)

        # Remove from positions
        del positions[stock_code]

        # Save positions to file immediately
        save_positions()

        # Send email notification
        email_subject = f"Position Closed: {stock_code}"
        email_body = f"""
        EXIT ALERT: {stock_code}

        Details:
        --------
        Entry Price: ₹{entry_price:.2f}
        Exit Price: ₹{executed_price:.2f}
        Quantity: {quantity}
        P&L: ₹{profit_loss:.2f} ({profit_loss_percent:.2f}%)
        Exit Reason: {exit_reason}
        Exit Time: {exit_time.strftime('%Y-%m-%d %H:%M:%S')}
        Holding Period: {(exit_time - datetime.datetime.fromisoformat(entry_time)).days} days

        Overall position result: {"PROFIT" if profit_loss > 0 else "LOSS"}
        """
        send_email(email_subject, email_body)

        return True

    except Exception as e:
        logging.error(f"Exception in exit_position for {stock_code}: {e}")
        return False


def save_positions():
    """Save current positions to file"""
    global positions
    try:
        positions_dir = "positions"
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        filename = os.path.join(positions_dir, f"positions_{today_str}.json")

        if not os.path.exists(positions_dir):
            os.makedirs(positions_dir)

        with open(filename, "w") as f:
            json.dump(positions, f, indent=4)

        logging.info(f"Saved {len(positions)} positions to {filename}")
    except Exception as e:
        logging.error(f"Error saving positions: {e}")


def load_positions():
    """
    Load positions from file. If today's positions file doesn't exist,
    loads positions from the most recent previous trading day's file.
    """
    global positions
    positions_dir = "positions"
    os.makedirs(positions_dir, exist_ok=True)

    try:
        today = datetime.datetime.now()
        today_str = today.strftime("%Y%m%d")
        filename = os.path.join(positions_dir, f"positions_{today_str}.json")

        # If today's file exists, load it
        if os.path.exists(filename):
            with open(filename, "r") as f:
                positions.clear()
                positions.update(json.load(f))
            logging.info(f"Loaded {len(positions)} positions from today's file")
            return

        # If we get here, today's file doesn't exist
        # Look for the most recent positions file
        position_files = sorted(
            [f for f in os.listdir(positions_dir) if f.startswith("positions_")],
            reverse=True,
        )

        if position_files:
            # Get the most recent positions file
            latest_file = position_files[0]
            latest_path = os.path.join(positions_dir, latest_file)

            # Load positions from the latest file
            with open(latest_path, "r") as f:
                positions.clear()
                positions.update(json.load(f))

            # Save as today's positions
            with open(filename, "w") as f:
                json.dump(positions, f, indent=2)

            logging.info(
                f"Copied {len(positions)} positions from {latest_file} to today's file"
            )
        else:
            # No position files exist at all
            positions.clear()
            logging.info("No previous positions found, starting fresh")

    except json.JSONDecodeError as e:
        logging.error(f"Error parsing positions file: {e}")
        positions.clear()
    except Exception as e:
        logging.error(f"Error loading positions: {e}")
        positions.clear()
    finally:
        logging.info(f"Current positions: {positions}")


def save_trades():
    """Save today's trades to file"""
    global today_trades
    try:
        trades_dir = "trades"
        if not os.path.exists(trades_dir):
            os.makedirs(trades_dir)

        today_str = datetime.datetime.now().strftime("%Y%m%d")
        filename = os.path.join(trades_dir, f"trades_{today_str}.json")

        with open(filename, "w") as f:
            json.dump(today_trades, f, indent=4)

        logging.info(f"Saved {len(today_trades)} trades to {filename}")

    except Exception as e:
        logging.error(f"Error saving trades: {e}")


def load_today_trades():
    """Load today's trades from file if exists"""
    global today_trades  # Add this line to modify the global variable
    try:
        trades_dir = "trades"
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        filename = os.path.join(trades_dir, f"trades_{today_str}.json")

        if os.path.exists(filename):
            with open(filename, "r") as f:
                today_trades.clear()  # Clear existing trades
                today_trades.extend(json.load(f))  # Update with loaded trades

            logging.info(f"Loaded {len(today_trades)} trades for today")
        else:
            today_trades.clear()  # Clear trades if no file exists for today
            logging.info("No trades file found for today, starting fresh")
    except Exception as e:
        logging.error(f"Error loading today's trades: {e}")
        today_trades.clear()  # Clear trades on error to avoid inconsistent state


def check_market_status():
    """Check if market is currently open

    Returns:
        bool: True if market is open or in paper trading mode, False otherwise
    """
    # If in paper trading mode, market is always considered open
    if PAPER_TRADING_MODE:
        logging.debug("PAPER TRADING MODE: Market check bypassed")
        return True

    now = datetime.datetime.now()
    current_time = now.time()
    current_day = now.strftime("%A")

    # Trading days: Monday to Friday
    trading_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    # Trading hours: 9:15 AM to 3:30 PM
    market_open = datetime.time(9, 15)
    market_close = datetime.time(15, 30)

    # Check if current day is a trading day
    if current_day not in trading_days:
        logging.info(f"Market closed: Not a trading day ({current_day})")
        return False

    # Check if current time is within market hours
    if current_time < market_open or current_time > market_close:
        logging.info(f"Market closed: Outside trading hours ({current_time})")
        return False

    logging.info("Market is open for trading")
    return True


def get_index_stocks(index_name):
    """
    Get list of stocks in the specified index.

    This function attempts to read stock constituents from a local CSV file in the
    'index_csv' directory (e.g., 'NIFTY_50.csv' for 'NIFTY 50'). If the file is not
    found or an error occurs, it falls back to a hardcoded list for known indices.

    Note: Ensure that the 'index_csv' directory contains CSV files for the indices,
    with filenames like 'NIFTY_50.csv', 'NIFTY_NEXT_50.csv', etc. These files should
    have a 'Symbol' column with stock codes and can be downloaded from the NSE website.

    Args:
        index_name (str): Name of the index (e.g., "NIFTY 50", "NIFTY NEXT 50")

    Returns:
        list: List of dictionaries with 'stock_code' and 'exchange_code'
    """
    try:
        # Construct the filename based on the index_name
        filename = f"{index_name.replace(' ', '_')}.csv"
        filepath = os.path.join(INDEX_DIR, filename)

        if not os.path.exists(filepath):
            logging.warning(f"CSV file for {index_name} not found at {filepath}")
            raise FileNotFoundError(f"CSV file for {index_name} not found")

        # Read the CSV file
        df = pd.read_csv(filepath)

        # Ensure 'Symbol' column exists
        if "Symbol" not in df.columns:
            raise ValueError(f"CSV file for {index_name} is missing 'Symbol' column")

        # Extract and validate stock codes
        stock_codes = []
        invalid_codes = []

        for code in df["Symbol"]:
            if stock_mapper.is_valid_symbol(code):
                stock_codes.append({"stock_code": code, "exchange_code": "NSE"})
            else:
                invalid_codes.append(code)

        if invalid_codes:
            logging.warning(
                f"Found {len(invalid_codes)} invalid stock symbols in {index_name}: {', '.join(invalid_codes)}"
            )

        # Return list in required format
        logging.info(
            f"Loaded {len(stock_codes)} valid stocks from {filepath} for {index_name}"
        )
        return stock_codes

    except Exception as e:
        logging.error(f"Error getting index stocks for {index_name}: {e}")

        # Fallback to hardcoded list for known indices, filtered by valid symbols
        if index_name == "NIFTY 50":
            logging.info(f"Using filtered hardcoded list for {index_name}")
            nifty50 = [
                "RELIANCE",
                "HDFCBANK",
                "INFY",
                "ICICIBANK",
                "TCS",
                "KOTAKBANK",
                "HINDUNILVR",
                "LT",
                "ITC",
                "SBIN",
                "BAJFINANCE",
                "BHARTIARTL",
                "ASIANPAINT",
                "AXISBANK",
                "MARUTI",
            ]
            return [
                {"stock_code": code, "exchange_code": "NSE"}
                for code in nifty50
                if stock_mapper.is_valid_symbol(code)
            ]
        elif index_name == "NIFTY NEXT 50":
            logging.info(f"Using filtered hardcoded list for {index_name}")
            next50 = [
                "ADANIPORTS",
                "ADANIGREEN",
                "PIDILITIND",
                "GODREJCP",
                "HDFCLIFE",
                "DABUR",
                "HAVELLS",
                "SBILIFE",
                "BERGEPAINT",
                "MUTHOOTFIN",
            ]
            return [
                {"stock_code": code, "exchange_code": "NSE"}
                for code in next50
                if stock_mapper.is_valid_symbol(code)
            ]
        else:
            logging.warning(
                f"No hardcoded list available for {index_name}, returning empty list"
            )
            return []


def filter_fundamentals(stock_codes, exchange_code="NSE"):
    """
    Filter stocks based on fundamental criteria

    Args:
        stock_codes (list): List of stock codes to filter
        exchange_code (str): Exchange code (default: NSE)

    Returns:
        list: Filtered list of stock codes meeting fundamental criteria
    """
    try:
        filtered = []
        for code in stock_codes:
            try:
                # For NSE stocks, append .NS to the ticker symbol
                ticker_suffix = ".NS" if exchange_code == "NSE" else ""
                ticker = yf.Ticker(f"{code}{ticker_suffix}")

                # Fetch company info
                info = ticker.info

                # Extract fundamental metrics (with defaults if not available)
                pe = info.get("trailingPE", float("inf"))
                debt_eq = info.get("debtToEquity", float("inf"))
                earnings_growth = info.get("earningsGrowth", 0)
                profit_margin = info.get("profitMargins", 0)

                # Apply fundamental filters
                # PE < 20, debt-to-equity < 1, positive earnings growth
                if pe < 20 and debt_eq < 1 and earnings_growth > 0.1:
                    logging.warning(
                        f"Stock {code} passed fundamental filters: PE={pe:.2f}, D/E={debt_eq:.2f}, EG={earnings_growth:.2f}"
                    )
                    filtered.append(code)
                else:
                    logging.info(
                        f"Stock {code} failed fundamental filters: PE={pe:.2f}, D/E={debt_eq:.2f}, EG={earnings_growth:.2f}"
                    )
            except Exception as e:
                logging.warning(f"Error fetching fundamentals for {code}: {e}")
                continue

        logging.info(
            f"Fundamental screening: {len(filtered)}/{len(stock_codes)} stocks passed"
        )
        return filtered

    except Exception as e:
        logging.error(f"Error in fundamental filtering: {e}")
        return stock_codes  # Return original list if filtering fails


def screen_stocks(stock_universe, market_condition, max_stocks=100, interval="1day"):
    """Screen stocks for potential opportunities

    Args:
        stock_universe (list): List of stocks to screen
        market_condition (dict): Current market condition analysis
        max_stocks (int): Maximum number of stocks to screen (default: 10)

    Returns:
        list: Scored stock opportunities
    """
    opportunities = []

    # Limit the number of stocks to screen
    stocks_to_screen = stock_universe[:max_stocks]
    logging.info(
        f"Screening top {len(stocks_to_screen)} out of {len(stock_universe)} stocks for opportunities"
    )

    for stock in stocks_to_screen:
        stock_code = stock["stock_code"]
        exchange_code = stock["exchange_code"]

        # Skip if already in a position
        if stock_code in positions:
            continue

        try:
            # Get current price
            current_price = get_current_price(stock_code, exchange_code)
            logging.info(f"Current price for {stock_code}: {current_price}")
            if current_price is None:
                continue

            # Check price range
            if current_price < MIN_PRICE or current_price > MAX_PRICE:
                logging.info(
                    f"Skipping {stock_code}: Price {current_price} outside range {MIN_PRICE}-{MAX_PRICE}"
                )
                continue

            # Get historical data
            hist_data = get_historical_data(
                stock_code, exchange_code, interval=interval
            )
            if hist_data is None:
                logging.warning(f"No historical data for {stock_code}")
                continue

            min_points = MIN_DATA_POINTS.get(
                interval, 20
            )  # Default to 20 if interval not found
            if len(hist_data) < min_points:
                logging.warning(
                    f"Skipping {stock_code}: Only {len(hist_data)} data points available, "
                    f"need at least {min_points} points for {interval} interval"
                )
                continue

            # Check volume
            avg_volume = hist_data["volume"].tail(5).mean()
            if avg_volume < MIN_VOLUME:
                logging.info(
                    f"Skipping {stock_code}: Volume {avg_volume} below minimum {MIN_VOLUME}"
                )
                continue

            # Calculate indicators
            with_indicators = calculate_indicators(hist_data)
            logging.info(
                f"Indicators calculated for {stock_code}" + str(with_indicators)
            )
            if with_indicators is None:
                continue

            # Check for buy signal
            buy_signal, signal_reason = check_buy_signal(
                with_indicators, market_condition
            )
            logging.warning(
                f"Buy signal for {stock_code}: {buy_signal} ({signal_reason})"
            )

            if buy_signal:
                # Get the latest ATR for stop calculation
                latest_atr = with_indicators["atr"].iloc[-1]

                # Calculate stop loss
                stop_loss = current_price - (2 * latest_atr)

                # Calculate position size
                quantity, position_value = calculate_position_size(
                    current_price, stop_loss, stock_code
                )

                if quantity <= 0:
                    continue

                # Calculate risk-reward ratio (assuming 5% target)
                risk = (current_price - stop_loss) * quantity
                reward = current_price * 0.05 * quantity  # 5% target
                risk_reward = reward / risk if risk > 0 else 0

                # Create opportunity
                opportunity = {
                    "stock_code": stock_code,
                    "exchange_code": exchange_code,
                    "current_price": current_price,
                    "stop_loss": stop_loss,
                    "quantity": quantity,
                    "position_value": position_value,
                    "risk_reward": risk_reward,
                    "signal_reason": signal_reason,
                }

                opportunities.append(opportunity)
                logging.warning(
                    f"Found opportunity: {stock_code} at {current_price:.2f}, R:R {risk_reward:.2f}"
                )

        except Exception as e:
            logging.error(f"Error screening {stock_code}: {e}")
            continue

    # Sort by risk-reward ratio
    opportunities.sort(key=lambda x: x["risk_reward"], reverse=True)

    logging.warning(f"Found {len(opportunities)} opportunities")
    return opportunities


def manage_positions(market_condition):
    """
    SIMPLIFIED position management - only handles data collection
    ALL exit logic is in check_sell_signal()
    """
    positions_to_check = list(positions.items())
    exited_count = 0
    MIN_HOLDING_DAYS = 1  # Prevent overtrading

    for stock_code, position in positions_to_check:
        if stock_code not in positions or position.get("exiting", False):
            continue

        try:
            positions[stock_code]["exiting"] = True
            exchange_code = position["exchange"]
            entry_price = position["entry_price"]
            entry_time = position.get("entry_time")

            # Calculate days held
            days_held = 0
            if entry_time:
                try:
                    entry_date = datetime.datetime.fromisoformat(entry_time)
                    time_diff = datetime.datetime.now() - entry_date
                    days_held = time_diff.days

                    # Handle same-day positions
                    if days_held == 0:
                        hours_held = time_diff.total_seconds() / 3600
                        if hours_held >= 6:
                            days_held = 1

                except Exception as e:
                    logging.warning(f"Error parsing entry_time for {stock_code}: {e}")
                    days_held = 1

            # Skip if too new (prevent overtrading)
            if days_held < MIN_HOLDING_DAYS:
                continue

            # Get current price
            current_price = get_current_price(stock_code, exchange_code)
            if current_price is None:
                continue

            # Calculate current profit for logging
            profit_percent = ((current_price / entry_price) - 1) * 100
            logging.info(
                f"{stock_code}: {profit_percent:.2f}% profit after {days_held} days"
            )

            # Get historical data and indicators
            hist_data = get_historical_data(stock_code, exchange_code)
            if hist_data is None:
                continue

            with_indicators = calculate_indicators(hist_data)
            if with_indicators is None:
                continue

            # ============================================
            # Sell signal check
            # ============================================

            sell_signal, reason = check_sell_signal(
                with_indicators, entry_price, days_held, market_condition
            )

            if sell_signal:
                logging.warning(f"{stock_code}: Exit triggered - {reason}")
                if exit_position(stock_code, exit_reason=reason):
                    exited_count += 1

        except Exception as e:
            logging.error(f"Error managing position for {stock_code}: {e}")
        finally:
            if stock_code in positions:
                positions[stock_code].pop("exiting", None)

    return exited_count


price_cache = {}


def get_cached_price(stock_code, exchange_code):
    """
    Get the current price of a stock from cache or fetch it if not cached.
    """
    global price_cache
    if stock_code not in price_cache:
        price_cache[stock_code] = get_current_price(stock_code, exchange_code)
    return price_cache[stock_code]


def generate_daily_report():
    """Generate and send daily trading report"""
    global positions, today_trades
    load_positions()
    load_today_trades()

    daily_pnl = 0
    for trade in today_trades:
        daily_pnl += trade.get("profit_loss", 0)

    total_trades = len(today_trades)
    winning_trades = sum(1 for trade in today_trades if trade.get("profit_loss", 0) > 0)
    losing_trades = sum(1 for trade in today_trades if trade.get("profit_loss", 0) < 0)

    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    current_positions_value = 0
    unrealized_pnl = 0

    # log existing positions status
    log_position_status()

    for stock_code, position in positions.items():
        quantity = position.get("quantity", 0)
        entry_price = position.get("entry_price", 0)

        current_price = get_cached_price(stock_code, position.get("exchange", "NSE"))

        if current_price:
            position_value = current_price * quantity
            position_pnl = (current_price - entry_price) * quantity

            current_positions_value += position_value
            unrealized_pnl += position_pnl

    report = f"""DAILY TRADING REPORT - {datetime.datetime.now().strftime('%Y-%m-%d')}
=======================================================

PERFORMANCE SUMMARY:
--------------------
Realized P&L: ₹{daily_pnl:.2f}
Unrealized P&L: ₹{unrealized_pnl:.2f}
Total P&L: ₹{daily_pnl + unrealized_pnl:.2f}

TRADING ACTIVITY:
-----------------
Total Trades: {total_trades}
Winning Trades: {winning_trades}
Losing Trades: {losing_trades}
Win Rate: {win_rate:.1f}%

CURRENT POSITIONS:
-----------------"""

    if positions:
        for stock_code, position in positions.items():
            entry_price = position.get("entry_price", 0)
            quantity = position.get("quantity", 0)
            stop_loss = position.get("stop_loss", 0)
            entry_time = position.get("entry_time", "Unknown")

            current_price = get_cached_price(
                stock_code, position.get("exchange", "NSE")
            )

            if current_price:
                pnl = (current_price - entry_price) * quantity
                pnl_percent = ((current_price / entry_price) - 1) * 100

                report += f"""
{stock_code}:
    Entry Price: ₹{entry_price:.2f}
    Current Price: ₹{current_price:.2f}
    Quantity: {quantity}
    Stop Loss: ₹{stop_loss:.2f}
    Unrealized P&L: ₹{pnl:.2f} ({pnl_percent:.2f}%)
    Held Since: {entry_time}"""
            else:
                report += f"""
{stock_code}:
    Entry Price: ₹{entry_price:.2f}
    Current Price: Unable to fetch
    Quantity: {quantity}
    Stop Loss: ₹{stop_loss:.2f}
    Held Since: {entry_time}"""
    else:
        report += "\nNo positions found."

    report += "\n\nCOMPLETED TRADES TODAY:\n"
    report += "----------------------"

    if today_trades:
        for i, trade in enumerate(today_trades, 1):
            report += f"""
Trade #{i}:
    Stock: {trade.get('stock_code', 'Unknown')}
    Entry: ₹{trade.get('entry_price', 0):.2f}
    Exit: ₹{trade.get('exit_price', 0):.2f}
    Quantity: {trade.get('quantity', 0)}
    P&L: ₹{trade.get('profit_loss', 0):.2f} ({trade.get('profit_loss_percent', 0):.2f}%)
    Exit Type: {trade.get('exit_type', 'Unknown')}
    Exit Time: {trade.get('exit_time', 'Unknown')}"""
    else:
        report += "\nNo trades completed today."

    logging.info("Daily report generated")

    report_dir = "reports"
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)

    report_file = os.path.join(
        report_dir, f"report_{datetime.datetime.now().strftime('%Y%m%d')}.txt"
    )
    with open(report_file, "w") as f:
        f.write(report)

    send_email("Trading Daily Report", report)

    return report


def log_position_status():
    """Simple position status logging"""
    global positions

    if not positions:
        return

    logging.info("=== POSITION STATUS ===")
    for stock_code, position in positions.items():
        entry_time = position.get("entry_time")
        entry_price = position.get("entry_price", 0)

        if entry_time:
            try:
                entry_date = datetime.datetime.fromisoformat(entry_time)
                days_held = (datetime.datetime.now() - entry_date).days

                current_price = get_current_price(
                    stock_code, position.get("exchange", "NSE")
                )
                if current_price and entry_price:
                    profit_pct = ((current_price / entry_price) - 1) * 100

                    # Week indicator
                    if days_held <= 7:
                        week = "W1"
                    elif days_held <= 14:
                        week = "W2"
                    elif days_held <= 21:
                        week = "W3"
                    else:
                        week = f"W4+({days_held}d)"

                    logging.info(
                        f"{stock_code}: {week} | {profit_pct:+.1f}% | {days_held}d"
                    )
            except:
                pass


def run_strategy():
    """
    Run the trading strategy with mid-term focus
    Returns:
    True if strategy execution completed successfully, False otherwise
    """
    global today_trades, positions
    logging.info("STARTED RUNNINV MID-TERM TRADING STRATEGY")
    load_positions()
    logging.warning(f"Current positions: {positions}")
    load_today_trades()
    logging.warning(f"Current trades: {today_trades}")

    # Check if market is open
    if not check_market_status():
        logging.info("Market is closed. Skipping strategy execution.")
        return True  # Successfully skipped

    try:
        # Get market index data and calculate indicators
        market_index = INDEX_FOR_STOCKS
        #map to actual index identifiers for yahoo api
        if(market_index == "NIFTY 50"):
            market_index = "NIFTY"
        elif(market_index == "SENSEX"):
            market_index = "SENSEX"
        elif(market_index == "BANKNIFTY"):
            market_index = "BANKNIFTY"
        else:
            logging.warning("Invalid market index: " + market_index)
            return False

        index_data = get_historical_data_index(market_index, days=300)
        if index_data.empty:
            logging.warning("Could not get market index data")
            return False  # Failed to get market data

        # Calculate indicators directly
        if "sma_20" not in index_data.columns:
            index_data["sma_20"] = index_data["close"].rolling(window=20).mean()

        if "sma_50" not in index_data.columns:
            index_data["sma_50"] = index_data["close"].rolling(window=50).mean()

        if "sma_200" not in index_data.columns:
            index_data["sma_200"] = index_data["close"].rolling(window=200).mean()

        # Calculate RSI if needed for market condition
        if "rsi" not in index_data.columns:
            delta = index_data["close"].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            rs = avg_gain / avg_loss
            index_data["rsi"] = 100 - (100 / (1 + rs))

        if "sma_200" in index_data.columns:
            current_price = index_data["close"].iloc[-1]
            sma_200 = index_data["sma_200"].iloc[-1]
            days_available = len(index_data)

            print(
                f"\nMARKET SMA DEBUG: NIFTY Current: {current_price:.2f}, 200-day SMA: {sma_200:.2f}"
            )
            print(
                f"Difference: {(current_price - sma_200):.2f} points ({((current_price/sma_200)-1)*100:.2f}%)"
            )
            print(
                f"Status: {'ABOVE' if current_price > sma_200 else 'BELOW'} 200-day SMA"
            )
            print(f"Data points available: {days_available}/200\n")

            logging.info(
                f"MARKET DEBUG: NIFTY={current_price:.2f}, 200-SMA={sma_200:.2f}, Diff={((current_price/sma_200)-1)*100:.2f}%, Points={days_available}"
            )
        # Analyze market condition
        market_condition = analyze_market_condition(index_data)
        logging.info(f"Market condition: {market_condition}")

        # Manage existing positions with mid-term criteria
        positions_exited = manage_positions(market_condition)
        logging.warning(f"Exited {positions_exited} positions")

        updated_stops = update_trailing_stops()
        logging.warning(f"Updated trailing stops for {updated_stops} positions")

        # Only look for new opportunities if we have fewer than MAX_POSITIONS
        # AND the market is above 200-day SMA (critical for mid-term trading)
        if len(positions) < MAX_POSITIONS and market_condition.get(
            "above_200_sma", False
        ):
            try:
                # Get both NIFTY 50 and NIFTY NEXT 50 stocks
                nifty50_stocks = get_index_stocks("NIFTY 50")
                nifty_next50_stocks = get_index_stocks("NIFTY NEXT 50")
                stock_universe = nifty50_stocks + nifty_next50_stocks
                logging.info(
                    f"Expanded stock universe: {len(stock_universe)} stocks (NIFTY 50 + NIFTY NEXT 50)"
                )
            except Exception as e:
                logging.warning(
                    f"Error getting expanded universe: {e}, falling back to default"
                )
                stock_universe = get_index_stocks(
                    INDEX_FOR_STOCKS
                )  # Fallback to default index
            # Get stock universe
            limited_universe = stock_universe[:100]  # Limit to 100 stocks

            # Screen stocks for opportunities
            opportunities = screen_stocks(limited_universe, market_condition)

            # Take the best opportunity
            if opportunities:
                best_opportunity = opportunities[0]
                if enter_position(
                    best_opportunity["stock_code"], best_opportunity["exchange_code"]
                ):
                    logging.warning(
                        f"Entered position for {best_opportunity['stock_code']}"
                    )
            else:
                logging.warning("No suitable opportunities found")
        else:
            if not market_condition.get("above_200_sma", False):
                logging.warning(
                    "Market below 200-day SMA. Not looking for new positions."
                )
            else:
                logging.warning(
                    f"Already at maximum positions ({len(positions)}/{MAX_POSITIONS})"
                )

        # Save positions and trades
        save_positions()
        save_trades()
        logging.warning("Run Strategy completed: Positions and trades saved")

        return True  # Strategy execution successful

    except Exception as e:
        logging.error(f"Error in strategy execution: {e}")
        logging.exception("Stack trace:")  # Add this to get the full stack trace
        return False  # Strategy execution failed


if __name__ == "__main__":
    # Set up logging directory
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Set up reports directory
    report_dir = "reports"
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)

    # Load any existing positions
    load_positions()

    # Load today's trades if any
    load_today_trades()

    # Initialize API connection
    if not initialize_api():
        logging.error("Failed to initialize API. Exiting.")
        exit(1)

    try:
        # Run the strategy once
        run_strategy()

        # Save trades before exiting
        save_trades()

    except KeyboardInterrupt:
        logging.info("Strategy execution interrupted")

    except Exception as e:
        logging.error(f"Unhandled error in strategy execution: {e}")

        # Send error notification
        error_message = f"Trading strategy encountered an error: {str(e)}"
        send_email("Trading Strategy Error", error_message)

    finally:
        logging.info("Strategy execution complete")

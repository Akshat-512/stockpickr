#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Price Debugging Module for ICICI Direct Breeze API
Standalone file to test and debug price retrieval issues
"""

import time
import logging
import json
import configparser
from breeze_connect import BreezeConnect
from stock_utils import stock_mapper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("price_debug.log"), logging.StreamHandler()],
    force=True,
)

# Global breeze connection
breeze = None


def initialize_api():
    """Initialize the Breeze API connection"""
    global breeze

    try:
        # Load configuration
        config = configparser.ConfigParser()
        config.read("config.ini")

        API_KEY = config.get("APICredentials", "api_key", fallback="")
        API_SECRET = config.get("APICredentials", "api_secret", fallback="")
        SESSION_TOKEN = config.get("APICredentials", "session_token", fallback="")

        if not API_KEY or not API_SECRET or not SESSION_TOKEN:
            logging.error("Missing API credentials in config.ini")
            return False

        logging.info("Initializing API connection")
        breeze = BreezeConnect(api_key=API_KEY)
        breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)

        # Test connection
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
        logging.error(f"Failed to initialize API: {e}")
        return False


def _find_price_recursively(data, depth=0, max_depth=5):
    """Recursively search for price in nested data structures"""
    if depth > max_depth or data is None:
        return None

    # If it's a number and looks like a reasonable stock price
    if isinstance(data, (int, float)):
        if 1 <= data <= 100000:  # Reasonable price range
            return float(data)
        return None

    # If it's a string that can be converted to a price
    if isinstance(data, str):
        try:
            price = float(data)
            if 1 <= price <= 100000:
                return price
        except (ValueError, TypeError):
            pass
        return None

    # If it's a dictionary, search through it
    if isinstance(data, dict):
        # First check common price field names
        price_fields = [
            "ltp",
            "last_price",
            "last",
            "close",
            "price",
            "lastPrice",
            "currentPrice",
        ]
        for field in price_fields:
            if field in data:
                result = _find_price_recursively(data[field], depth + 1, max_depth)
                if result:
                    return result

        # Then search through all values
        for key, value in data.items():
            if "price" in key.lower() or "ltp" in key.lower() or "last" in key.lower():
                result = _find_price_recursively(value, depth + 1, max_depth)
                if result:
                    return result

    # If it's a list, search through items
    if isinstance(data, list):
        for item in data:
            result = _find_price_recursively(item, depth + 1, max_depth)
            if result:
                return result

    return None


def get_current_price_debug(stock_code, exchange_code="NSE", max_retries=3):
    """Get current market price for a stock with enhanced debugging

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
        logging.info(
            f"Converted NSE symbol {stock_code} to Breeze symbol {breeze_symbol}"
        )

    retry_count = 0
    base_delay = 1

    while retry_count <= max_retries:
        try:
            # Add delay between retries
            if retry_count > 0:
                wait_time = base_delay * (2 ** (retry_count - 1))
                logging.info(
                    f"Retry {retry_count}/{max_retries} for {breeze_symbol} - Waiting {wait_time} seconds..."
                )
                time.sleep(wait_time)

            # Get latest quote
            quote = breeze.get_quotes(
                stock_code=breeze_symbol,
                exchange_code=exchange_code,
                expiry_date="",
                product_type="cash",
                right="",
                strike_price="",
            )

            # DETAILED LOGGING FOR DEBUGGING
            print(
                f"\n=== API Response Debug for {stock_code} (Attempt {retry_count + 1}) ==="
            )
            print(f"Raw response type: {type(quote)}")
            if quote:
                print(f"Raw response: {json.dumps(quote, indent=2, default=str)}")
            else:
                print("Raw response: None")

            logging.info(
                f"API Response for {stock_code} (attempt {retry_count + 1}): {quote}"
            )

            if not quote:
                logging.warning(f"Empty response for {stock_code}")
                retry_count += 1
                continue

            # Try to extract price using multiple strategies
            price = None

            # Strategy 1: Check Success list format
            if isinstance(quote, dict) and "Success" in quote:
                success_data = quote["Success"]
                print(f"Strategy 1 - Success data type: {type(success_data)}")

                if isinstance(success_data, list) and len(success_data) > 0:
                    for i, item in enumerate(success_data):
                        print(f"Success item {i}: {item}")
                        if isinstance(item, dict):
                            # Try different price fields in order of preference
                            for price_field in [
                                "ltp",
                                "last_price",
                                "last",
                                "close",
                                "price",
                            ]:
                                if (
                                    price_field in item
                                    and item[price_field] is not None
                                ):
                                    try:
                                        temp_price = float(item[price_field])
                                        if temp_price > 0:
                                            price = temp_price
                                            print(
                                                f"✓ Found price {price} using field '{price_field}'"
                                            )
                                            break
                                    except (ValueError, TypeError):
                                        continue
                        if price:
                            break

            # Strategy 2: Check direct fields in quote
            if not price and isinstance(quote, dict):
                print("Strategy 2 - Checking direct fields in quote")
                for price_field in ["ltp", "last_price", "last", "close", "price"]:
                    if price_field in quote and quote[price_field] is not None:
                        try:
                            temp_price = float(quote[price_field])
                            if temp_price > 0:
                                price = temp_price
                                print(
                                    f"✓ Found price {price} using direct field '{price_field}'"
                                )
                                break
                        except (ValueError, TypeError):
                            continue

            # Strategy 3: Legacy format with stat and values
            if not price and isinstance(quote, dict) and quote.get("stat") == "Ok":
                print("Strategy 3 - Checking legacy format")
                if "values" in quote and isinstance(quote["values"], list):
                    for item in quote["values"]:
                        if isinstance(item, dict):
                            for price_field in ["last", "ltp", "close", "price"]:
                                if (
                                    price_field in item
                                    and item[price_field] is not None
                                ):
                                    try:
                                        temp_price = float(item[price_field])
                                        if temp_price > 0:
                                            price = temp_price
                                            print(
                                                f"✓ Found price {price} using legacy field '{price_field}'"
                                            )
                                            break
                                    except (ValueError, TypeError):
                                        continue
                            if price:
                                break

            # Strategy 4: Recursive search through the entire response
            if not price:
                print("Strategy 4 - Recursive search")
                price = _find_price_recursively(quote)
                if price:
                    print(f"✓ Found price {price} using recursive search")

            if price and price > 0:
                print(f"SUCCESS: Got price for {stock_code}: {price}")
                logging.info(f"Successfully got price for {stock_code}: {price}")
                return float(price)
            else:
                print(
                    f"FAILED: No valid price found for {stock_code} in attempt {retry_count + 1}"
                )
                logging.warning(
                    f"No valid price found for {stock_code} in attempt {retry_count + 1}"
                )

            retry_count += 1

        except Exception as e:
            error_msg = str(e)
            print(
                f"ERROR: Exception getting price for {stock_code} (attempt {retry_count + 1}): {error_msg}"
            )
            logging.error(
                f"Error getting price for {stock_code} (attempt {retry_count + 1}): {error_msg}"
            )

            # Check if it's a temporary error
            if any(
                err in error_msg.lower()
                for err in [
                    "error_exception",
                    "nonetype",
                    "503",
                    "timeout",
                    "connection",
                ]
            ):
                logging.debug(f"Temporary error detected, will retry")
                retry_count += 1
            else:
                logging.exception("Unexpected error details:")
                return None

    print(
        f"FINAL FAILURE: Failed to get price for {stock_code} after {max_retries + 1} attempts"
    )
    logging.error(
        f"Failed to get price for {stock_code} after {max_retries + 1} attempts"
    )
    return None


def test_multiple_stocks(stocks_to_test=None):
    """Test price retrieval for multiple stocks"""
    if stocks_to_test is None:
        stocks_to_test = [
            ("RELIANCE", "NSE"),
            ("TCS", "NSE"),
            ("INFY", "NSE"),
            ("HDFCBANK", "NSE"),
            ("ICICIBANK", "NSE"),
        ]

    print(f"\n{'='*60}")
    print(f"TESTING PRICE RETRIEVAL FOR {len(stocks_to_test)} STOCKS")
    print(f"{'='*60}")

    results = {}

    for stock_code, exchange_code in stocks_to_test:
        print(f"\n{'-'*40}")
        print(f"Testing: {stock_code} ({exchange_code})")
        print(f"{'-'*40}")

        try:
            price = get_current_price_debug(stock_code, exchange_code)
            results[stock_code] = price

            if price:
                print(f"✅ SUCCESS: {stock_code} = ₹{price}")
            else:
                print(f"❌ FAILED: {stock_code} - No price retrieved")

        except Exception as e:
            print(f"❌ ERROR: {stock_code} - {e}")
            results[stock_code] = None

        # Small delay between requests
        time.sleep(1)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    successful = 0
    for stock_code, price in results.items():
        if price:
            print(f"✅ {stock_code:<12} = ₹{price}")
            successful += 1
        else:
            print(f"❌ {stock_code:<12} = Failed")

    print(
        f"\nSuccess Rate: {successful}/{len(stocks_to_test)} ({successful/len(stocks_to_test)*100:.1f}%)"
    )

    return results


def test_raw_api_call(stock_code="RELIANCE", exchange_code="NSE"):
    """Test raw API call to see exact response structure"""
    print(f"\n{'='*60}")
    print(f"RAW API CALL TEST FOR {stock_code}")
    print(f"{'='*60}")

    try:
        # Get the breeze symbol
        breeze_symbol = stock_mapper.get_breeze_symbol(stock_code)
        print(f"Original symbol: {stock_code}")
        print(f"Breeze symbol: {breeze_symbol}")

        # Make the API call
        print(f"\nCalling breeze.get_quotes() with:")
        print(f"  stock_code: {breeze_symbol}")
        print(f"  exchange_code: {exchange_code}")
        print(f"  product_type: cash")

        quote = breeze.get_quotes(
            stock_code=breeze_symbol,
            exchange_code=exchange_code,
            expiry_date="",
            product_type="cash",
            right="",
            strike_price="",
        )

        print(f"\nRAW API RESPONSE:")
        print(f"Type: {type(quote)}")

        if quote:
            print(f"JSON Response:")
            print(json.dumps(quote, indent=2, default=str))
        else:
            print("Response is None or empty")

    except Exception as e:
        print(f"Error in raw API call: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Main function for testing price retrieval"""
    print("ICICI Breeze Price Debug Tool")
    print("=" * 50)

    # Initialize API
    if not initialize_api():
        print("❌ Failed to initialize API connection")
        return

    print("✅ API connection successful")

    # Test options
    while True:
        print(f"\nChoose test option:")
        print("1. Test single stock (detailed debug)")
        print("2. Test multiple stocks")
        print("3. Raw API call test")
        print("4. Exit")

        choice = input("\nEnter choice (1-4): ").strip()

        if choice == "1":
            stock = (
                input("Enter stock symbol (default: RELIANCE): ").strip() or "RELIANCE"
            )
            exchange = input("Enter exchange (default: NSE): ").strip() or "NSE"

            print(f"\nTesting detailed price retrieval for {stock}...")
            price = get_current_price_debug(stock, exchange)

            if price:
                print(f"\n🎉 FINAL RESULT: {stock} = ₹{price}")
            else:
                print(f"\n😞 FINAL RESULT: Failed to get price for {stock}")

        elif choice == "2":
            print("\nTesting multiple stocks...")
            test_multiple_stocks()

        elif choice == "3":
            stock = (
                input("Enter stock symbol (default: RELIANCE): ").strip() or "RELIANCE"
            )
            exchange = input("Enter exchange (default: NSE): ").strip() or "NSE"
            test_raw_api_call(stock, exchange)

        elif choice == "4":
            print("Goodbye!")
            break

        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()

import logging
import time
from breeze_connect import BreezeConnect
import configparser

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Load configuration
config = configparser.ConfigParser()
config.read("config.ini")

# API credentials
API_KEY = config.get("APICredentials", "api_key", fallback="")
API_SECRET = config.get("APICredentials", "api_secret", fallback="")
SESSION_TOKEN = config.get("APICredentials", "session_token", fallback="")


def test_nifty50_symbols():
    """Test all NIFTY 50 symbol mappings to find which ones work with Breeze API"""

    # Initialize Breeze API
    breeze = BreezeConnect(api_key=API_KEY)
    breeze.generate_session(api_secret=API_SECRET, session_token=SESSION_TOKEN)

    # List of pairs to test [NSE_Symbol, Breeze_Symbol]
    symbols_to_test = {
        # Confirmed working symbols
        "AXISBANK": "AXIBAN",
        "TATAMOTORS": "TATMOT",
        # Likely conversions based on pattern (remove vowels, shorten)
        "ADANIENT": "ADAENT",
        "ADANIPORTS": "ADAPOR",
        "APOLLOHOSP": "APLHOS",
        "ASIANPAINT": "ASIPAI",
        "BAJAJ-AUTO": "BAJAUTO",  # Might keep hyphen
        "BAJAJFINSV": "BAJFSV",
        "BAJFINANCE": "BAJFIN",
        "BHARTIARTL": "BHAART",
        "BPCL": "BPCL",  # Likely unchanged (already short)
        "BRITANNIA": "BRITIND",
        "CIPLA": "CIPLA",  # Likely unchanged (already short)
        "COALINDIA": "COALIND",
        "DIVISLAB": "DIVLAB",
        "DRREDDY": "DRREDY",
        "EICHERMOT": "EICMOT",
        "GRASIM": "GRASIM",  # Likely unchanged (already short)
        "HCLTECH": "HCLTEC",
        "HDFCBANK": "HDFBAN",
        "HDFCLIFE": "HDFLIFE",
        "HEROMOTOCO": "HERMOT",
        "HINDALCO": "HINDAL",
        "HINDUNILVR": "HINLVR",
        "ICICIBANK": "ICIBAN",
        "INDUSINDBK": "INDBAN",
        "INFY": "INFY",  # Likely unchanged (already short)
        "ITC": "ITC",  # Likely unchanged (already short)
        "JSWSTEEL": "JSWSTL",
        "KOTAKBANK": "KOTBAN",
        "LT": "LT",  # Likely unchanged (already short)
        "M&M": "M&M",  # Likely unchanged (already short)
        "MARUTI": "MARUTI",  # May remain unchanged
        "NESTLEIND": "NESIND",
        "NTPC": "NTPC",  # Likely unchanged (already short)
        "ONGC": "ONGC",  # Likely unchanged (already short)
        "POWERGRID": "POWGRD",
        "RELIANCE": "REL",  # Could be shortened this way
        "SBILIFE": "SBILIFE",  # May remain unchanged
        "SBIN": "SBIN",  # Likely unchanged (already short)
        "SUNPHARMA": "SUNPHA",
        "TATACONSUM": "TATCON",
        "TATASTEEL": "TATSTL",
        "TCS": "TCS",  # Likely unchanged (already short)
        "TECHM": "TECMAH",
        "TITAN": "TITAN",  # May remain unchanged
        "ULTRACEMCO": "ULTCEM",
        "UPL": "UPL",  # Likely unchanged (already short)
        "WIPRO": "WIPRO",  # May remain unchanged
        # Newer NIFTY 50 additions that might be present
        "ZOMATO": "ZOMATO",  # Likely unchanged
        "JIOFIN": "JIOFIN",  # Jio Financial Services - likely unchanged
        "LTIM": "LTIM",  # LTI Mindtree - likely unchanged
        "PIDILITIND": "PIDIND",  # Pidilite Industries
        "SIEMENS": "SIEMENS",  # Likely unchanged
        "SHREECEM": "SHRECEM",  # Shree Cement
        "TIINDIA": "TIIND",  # Tube Investments of India
        "HAVELLS": "HAVELLS",  # Likely unchanged
        "SBICARD": "SBICARD",  # Likely unchanged
        "SHRIRAMFIN": "SHRIFIN",  # Shriram Finance
        "BEL": "BEL",  # Bharat Electronics - likely unchanged
    }

    results = []

    for nse_symbol, breeze_symbol in symbols_to_test.items():
        try:
            logging.info(f"Testing: {nse_symbol} -> {breeze_symbol}")

            # First try with the Breeze symbol
            quote = breeze.get_quotes(
                stock_code=breeze_symbol,
                exchange_code="NSE",
                product_type="cash",
                expiry_date="",
                right="",
                strike_price="",
            )

            # Log complete response for debugging
            logging.info(f"Response for {breeze_symbol}: {quote}")
            
            if isinstance(quote, dict):
                logging.info(f"Response keys: {list(quote.keys())}")
                if "Success" in quote and quote["Success"] and isinstance(quote["Success"], list) and len(quote["Success"]) > 0:
                    first_item = quote["Success"][0]
                    logging.info(f"First item in Success: {first_item}")
                    if isinstance(first_item, dict):
                        logging.info(f"Available fields in first item: {list(first_item.keys())}")
            
            # Try to extract price from different possible locations
            price = None
            if isinstance(quote, dict):
                if "Success" in quote and quote["Success"] and isinstance(quote["Success"], list) and len(quote["Success"]) > 0:
                    first_item = quote["Success"][0]
                    if isinstance(first_item, dict):
                        # Try different possible field names for price
                        for field in ["last", "ltp", "last_price", "close", "lasttradeprice"]:
                            if field in first_item:
                                price = first_item[field]
                                break
            
            if price is not None:
                logging.info(f"WORKING: {breeze_symbol} -> Price: {price}")
                results.append(
                    f"{nse_symbol} -> {breeze_symbol}: WORKING (Price: {price})"
                )
            else:
                error = (
                    quote.get("Error", 
                    quote.get("error", 
                    quote.get("message", 
                    "Unknown error - check response structure")))
                    if isinstance(quote, dict)
                    else "Unknown error - not a dict"
                )
                logging.info(f"NOT WORKING: {breeze_symbol} -> {error}")
                results.append(
                    f"{nse_symbol} -> {breeze_symbol}: NOT WORKING ({error}) - Response: {str(quote)[:200]}"
                )

            # Sleep to avoid rate limiting
            time.sleep(1)

        except Exception as e:
            logging.error(f"Error testing {breeze_symbol}: {str(e)}")
            results.append(f"{nse_symbol} -> {breeze_symbol}: ERROR ({str(e)})")
            time.sleep(1)

    # Save results to file
    with open("symbol_test_results.txt", "w") as f:
        f.write("\n".join(results))

    logging.info(f"Testing complete. Results saved to symbol_test_results.txt")


if __name__ == "__main__":
    test_nifty50_symbols()

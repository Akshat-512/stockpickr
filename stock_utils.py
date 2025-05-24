"""
Stock symbol utilities for NSE and Breeze API integration
"""
import csv
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Dictionary to store NIFTY 50 symbols and their details
NIFTY_50_SYMBOLS = {
    'RELIANCE', 'TCS', 'HDFCBANK', 'ICICIBANK', 'HINDUNILVR', 'INFY', 'ITC', 'SBIN', 'BHARTIARTL',
    'KOTAKBANK', 'LT', 'HCLTECH', 'ASIANPAINT', 'AXISBANK', 'TITAN', 'BAJFINANCE', 'MARUTI', 'ULTRACEMCO',
    'TATASTEEL', 'NTPC', 'POWERGRID', 'NESTLEIND', 'BAJAJFINSV', 'SUNPHARMA', 'ADANIPORTS', 'TECHM', 'JSWSTEEL',
    'HDFCLIFE', 'DRREDDY', 'BRITANNIA', 'HINDALCO', 'DIVISLAB', 'GRASIM', 'TATACONSUM', 'BAJAJ-AUTO', 'UPL',
    'COALINDIA', 'CIPLA', 'ONGC', 'SBILIFE', 'M&M', 'TATAMOTORS', 'APOLLOHOSP', 'ADANIENT', 'WIPRO', 'HDFC',
    'INDUSINDBK', 'EICHERMOT', 'BAJAJHLDNG', 'HEROMOTOCO'
}

class StockMapper:
    _instance = None
    _initialized = False
    
    def __new__(cls, master_file_path='NSEScripMaster.txt'):
        if cls._instance is None:
            cls._instance = super(StockMapper, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, master_file_path='NSEScripMaster.txt'):
        """
        Initialize the stock mapper with the master file
        
        Args:
            master_file_path (str): Path to the master file containing stock information
        """
        if not self._initialized:
            self.master_file = Path(master_file_path)
            self.symbol_map = {}  # Maps NSE symbol to Breeze symbol
            self.company_map = {}  # Maps company name to NSE symbol
            self._load_master_file()
            StockMapper._initialized = True
    
    def _load_master_file(self):
        """Load and parse the master file"""
        if not self.master_file.exists():
            logging.error(f"Master file not found: {self.master_file}")
            return
        
        try:
            with open(self.master_file, 'r', encoding='utf-8') as f:
                # Read header
                header = next(csv.reader([next(f).strip()]))
                
                # Find column indices
                short_name_idx = header.index('"ShortName"') if '"ShortName"' in header else 1
                series_idx = header.index('"Series"') if '"Series"' in header else 2
                name_idx = header.index('"CompanyName"') if '"CompanyName"' in header else 3
                
                # The ExchangeCode is the last column in the file
                exchange_code_idx = -1
                
                # Read data
                for line in f:
                    try:
                        # Clean and split the CSV line
                        row = [field.strip('\" ') for field in next(csv.reader([line.strip()]))]
                        
                        if len(row) <= max(short_name_idx, series_idx, name_idx, exchange_code_idx):
                            continue
                            
                        short_name = row[short_name_idx]  # This is the Breeze code
                        series = row[series_idx]
                        company_name = row[name_idx].upper()
                        exchange_code = row[exchange_code_idx]  # This is the NSE symbol
                        
                        # Only include equity stocks
                        if series == 'EQ':
                            # Store symbol mapping (NSE symbol to Breeze code)
                            self.symbol_map[exchange_code] = short_name
                            
                            # Store company name to NSE symbol mapping
                            self.company_map[company_name] = exchange_code
                            
                    except Exception as e:
                        logging.warning(f"Error parsing line: {line.strip()}. Error: {e}")
                        continue
                        
            logging.info(f"Loaded {len(self.symbol_map)} symbols from master file")
            
        except Exception as e:
            logging.error(f"Error loading master file: {e}")
    
    def get_breeze_symbol(self, nse_symbol):
        """
        Get Breeze symbol for the given NSE symbol
        
        Args:
            nse_symbol (str): NSE symbol
            
        Returns:
            str: Breeze symbol if found, else None
        """
        return self.symbol_map.get(nse_symbol)
    
    def get_nse_symbol(self, company_name):
        """
        Get NSE symbol for the given company name
        
        Args:
            company_name (str): Company name
            
        Returns:
            str: NSE symbol if found, else None
        """
        return self.company_map.get(company_name.upper())
    
    def get_nifty50_symbols(self):
        """
        Get list of NIFTY 50 symbols that exist in the master file
        
        Returns:
            list: List of NIFTY 50 symbols
        """
        return [sym for sym in NIFTY_50_SYMBOLS if sym in self.symbol_map]
    
    def is_valid_symbol(self, symbol):
        """
        Check if the symbol exists in the master file
        
        Args:
            symbol (str): Stock symbol to check
            
        Returns:
            bool: True if symbol exists, False otherwise
        """
        return symbol in self.symbol_map

# Create a global instance for easy import
# This will be a singleton instance that's reused throughout the application
stock_mapper = StockMapper()

# Example usage
if __name__ == "__main__":
    # Initialize the stock mapper
    mapper = StockMapper()
    
    # Example: Get Breeze symbol for NSE symbol
    nse_symbol = "RELIANCE"
    breeze_symbol = mapper.get_breeze_symbol(nse_symbol)
    print(f"NSE: {nse_symbol} -> Breeze: {breeze_symbol}")
    
    # Example: Get NIFTY 50 symbols
    nifty50 = mapper.get_nifty50_symbols()
    print(f"\nFound {len(nifty50)} NIFTY 50 symbols:")
    for i, sym in enumerate(sorted(nifty50), 1):
        print(f"{i}. {sym}")
    
    # Example: Check if a symbol is valid
    test_symbol = "RELIANCE"
    print(f"\nIs {test_symbol} valid? {mapper.is_valid_symbol(test_symbol)}")

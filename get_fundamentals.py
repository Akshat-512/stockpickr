import pandas as pd
from Fundamentals import Tickertape

# Initialize MoneyControl module
tt = Tickertape()

# List of top 5 NIFTY companies (hardcoded)
companies = ["RELIANCE", "HDFCBANK", "INFY", "ICICIBANK", "HDFC"]

# Fetch ratios for each company
data = {}
for company in companies:
    try:
        # Get ticker data to find the slug
        _, raw_data = tt.get_ticker(company)
        if raw_data and isinstance(raw_data, list) and len(raw_data) > 0 and 'slug' in raw_data[0]:
            slug_url = raw_data[0].get('slug')
            print(f"Fetching ratios for {company} using slug: {slug_url}")
            # Fetch key ratios using the slug
            ratios_df = tt.get_key_ratios(slug_url) # tt.get_key_ratios returns a DataFrame

            if isinstance(ratios_df, pd.DataFrame) and not ratios_df.empty:
                # The DataFrame has metric names as index and values in a single column (e.g., column '0').
                # We extract this column as a Pandas Series.
                series_from_df_column = ratios_df.iloc[:, 0]
                
                # Define a helper function to unwrap single-element lists/tuples
                def unwrap_value(val):
                    if isinstance(val, (list, tuple)) and len(val) == 1:
                        return val[0]
                    # Add more specific unwrapping if values can be numpy arrays like np.array([value])
                    # For example, if isinstance(val, np.ndarray) and val.size == 1:
                    #     return val.item() # or val[0]
                    return val
                
                # Apply the unwrapping function to each element in the Series
                data[company] = series_from_df_column.apply(unwrap_value) 
            elif isinstance(ratios_df, pd.DataFrame) and ratios_df.empty:
                print(f"Warning: Received an empty DataFrame for {company} ratios.")
                data[company] = pd.Series(dtype='object')
            else:
                print(f"Warning: Expected a DataFrame for ratios from tt.get_key_ratios for {company}, but got {type(ratios_df)}. Storing empty Series. Data: {ratios_df}")
                data[company] = pd.Series(dtype='object') # Store an empty Series

        else:
            print(f"Could not find slug for {company}. Raw data: {raw_data}")
            data[company] = None
    except Exception as e:
        print(f"Error fetching data for {company}: {e}")
        data[company] = None

# Save the data to a CSV file
if data:
    df = pd.DataFrame.from_dict(data, orient="index")
    df.index.name = "symbol"  # Name the index column
    df.to_csv("fundamentals_data/top_5_nifty_ratios.csv", index=True)
    print("Data saved to 'fundamentals_data/top_5_nifty_ratios.csv'.")
else:
    print("No data fetched.")

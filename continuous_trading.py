#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Continuous Trader - Runs the trading strategy in a loop during market hours
Specifically optimized for macOS
"""

import sys
import os
import time
import datetime
import logging
import signal

# Add the trader directory to the path if needed
# sys.path.append('/path/to/trader')

# Import your existing trader module
import trader

# Flags for testing strategy execution off-hours
RUN_STRATEGY_OFF_HOURS_FOR_TESTING = False  # Set to False for normal operation
TEST_MODE_STRATEGY_INTERVAL_SECONDS = 300  # Run strategy every 5 minutes in test mode
TEST_MODE_LOOP_SLEEP_SECONDS = 30  # Main loop sleeps for 30 seconds in test mode
NORMAL_MODE_STRATEGY_INTERVAL_SECONDS = (
    1800  # Run strategy every 30 minutes in normal mode
)
NORMAL_MODE_LOOP_SLEEP_SECONDS = 60  # Main loop sleeps for 60 seconds in normal mode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("continuous_trader.log"),
        logging.StreamHandler(sys.stdout),
    ],
)


def refresh_session():
    """Refresh the API session if needed"""
    try:
        # Test the current session by making a simple API call
        test_result = trader.breeze.get_customer_details(
            api_session=trader.SESSION_TOKEN
        )

        if not test_result or "Success" not in test_result:
            logging.warning("Session appears to be invalid, attempting to refresh")

            # Re-initialize API
            if trader.initialize_api():
                logging.info("Session refreshed successfully")
                return True
            else:
                logging.error("Failed to refresh session")
                return False

        return True  # Session is valid

    except Exception as e:
        logging.error(f"Error checking/refreshing session: {e}")
        return False


def is_market_day():
    """Check if today is a trading day (Monday to Friday)"""
    current_day = datetime.datetime.now().strftime("%A")
    trading_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    return current_day in trading_days


def is_during_market_hours():
    """Check if current time is during market hours (9:15 AM to 3:30 PM)"""
    now = datetime.datetime.now().time()
    market_open = datetime.time(9, 15)
    market_close = datetime.time(15, 30)
    return market_open <= now <= market_close


def is_pre_market():
    """Check if current time is just before market open (9:00 AM to 9:15 AM)"""
    now = datetime.datetime.now().time()
    pre_open_start = datetime.time(9, 0)
    market_open = datetime.time(9, 15)
    return pre_open_start <= now < market_open


def is_post_market():
    """Check if current time is just after market close (3:30 PM to 3:45 PM)"""
    now = datetime.datetime.now().time()
    market_close = datetime.time(15, 30)
    post_close_end = datetime.time(15, 45)
    return market_close < now <= post_close_end


def run_continuously():
    """Run the trading strategy continuously"""
    print("=== STARTING CONTINUOUS TRADER ===")
    logging.info("Starting continuous trader")

    # Initialize API connection only once
    if not trader.initialize_api():
        logging.error("Failed to initialize API. Exiting.")
        return

    # Load any existing positions
    trader.load_positions()
    trader.load_today_trades()

    day_started = False
    day_ended = False
    last_run_time = None

    try:
        while True:
            now = datetime.datetime.now()
            current_day = now.strftime("%Y-%m-%d")
            # print(f"\n=== CONTINUOUS TRADER RUN AT {now.strftime('%H:%M:%S')} ===")
            # print(f"Current day: {current_day}")
            # print(f"Market day: {is_market_day()}")
            # print(f"Market hours: {is_during_market_hours()}")
            # print(f"Pre-market: {is_pre_market()}")
            # print(f"Post-market: {is_post_market()}")
            # print(f"Last run time: {last_run_time}")
            # print(
            #     f"Time since last run: {(now - last_run_time).seconds if last_run_time else 'N/A'}"
            # )
            # print(f"Strategy interval: {NORMAL_MODE_STRATEGY_INTERVAL_SECONDS} seconds")

            # Check if it's a new day (applies to both modes)
            if last_run_time and last_run_time.strftime("%Y-%m-%d") != current_day:
                day_started = False  # Reset for normal mode logic
                day_ended = False  # Reset for normal mode logic
                trader.today_trades = []  # Reset today's trades
                logging.info(f"New day ({current_day}). Resetting daily states.")

            if RUN_STRATEGY_OFF_HOURS_FOR_TESTING:
                logging.info("CONTINUOUS TRADER (Test Mode): Active.")
                if not refresh_session():  # Ensure session is valid
                    logging.error(
                        "CONTINUOUS TRADER (Test Mode): Unable to maintain valid session. Waiting."
                    )
                    time.sleep(300)  # Wait 5 minutes before trying again
                    continue

                # Run the strategy periodically in test mode
                if (
                    last_run_time is None
                    or (now - last_run_time).seconds
                    >= TEST_MODE_STRATEGY_INTERVAL_SECONDS
                ):
                    logging.info(
                        f"CONTINUOUS TRADER (Test Mode): Running trader.run_strategy() (Interval: {TEST_MODE_STRATEGY_INTERVAL_SECONDS}s)"
                    )
                    trader.run_strategy()
                    last_run_time = now
            else:  # Normal Operation Mode (RUN_STRATEGY_OFF_HOURS_FOR_TESTING is False)
                logging.info("CONTINUOUS TRADER (Normal Mode): Active.")
                if is_market_day():
                    if not refresh_session():  # Ensure session is valid
                        logging.error(
                            "CONTINUOUS TRADER (Normal Mode): Unable to maintain valid session. Waiting."
                        )
                        time.sleep(300)  # Wait 5 minutes before trying again
                        continue

                    # Pre-market preparation
                    if is_pre_market() and not day_started:
                        logging.info(
                            "CONTINUOUS TRADER (Normal Mode): Pre-market preparation"
                        )
                        day_started = True
                        trader.load_positions()
                        trader.load_today_trades()
                        # Potentially run strategy once: trader.run_strategy()
                        # last_run_time = now

                    # Regular market hours operation
                    elif is_during_market_hours():
                        if (
                            last_run_time is None
                            or (now - last_run_time).seconds
                            >= NORMAL_MODE_STRATEGY_INTERVAL_SECONDS
                        ):
                            logging.info(
                                f"CONTINUOUS TRADER (Normal Mode): Running trader.run_strategy() (Interval: {NORMAL_MODE_STRATEGY_INTERVAL_SECONDS}s)"
                            )
                            trader.run_strategy()
                            last_run_time = now

                    # Post-market operations
                    elif is_post_market() and not day_ended:
                        logging.info(
                            "CONTINUOUS TRADER (Normal Mode): Running end-of-day procedures"
                        )
                        trader.generate_daily_report()
                        trader.save_trades()
                        day_ended = True

            # Determine sleep duration based on mode
            current_loop_sleep = (
                TEST_MODE_LOOP_SLEEP_SECONDS
                if RUN_STRATEGY_OFF_HOURS_FOR_TESTING
                else NORMAL_MODE_LOOP_SLEEP_SECONDS
            )
            logging.info(
                f"CONTINUOUS TRADER: Main loop sleeping for {current_loop_sleep} seconds."
            )
            time.sleep(current_loop_sleep)

    except KeyboardInterrupt:
        logging.info("Continuous trader interrupted by user")
    except Exception as e:
        logging.error(f"Unhandled error in continuous trader: {e}")
        # Send error notification
        trader.send_email(
            "Trading Strategy Error", f"Trading strategy encountered an error: {str(e)}"
        )
    finally:
        logging.info("Continuous trader stopped")


# Graceful shutdown handler
def signal_handler(sig, frame):
    logging.info("Received shutdown signal, exiting gracefully...")
    sys.exit(0)


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    run_continuously()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Continuous Trading System

Runs automated trading strategies during market hours with session management,
error handling, and reporting capabilities.
"""

import sys
import os
import time
import datetime
import logging
import signal
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

import trader


# Configuration
class Config:
    """Global configuration settings."""

    RUN_STRATEGY_OFF_HOURS = False  # Set to True for testing outside market hours
    TEST_MODE_STRATEGY_INTERVAL = 300  # 5 minutes
    TEST_MODE_LOOP_SLEEP = 30  # 30 seconds
    NORMAL_MODE_STRATEGY_INTERVAL = 1800  # 30 minutes
    NORMAL_MODE_LOOP_SLEEP = 60  # 60 seconds

    # Market hours (IST)
    MARKET_OPEN = datetime.time(9, 15)  # 9:15 AM
    MARKET_CLOSE = datetime.time(15, 30)  # 3:30 PM
    PRE_MARKET_OPEN = datetime.time(9, 0)  # 9:00 AM
    POST_MARKET_CLOSE = datetime.time(15, 45)  # 3:45 PM

    # Report generation
    REPORT_GEN_HOURS = {0, 12}  # Generate reports at midnight and noon
    REPORT_GEN_WINDOW = 2  # Minutes window for report generation
    REPORTS_DIR = "reports"


@dataclass
class TradingSession:
    """Manages the trading session state."""

    day_started: bool = False
    day_ended: bool = False
    last_run_time: Optional[datetime.datetime] = None
    positions: Dict[str, Any] = field(default_factory=dict)
    today_trades: list = field(default_factory=list)

    def reset_for_new_day(self):
        """Reset session state for a new trading day."""
        self.day_started = False
        self.day_ended = False
        self.today_trades = []
        self.positions = {}
        logging.info("Trading session reset for new day")


def setup_logging() -> None:
    """Configure logging to both file and console."""
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "continuous_trader.log")

    # Clear existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Add handlers
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.info("=" * 60)
    logging.info("STARTING CONTINUOUS TRADING SYSTEM")
    logging.info(f"Log file: {os.path.abspath(log_file)}")
    logging.info(f"Python: {sys.version.split()[0]} on {sys.platform}")
    logging.info("=" * 60)


# Initialize logging
setup_logging()


def refresh_session() -> bool:
    """Refresh the API session if needed."""
    try:
        test_result = trader.breeze.get_customer_details(
            api_session=trader.SESSION_TOKEN
        )
        if test_result and "Success" in test_result:
            return True

        logging.warning("Session invalid, attempting to refresh...")
        if trader.initialize_api():
            logging.info("Session refreshed successfully")
            return True

        logging.error("Failed to refresh session")
        return False

    except Exception as e:
        logging.error(f"Error refreshing session: {e}", exc_info=True)
        return False


def is_market_day() -> bool:
    """Check if today is a trading day (Monday to Friday)."""
    return datetime.datetime.now().weekday() < 5  # 0=Monday, 6=Sunday


def is_during_market_hours() -> bool:
    """Check if current time is during market hours."""
    now = datetime.datetime.now().time()
    return Config.MARKET_OPEN <= now <= Config.MARKET_CLOSE


def is_pre_market() -> bool:
    """Check if current time is during pre-market hours."""
    now = datetime.datetime.now().time()
    return Config.PRE_MARKET_OPEN <= now < Config.MARKET_OPEN


def is_post_market() -> bool:
    """Check if current time is during post-market hours."""
    now = datetime.datetime.now().time()
    return Config.MARKET_CLOSE < now <= Config.POST_MARKET_CLOSE


def check_and_generate_report() -> bool:
    """
    Check if today's report exists and generate it if missing.

    Returns:
        bool: True if report was generated or already exists, False on error
    """
    try:
        os.makedirs(Config.REPORTS_DIR, exist_ok=True)
        today = datetime.date.today()
        report_file = os.path.join(
            Config.REPORTS_DIR, f"report_{today.strftime('%Y%m%d')}.txt"
        )

        if not os.path.exists(report_file):
            logging.info("Today's report not found. Generating daily report...")
            trader.generate_daily_report()

            # Verify report was created
            if os.path.exists(report_file):
                logging.info(f"Successfully generated report: {report_file}")
                return True
            else:
                logging.error(f"Failed to generate report: {report_file}")
                return False

        logging.debug("Today's report already exists")
        return True

    except Exception as e:
        logging.error(f"Error in check_and_generate_report: {e}", exc_info=True)
        return False


def generate_daily_report() -> None:
    """Generate and save daily trading report if it doesn't exist."""
    if not check_and_generate_report():
        logging.warning("Failed to ensure daily report exists")


def run_trading_cycle(session: TradingSession) -> None:
    """Execute one cycle of the trading strategy."""
    now = datetime.datetime.now()

    # Check for new day
    if session.last_run_time and session.last_run_time.date() != now.date():
        session.reset_for_new_day()
        generate_daily_report()

    # Log market status
    logging.info(
        f"Market - Day: {is_market_day()}, "
        f"Hours: {is_during_market_hours()}, "
        f"Pre: {is_pre_market()}, "
        f"Post: {is_post_market()}"
    )

    # Generate reports at configured times
    if now.hour in Config.REPORT_GEN_HOURS and now.minute < Config.REPORT_GEN_WINDOW:
        generate_daily_report()

    # Run strategy based on market conditions
    if Config.RUN_STRATEGY_OFF_HOURS:
        run_test_mode(session, now)
    else:
        run_normal_mode(session, now)


def run_test_mode(session: TradingSession, now: datetime.datetime) -> None:
    """Run trading strategy in test mode."""
    logging.info("Test Mode: Active")

    if not refresh_session():
        logging.error("Test Mode: Session refresh failed")
        time.sleep(300)
        return

    if (
        session.last_run_time is None
        or (now - session.last_run_time).seconds >= Config.TEST_MODE_STRATEGY_INTERVAL
    ):
        logging.info(
            f"Test Mode: Running strategy (Interval: {Config.TEST_MODE_STRATEGY_INTERVAL}s)"
        )
        trader.run_strategy()
        session.last_run_time = now


def run_normal_mode(session: TradingSession, now: datetime.datetime) -> None:
    """Run trading strategy in normal market mode."""
    if not is_market_day():
        return

    if not refresh_session():
        logging.error("Normal Mode: Session refresh failed")
        time.sleep(300)
        return

    # Pre-market
    if is_pre_market() and not session.day_started:
        logging.info("Normal Mode: Pre-market preparation")
        session.day_started = True
        trader.load_positions()
        trader.load_today_trades()

    # Market hours
    elif is_during_market_hours():
        if (
            session.last_run_time is None
            or (now - session.last_run_time).seconds
            >= Config.NORMAL_MODE_STRATEGY_INTERVAL
        ):
            logging.info(
                f"Normal Mode: Running strategy (Interval: {Config.NORMAL_MODE_STRATEGY_INTERVAL}s)"
            )
            trader.run_strategy()
            session.last_run_time = now

    # Post-market
    elif is_post_market() and not session.day_ended:
        logging.info("Normal Mode: End-of-day procedures")
        generate_daily_report()
        trader.save_trades()
        session.day_ended = True
    else:
        generate_daily_report()
        logging.info("Normal Mode: Market closed")


def get_sleep_duration() -> int:
    """Determine how long to sleep based on current mode and market status."""
    if Config.RUN_STRATEGY_OFF_HOURS:
        return Config.TEST_MODE_LOOP_SLEEP

    if not is_market_day() or not any(
        [is_during_market_hours(), is_pre_market(), is_post_market()]
    ):
        logging.info("Market closed. Next check in 1 hour.")
        return 3600  # 1 hour

    return Config.NORMAL_MODE_LOOP_SLEEP


def run_continuously() -> None:
    """Run the trading strategy continuously."""
    logging.info("Starting continuous trading system")

    if not trader.initialize_api():
        logging.error("Failed to initialize API. Exiting.")
        return

    session = TradingSession()

    try:
        while True:
            run_trading_cycle(session)
            sleep_duration = get_sleep_duration()
            logging.info(f"Sleeping for {sleep_duration} seconds...")
            time.sleep(sleep_duration)

    except KeyboardInterrupt:
        logging.info("Trading system stopped by user")
    except Exception as e:
        logging.error(f"Fatal error in trading system: {e}", exc_info=True)
        trader.send_email(
            "Trading System Error",
            f"A fatal error occurred: {str(e)}\n\nCheck logs for details.",
        )
    finally:
        logging.info("Trading system shutdown complete")


def signal_handler(sig: int, frame) -> None:
    """Handle shutdown signals gracefully."""
    logging.info("Shutdown signal received. Exiting...")
    sys.exit(0)


if __name__ == "__main__":
    try:
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Log system info
        logging.info(f"Working directory: {os.getcwd()}")
        logging.info(f"Python version: {sys.version}")
        logging.info(f"Mode: {'TEST' if Config.RUN_STRATEGY_OFF_HOURS else 'NORMAL'}")

        # Start trading
        run_continuously()

    except Exception as e:
        logging.critical(f"Critical error: {e}", exc_info=True)
        sys.exit(1)

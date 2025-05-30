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
from session_generator import ManualBreezeAuth
import trader
from trader import TradingSystem


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
    REPORT_START_TIME = datetime.time(16, 0)
    REPORT_GEN_WINDOW = 2  # Minutes window for report generation
    REPORTS_DIR = "reports"


@dataclass
class TradingSession:
    """Manages the trading session state."""

    day_started: bool = False
    report_generated_today: bool = False
    day_ended: bool = False
    last_run_time: Optional[datetime.datetime] = None
    positions: Dict[str, Any] = field(default_factory=dict)
    today_trades: list = field(default_factory=list)
    session_auth: Optional[ManualBreezeAuth] = None

    def reset_for_new_day(self):
        """Reset session state for a new trading day."""
        self.day_started = False
        self.day_ended = False
        self.report_generated_today = False
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


# Global variable to track if we're currently in the process of getting a session
SESSION_REFRESH_IN_PROGRESS = False
LAST_SESSION_REFRESH_ATTEMPT = 0
SESSION_REFRESH_COOLDOWN = 60  # 1 minute cooldown between refresh attempts


def ensure_valid_session() -> bool:
    """Ensure we have a valid session token, automatically refresh if needed."""
    session_auth = None
    try:
        # Create session auth instance
        session_auth = ManualBreezeAuth()

        # Check for existing valid session first
        existing_token, hours_left = session_auth.check_existing_session()
        if existing_token and hours_left > 0.5:  # More than 30 minutes left
            logging.info(
                f"✅ Using existing valid session (expires in {hours_left:.1f} hours)"
            )
            return True

        logging.info("⚠️  No valid session found, attempting to generate new one...")

        # Try to generate new session
        session_token = session_auth.manual_session_generation()

        if not session_token:
            logging.error("❌ Failed to get valid session token")
            return False

        logging.info(f"✅ New session generated successfully")

        # Update config file with new session token
        try:
            config = configparser.ConfigParser()
            config.read("config.ini")
            if not config.has_section("APICredentials"):
                config.add_section("APICredentials")
            config.set("APICredentials", "session_token", session_token)
            with open("config.ini", "w") as f:
                config.write(f)
            logging.info("✅ Updated config file with new session token")
        except Exception as e:
            logging.error(f"⚠️  Failed to update config file: {e}")
            # Don't fail the whole operation if config update fails

        return True

    except Exception as e:
        logging.error(f"❌ Error ensuring valid session: {e}")
        return False

    finally:
        # Always release the lock if we have it
        if session_auth:
            session_auth.release_lock()


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


def check_and_generate_report(session, trading_system: TradingSystem) -> bool:
    now = datetime.datetime.now()
    if not (is_market_day() and now.time() >= Config.REPORT_START_TIME):
        return True
    if session.report_generated_today:
        return True
    today_str = now.strftime("%Y%m%d")
    report_file = os.path.join(Config.REPORTS_DIR, f"report_{today_str}.txt")
    if os.path.exists(report_file):
        session.report_generated_today = True
        return True
    try:
        trading_system.generate_daily_report()
        session.report_generated_today = True
        trading_system.portfolio.today_trades = []
        return True
    except Exception as e:
        logging.error(f"Error generating report: {e}")
        return False


def run_trading_cycle(session: TradingSession) -> None:
    # initialize trading system from trader.py

    trading_system = TradingSystem()
    if not trading_system.initialize():
        logging.error("❌ Failed to initialize trading system. Exiting.")
        return

    """Execute one cycle of the trading strategy."""
    now = datetime.datetime.now()

    # Check for new day
    if session.last_run_time and session.last_run_time.date() != now.date():
        session.reset_for_new_day()

    # Market status
    logging.info(
        f"Market - Day: {is_market_day()}, "
        f"Hours: {is_during_market_hours()}, "
        f"Pre: {is_pre_market()}, "
        f"Post: {is_post_market()}"
    )

    # Generate report
    check_and_generate_report(session, trading_system)

    # Run strategy based on market conditions
    if Config.RUN_STRATEGY_OFF_HOURS:
        run_test_mode(session, trading_system, now)
    else:
        run_normal_mode(session, trading_system, now)


def run_test_mode(
    session: TradingSession, trading_system: TradingSystem, now: datetime.datetime
) -> None:
    """Run trading strategy in test mode."""
    logging.info("Test Mode: Active")

    if (
        session.last_run_time is None
        or (now - session.last_run_time).seconds >= Config.TEST_MODE_STRATEGY_INTERVAL
    ):
        logging.info(
            f"Test Mode: Running strategy (Interval: {Config.TEST_MODE_STRATEGY_INTERVAL}s)"
        )
        trading_system.run_strategy()
        session.last_run_time = now


def run_normal_mode(
    session: TradingSession, trading_system: TradingSystem, now: datetime.datetime
) -> None:
    """Run trading strategy in normal market mode."""
    if not is_market_day():
        return

    # Pre-market
    if is_pre_market() and not session.day_started:
        logging.info("Normal Mode: Pre-market preparation")
        session.day_started = True
        trading_system.portfolio.load_positions()
        trading_system.portfolio.load_today_trades()

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
            trading_system.run_strategy()
            session.last_run_time = now

    # Post-market
    elif is_post_market() and not session.day_ended:
        logging.info("Normal Mode: End-of-day procedures")
        session.day_ended = True
    else:
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

    if not ensure_valid_session():
        logging.error("❌ Failed to get valid session. Exiting.")
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

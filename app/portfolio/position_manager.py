#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Position Management Module - Complete Version
Handles position tracking, entry, exit, and risk management with all original functionality
"""

import datetime
import json
import os
import logging
import time
import pandas as pd
from typing import Dict, List, Optional, Tuple


class PositionManager:
    """Manages trading positions and risk - Complete Implementation"""

    def __init__(self, config, api_client):
        self.config = config
        self.api = api_client
        self.positions = {}
        self.today_trades = []

        # Configuration
        self.INITIAL_CAPITAL = config.getfloat("Basic", "capital", fallback=5000)
        self.RISK_PER_TRADE = config.getfloat("Strategy", "risk_percent", fallback=2.0)
        self.MAX_POSITIONS = config.getint("Strategy", "max_positions", fallback=2)
        self.PAPER_TRADING_MODE = config.getboolean(
            "Strategy", "paper_trading_mode", fallback=True
        )
        self.MAX_WAIT_TIME_ORDER = 60

        # Load existing positions
        self.load_positions()
        self.load_today_trades()

    def calculate_position_size(
        self, current_price: float, stop_loss: float, stock_code: str
    ) -> Tuple[int, float]:
        """Calculate position size based on risk parameters"""
        try:
            # Risk amount in rupees
            risk_amount = self.INITIAL_CAPITAL * (self.RISK_PER_TRADE / 100)

            # Risk per share
            risk_per_share = current_price - stop_loss

            if risk_per_share <= 0:
                logging.warning(
                    f"Invalid stop loss for {stock_code} - must be below current price"
                )
                return 0, 0

            # Calculate quantity based on risk
            quantity = int(risk_amount / risk_per_share)
            quantity = max(1, quantity)  # Minimum 1 share

            # Calculate total position cost
            total_cost = quantity * current_price

            # Check if position is too large (> 50% of capital)
            max_position = self.INITIAL_CAPITAL * 0.5
            if total_cost > max_position:
                # Adjust quantity to fit max position size
                quantity = int(max_position / current_price)
                total_cost = quantity * current_price

            logging.info(
                f"Position size for {stock_code}: Price={current_price}, Stop={stop_loss}, Quantity={quantity}, Cost={total_cost}"
            )
            return quantity, total_cost

        except Exception as e:
            logging.error(f"Error calculating position size for {stock_code}: {e}")
            return 0, 0

    def enter_position(self, opportunity: Dict) -> bool:
        """Enter a new position - Complete implementation with all original functionality"""
        stock_code = opportunity["stock_code"]
        exchange_code = opportunity["exchange_code"]

        # Validate stock symbol
        if stock_code.startswith(("NIFTY", "SENSEX", "BANKNIFTY")):
            logging.warning(f"Cannot enter position in index: {stock_code}")
            return False

        # Enhanced position check to prevent duplicate entries
        if stock_code in self.positions:
            logging.warning(
                f"Position already exists for {stock_code}, skipping new entry"
            )
            return False

        # Check maximum positions
        if len(self.positions) >= self.MAX_POSITIONS:
            logging.warning(f"At maximum positions ({self.MAX_POSITIONS})")
            return False

        # Paper trading mode
        if self.PAPER_TRADING_MODE:
            logging.info(f"PAPER TRADING MODE: Would enter position in {stock_code}")

            # Still create position entry for paper trading tracking
            current_price = opportunity["current_price"]
            stop_loss = opportunity["stop_loss"]
            quantity, total_cost = self.calculate_position_size(
                current_price, stop_loss, stock_code
            )

            if quantity > 0:
                self.positions[stock_code] = {
                    "exchange": exchange_code,
                    "quantity": quantity,
                    "entry_price": current_price,
                    "entry_time": datetime.datetime.now().isoformat(),
                    "stop_loss": stop_loss,
                    "position_value": current_price * quantity,
                    "entry_reason": opportunity.get(
                        "signal_reason", "Technical signal"
                    ),
                    "relative_strength": opportunity.get("relative_strength", 1.0),
                    "paper_trading": True,
                }
                self.save_positions()

                # Send notification for paper trading too
                self._send_entry_notification(
                    stock_code,
                    {
                        "entry_price": current_price,
                        "quantity": quantity,
                        "stop_loss": stop_loss,
                        "position_value": current_price * quantity,
                    },
                )

            return True

        try:
            # Get current price
            current_price = self.api.get_current_price(stock_code, exchange_code)
            if current_price is None:
                logging.error(f"Could not get current price for {stock_code}")
                return False

            # Get historical data with indicators
            hist_data = self.api.get_historical_data(stock_code, exchange_code)
            if hist_data is None:
                logging.error(f"Could not get historical data for {stock_code}")
                return False

            # Calculate indicators
            with_indicators = self.api.calculate_indicators(hist_data)
            if with_indicators is None:
                logging.error(f"Could not calculate indicators for {stock_code}")
                return False

            # Get latest ATR for stop loss calculation
            latest_atr = with_indicators["atr"].iloc[-1]

            # Calculate stop loss price (2 ATR below current price)
            stop_loss_price = current_price - (2 * latest_atr)
            stop_loss_price = round(stop_loss_price, 1)  # Round to 1 decimal place

            # Calculate position size
            quantity, total_cost = self.calculate_position_size(
                current_price, stop_loss_price, stock_code
            )

            if quantity <= 0:
                logging.warning(
                    f"Calculated quantity is zero or negative for {stock_code}"
                )
                return False

            logging.warning(
                f"Entering position for {stock_code} at {current_price:.2f}, stop loss: {stop_loss_price:.2f}, quantity: {quantity}"
            )

            # Place buy order
            order_id = self.api.place_order(stock_code, exchange_code, "buy", quantity)

            if not order_id:
                logging.error(f"Failed to place buy order for {stock_code}")
                return False

            logging.warning(f"Buy order placed for {stock_code}, order ID: {order_id}")

            # Store position immediately (before waiting for execution)
            self.positions[stock_code] = {
                "exchange": exchange_code,
                "quantity": quantity,
                "entry_price": current_price,
                "entry_time": datetime.datetime.now().isoformat(),
                "stop_loss": stop_loss_price,
                "position_value": current_price * quantity,
                "order_id": order_id,
                "entry_reason": opportunity.get("signal_reason", "Technical signal"),
                "relative_strength": opportunity.get("relative_strength", 1.0),
            }
            self.save_positions()

            # Wait for execution
            success, executed_price, filled_qty, order_status_history = (
                self.wait_for_order_execution(
                    order_id, stock_code, exchange_code, current_price
                )
            )

            if not success or executed_price == 0:
                # Order failed - clean up
                logging.error(f"Order execution failed for {stock_code}")
                if stock_code in self.positions:
                    del self.positions[stock_code]
                    self.save_positions()
                return False

            # Update position with executed price
            if stock_code in self.positions:
                self.positions[stock_code]["entry_price"] = executed_price
                self.positions[stock_code]["position_value"] = executed_price * quantity
                self.save_positions()

            # Store entry context for better exit decisions
            self.store_entry_context(
                stock_code, opportunity.get("signal_reason", "Technical entry signal")
            )

            # Send email notification
            self._send_entry_notification(
                stock_code,
                {
                    "entry_price": executed_price,
                    "quantity": quantity,
                    "stop_loss": stop_loss_price,
                    "position_value": executed_price * quantity,
                },
            )

            logging.warning(f"Position entered successfully: {stock_code}")
            return True

        except Exception as e:
            logging.error(f"Exception in enter_position for {stock_code}: {e}")
            # Clean up any partial position
            if stock_code in self.positions:
                del self.positions[stock_code]
                self.save_positions()
            return False

    def wait_for_order_execution(
        self, order_id: str, stock_code: str, exchange_code: str, current_price: float
    ) -> Tuple[bool, float, int, List]:
        """Wait for order execution and return execution details - Complete implementation"""
        start_time = time.time()
        order_status_history = []
        last_order_status = None
        wait_interval = 2

        while time.time() - start_time < self.MAX_WAIT_TIME_ORDER:
            try:
                # Get order status using the API client
                order_status = self.api.get_order_status(order_id, exchange_code)
                last_order_status = order_status

                # Validate response structure
                if not (
                    order_status
                    and isinstance(order_status.get("Success"), list)
                    and order_status["Success"]
                ):
                    logging.warning(
                        f"Invalid order response for {stock_code}: {order_status}"
                    )
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
                    logging.error(f"Error parsing order data for {stock_code}: {e}")
                    time.sleep(wait_interval)
                    continue

                logging.info(
                    f"Order {order_id} for {stock_code}: Status={status}, Filled={filled_qty}/{quantity}, Price={executed_price:.2f}"
                )

                # Check order status
                if status == "Executed":
                    logging.info(
                        f"Order executed for {stock_code} at price: {executed_price}"
                    )
                    return True, executed_price, filled_qty, order_status_history

                elif status in ["Cancelled", "Rejected", "Expired"]:
                    logging.warning(f"Order {order_id} {status} for {stock_code}")
                    return False, 0, 0, order_status_history

                # Order still pending - continue waiting
                time.sleep(wait_interval)

            except Exception as e:
                logging.error(f"Error checking order {order_id} for {stock_code}: {e}")
                time.sleep(wait_interval)

        # Timeout reached - log history for debugging
        logging.error(
            f"Order for {stock_code} did not execute within {self.MAX_WAIT_TIME_ORDER} seconds"
        )
        logging.error("Order status history:")
        for timestamp, status in order_status_history:
            logging.error(f"{timestamp}: {status}")

        # Try to cancel pending order
        if last_order_status:
            try:
                if (
                    last_order_status.get("Success")
                    and len(last_order_status["Success"]) > 0
                ):
                    last_status = last_order_status["Success"][0].get("status")
                    if last_status == "Pending":
                        cancel_response = self.api.cancel_order(order_id)
                        logging.info(
                            f"Attempted to cancel pending order for {stock_code}: {cancel_response}"
                        )
            except Exception as e:
                logging.error(f"Error cancelling order for {stock_code}: {e}")

        return False, 0, 0, order_status_history

    def store_entry_context(self, stock_code: str, signal_reason: str):
        """Store why we entered this position"""
        if stock_code in self.positions:
            self.positions[stock_code]["entry_reason"] = signal_reason
            self.positions[stock_code][
                "entry_date"
            ] = datetime.datetime.now().isoformat()

            # Set expected timeframe based on entry reason
            if (
                "momentum" in signal_reason.lower()
                or "volume surge" in signal_reason.lower()
            ):
                self.positions[stock_code]["expected_duration"] = "1-3_weeks"
            else:
                self.positions[stock_code]["expected_duration"] = "2-4_weeks"

            self.save_positions()

    def _send_entry_notification(self, stock_code: str, details: Dict):
        """Send entry notification email"""
        try:
            # Import the send_email function from the main trader module
            from trader import send_email

            email_subject = f"New Position: {stock_code}"
            email_body = f"""
ENTRY ALERT: {stock_code}

Details:
--------
Entry Price: ₹{details['entry_price']:.2f}
Quantity: {details['quantity']}
Position Value: ₹{details['position_value']:.2f}
Stop Loss: ₹{details['stop_loss']:.2f}
Entry Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This position represents {(details['position_value'] / self.INITIAL_CAPITAL) * 100:.1f}% of your trading capital.

Target: 10% monthly return
Expected holding: 2-4 weeks
Paper Trading: {"YES" if self.PAPER_TRADING_MODE else "NO"}
            """

            send_email(email_subject, email_body)

        except Exception as e:
            logging.error(f"Error sending entry notification for {stock_code}: {e}")

    def exit_position(self, stock_code: str, exit_reason: str = "Manual") -> bool:
        """Exit an existing position - Complete implementation"""
        if stock_code not in self.positions:
            logging.warning(f"No position found for {stock_code}")
            return False

        position = self.positions[stock_code]

        # Handle paper trading
        if self.PAPER_TRADING_MODE or position.get("paper_trading", False):
            logging.info(
                f"PAPER TRADING MODE: Would exit position in {stock_code} - {exit_reason}"
            )

            # Get current price for paper trading P&L calculation
            current_price = self.api.get_current_price(
                stock_code, position.get("exchange", "NSE")
            )
            if current_price:
                entry_price = position["entry_price"]
                quantity = position["quantity"]
                profit_loss = (current_price - entry_price) * quantity
                profit_loss_pct = ((current_price / entry_price) - 1) * 100

                # Record paper trade
                exit_time = datetime.datetime.now()
                trade = {
                    "stock_code": stock_code,
                    "exchange": position.get("exchange", "NSE"),
                    "entry_price": entry_price,
                    "exit_price": current_price,
                    "quantity": quantity,
                    "entry_time": position.get("entry_time"),
                    "exit_time": exit_time.isoformat(),
                    "profit_loss": profit_loss,
                    "profit_loss_percent": profit_loss_pct,
                    "exit_reason": exit_reason,
                    "holding_days": self._calculate_holding_days(
                        position.get("entry_time", "")
                    ),
                    "paper_trading": True,
                }

                self.today_trades.append(trade)

                # Remove position
                del self.positions[stock_code]
                self.save_positions()
                self.save_trades()

                # Send notification
                self._send_exit_notification(stock_code, trade)

                logging.warning(
                    f"Paper position exited: {stock_code} - P&L: ₹{profit_loss:.2f} ({profit_loss_pct:.2f}%)"
                )

            return True

        try:
            exchange_code = position["exchange"]
            quantity = position["quantity"]
            entry_price = position["entry_price"]
            entry_time = position["entry_time"]

            # Get current price
            current_price = self.api.get_current_price(stock_code, exchange_code)
            if current_price is None:
                logging.error(f"Could not get current price for {stock_code}")
                return False

            logging.warning(
                f"Exiting position: {stock_code} at ₹{current_price:.2f} - {exit_reason}"
            )

            # Place sell order
            order_id = self.api.place_order(stock_code, exchange_code, "sell", quantity)

            if not order_id:
                logging.error(f"Failed to place sell order for {stock_code}")
                return False

            logging.warning(f"Sell order placed for {stock_code}, order ID: {order_id}")

            # Wait for order execution with same logic as entry
            success, executed_price, filled_qty, order_status_history = (
                self.wait_for_order_execution(
                    order_id, stock_code, exchange_code, current_price
                )
            )

            if not success or executed_price == 0:
                logging.error(f"Sell order execution failed for {stock_code}")
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
                "exit_reason": exit_reason,
                "holding_days": self._calculate_holding_days(entry_time),
            }

            self.today_trades.append(trade)

            # Remove from positions
            del self.positions[stock_code]

            # Save positions and trades
            self.save_positions()
            self.save_trades()

            # Send email notification
            self._send_exit_notification(stock_code, trade)

            return True

        except Exception as e:
            logging.error(f"Exception in exit_position for {stock_code}: {e}")
            return False

    def _send_exit_notification(self, stock_code: str, trade: Dict):
        """Send exit notification email"""
        try:
            # Import the send_email function from the main trader module
            from trader import send_email

            pnl = trade["profit_loss"]
            pnl_pct = trade["profit_loss_percent"]

            email_subject = f"Position Closed: {stock_code}"
            email_body = f"""
EXIT ALERT: {stock_code}

Details:
--------
Entry Price: ₹{trade['entry_price']:.2f}
Exit Price: ₹{trade['exit_price']:.2f}
Quantity: {trade['quantity']}
P&L: ₹{pnl:.2f} ({pnl_pct:+.2f}%)
Exit Reason: {trade['exit_reason']}
Exit Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Days Held: {trade.get('holding_days', 0)}

Overall Result: {"PROFIT" if pnl > 0 else "LOSS"}
Paper Trading: {"YES" if trade.get('paper_trading', False) else "NO"}

Monthly Progress: {"On Track" if pnl_pct >= 0 else "Recovery Needed"}
            """

            send_email(email_subject, email_body)

        except Exception as e:
            logging.error(f"Error sending exit notification for {stock_code}: {e}")

    def _calculate_holding_days(self, entry_time_str: str) -> int:
        """Calculate number of days position was held"""
        try:
            entry_time = datetime.datetime.fromisoformat(entry_time_str)
            time_diff = datetime.datetime.now() - entry_time
            days = time_diff.days

            # Count same day as 1 if held > 6 hours
            if days == 0 and time_diff.total_seconds() / 3600 >= 6:
                days = 1

            return days
        except:
            return 1

    def check_exit_signals(self, market_condition: Dict) -> int:
        """Check all positions for exit signals"""
        positions_to_check = list(self.positions.items())
        exited_count = 0
        MIN_HOLDING_DAYS = 1  # Prevent overtrading

        for stock_code, position in positions_to_check:
            if stock_code not in self.positions or position.get("exiting", False):
                continue

            try:
                self.positions[stock_code]["exiting"] = True

                # Get position details
                entry_price = position["entry_price"]
                entry_time = position.get("entry_time")
                exchange_code = position["exchange"]

                # Calculate holding period
                days_held = (
                    self._calculate_holding_days(entry_time) if entry_time else 1
                )

                # Skip if too new (prevent overtrading)
                if days_held < MIN_HOLDING_DAYS:
                    continue

                # Get current price
                current_price = self.api.get_current_price(stock_code, exchange_code)
                if current_price is None:
                    continue

                # Calculate current profit for logging
                profit_percent = ((current_price / entry_price) - 1) * 100
                logging.info(
                    f"{stock_code}: {profit_percent:.2f}% profit after {days_held} days"
                )

                # Get historical data and indicators
                hist_data = self.api.get_historical_data(stock_code, exchange_code)
                if hist_data is None:
                    continue

                with_indicators = self.api.calculate_indicators(hist_data)
                if with_indicators is None:
                    continue

                # Check sell signal
                should_exit, reason = self._check_sell_signal(
                    with_indicators, entry_price, days_held, market_condition
                )

                if should_exit:
                    logging.warning(f"{stock_code}: Exit signal - {reason}")
                    if self.exit_position(stock_code, exit_reason=reason):
                        exited_count += 1

            except Exception as e:
                logging.error(f"Error checking exit for {stock_code}: {e}")
            finally:
                if stock_code in self.positions:
                    self.positions[stock_code].pop("exiting", None)

        return exited_count

    def _check_sell_signal(
        self,
        df: pd.DataFrame,
        entry_price: float,
        days_held: int,
        market_condition: Dict,
    ) -> Tuple[bool, str]:
        """Enhanced exit logic for 10% monthly target - Complete implementation"""
        if df is None or df.empty:
            return False, "No data"

        try:
            latest = df.iloc[-1]
            current_price = latest["close"]
            profit_percent = ((current_price / entry_price) - 1) * 100

            # TIME-BASED EXITS (Weekly targets for 10% monthly)

            # Week 1 (Days 1-7)
            if days_held <= 7:
                if profit_percent >= 8:  # Quick profit
                    return True, f"Week 1 profit taking: {profit_percent:.1f}%"
                if profit_percent <= -3 and days_held >= 2:  # Early loss control
                    return True, f"Week 1 loss control: {profit_percent:.1f}%"
                if days_held == 7 and profit_percent < 2.5:  # Week 1 target
                    return True, f"Week 1 underperformance: {profit_percent:.1f}%"

            # Week 2 (Days 8-14)
            elif days_held <= 14:
                if profit_percent >= 12:
                    return True, f"Week 2 profit target: {profit_percent:.1f}%"
                if profit_percent < 4 and days_held >= 10:
                    return True, f"Week 2 underperformance: {profit_percent:.1f}%"
                if days_held == 14 and profit_percent < 5:
                    return True, f"Week 2 checkpoint failed: {profit_percent:.1f}%"

            # Week 3 (Days 15-21)
            elif days_held <= 21:
                if profit_percent >= 15:
                    return True, f"Week 3 excellent profit: {profit_percent:.1f}%"
                if profit_percent < 6 and days_held >= 18:
                    return True, f"Week 3 underperformance: {profit_percent:.1f}%"
                if days_held == 21 and profit_percent < 7.5:
                    return True, f"Week 3 checkpoint failed: {profit_percent:.1f}%"

            # Week 4+ (Days 22-30)
            elif days_held <= 30:
                if profit_percent >= 10:  # Take 10%+ profits in final week
                    return True, f"Week 4 profit taking: {profit_percent:.1f}%"
                if profit_percent <= -2:
                    return True, f"Week 4 loss limitation: {profit_percent:.1f}%"
                if days_held >= 28:
                    return True, f"Approaching max hold: {profit_percent:.1f}%"

            # Force exit after 30 days
            else:
                return (
                    True,
                    f"Max holding period: {profit_percent:.1f}% after {days_held} days",
                )

            daily_exit, daily_reason = self._check_daily_momentum_degradation(
                df, days_held, profit_percent
            )
            if daily_exit:
                return True, daily_reason

            # TECHNICAL EXITS

            # Major profit target
            if profit_percent >= 20:
                return True, f"Major profit target: {profit_percent:.1f}%"

            # Stop loss (dynamic based on holding period)
            stop_threshold = (
                -4.0 if days_held <= 7 else -3.5 if days_held <= 14 else -3.0
            )
            if profit_percent <= stop_threshold:
                return True, f"Stop loss: {profit_percent:.1f}%"

            # Momentum breakdown
            if days_held >= 5:
                previous = df.iloc[-2]
                momentum_broken = (
                    previous["macd"] > previous["macd_signal"]
                    and latest["macd"] < latest["macd_signal"]
                    and latest["rsi"] < 40
                    and profit_percent < 6
                )
                if momentum_broken:
                    return True, f"Momentum breakdown after {days_held} days"

            # Market crash protection
            if market_condition:
                market_trend = market_condition.get("trend", "neutral")
                market_vs_sma200 = market_condition.get("close_vs_sma200", 0)

                if (
                    market_trend == "bearish"
                    and market_vs_sma200 < -8
                    and profit_percent > -3
                ):
                    return True, f"Market crash protection: {profit_percent:.1f}%"

            return False, f"Hold: {profit_percent:.1f}% after {days_held} days"

        except Exception as e:
            logging.error(f"Error in sell signal check: {e}")
            return False, f"Error: {str(e)}"

    def update_trailing_stops(self) -> int:
        """Update trailing stops for profitable positions"""
        updated_count = 0

        for stock_code, position in self.positions.items():
            try:
                entry_price = position["entry_price"]
                current_stop = position.get("stop_loss", 0)
                exchange_code = position["exchange"]

                # Get current price and ATR
                current_price = self.api.get_current_price(stock_code, exchange_code)
                if current_price is None:
                    continue

                hist_data = self.api.get_historical_data(stock_code, exchange_code)
                if hist_data is None:
                    continue

                with_indicators = self.api.calculate_indicators(hist_data)
                if with_indicators is None:
                    continue

                latest_atr = with_indicators["atr"].iloc[-1]
                profit_percent = ((current_price / entry_price) - 1) * 100

                logging.warning(
                    f"Profit percentage for {stock_code}: {profit_percent:.2f}%"
                )

                # Update trailing stop based on profit level
                new_stop = current_stop

                if profit_percent >= 8:  # Tighter trail at higher profit
                    trail_distance = 1.0 * latest_atr
                    potential_stop = current_price - trail_distance
                    new_stop = max(current_stop, potential_stop)
                elif profit_percent >= 4:  # Standard trail
                    trail_distance = 1.5 * latest_atr
                    potential_stop = current_price - trail_distance
                    new_stop = max(current_stop, potential_stop)

                # Update if stop moved up
                if new_stop > current_stop:
                    self.positions[stock_code]["stop_loss"] = new_stop
                    logging.warning(
                        f"Updated trailing stop for {stock_code}: ₹{current_stop:.2f} -> ₹{new_stop:.2f}"
                    )
                    updated_count += 1

            except Exception as e:
                logging.error(f"Error updating trailing stop for {stock_code}: {e}")

        if updated_count > 0:
            self.save_positions()

        return updated_count

    def _check_daily_momentum_degradation(
        self, df: pd.DataFrame, days_held: int, profit_percent: float
    ) -> Tuple[bool, str]:
        """
        Check for daily momentum degradation to catch gradually declining stocks

        Args:
            df: DataFrame with price data and indicators
            days_held: Number of days position has been held
            profit_percent: Current profit percentage

        Returns:
            tuple: (should_exit, reason)
        """
        try:
            if days_held < 2:  # Need at least 2 days of data
                return False, "Insufficient holding period for daily check"

            latest = df.iloc[-1]

            # Get recent price data
            recent_closes = df["close"].tail(5).values

            if len(recent_closes) < 3:
                return False, "Insufficient price data for momentum check"

            # 1. COUNT CONSECUTIVE DECLINING DAYS
            declining_days = 0
            for i in range(len(recent_closes) - 1, 0, -1):
                if recent_closes[i] < recent_closes[i - 1]:
                    declining_days += 1
                else:
                    break

            # 2. VOLUME PRESSURE ANALYSIS
            recent_volumes = df["volume"].tail(3).mean()
            older_volumes = df["volume"].tail(10).head(7).mean()
            volume_pressure = recent_volumes / older_volumes if older_volumes > 0 else 1

            # 3. RSI DETERIORATION CHECK
            current_rsi = latest["rsi"]
            rsi_decline = 0

            if days_held >= 3 and len(df) >= 4:
                rsi_3_days_ago = df["rsi"].iloc[-4]
                rsi_decline = rsi_3_days_ago - current_rsi

            # 4. DISTANCE FROM MOVING AVERAGES
            distance_from_sma20 = (
                ((latest["close"] / latest["sma_20"]) - 1) * 100
                if not pd.isna(latest["sma_20"])
                else 0
            )

            # 5. DAILY PRICE MOMENTUM
            daily_changes = (
                df["close"].pct_change().tail(3) * 100
            )  # Last 3 days % changes
            avg_daily_change = daily_changes.mean()

            logging.debug(
                f"Daily momentum check - Declining days: {declining_days}, "
                f"Volume pressure: {volume_pressure:.2f}, RSI decline: {rsi_decline:.1f}, "
                f"SMA20 distance: {distance_from_sma20:.2f}%"
            )

            # EXIT CONDITIONS FOR GRADUAL DECLINE

            # Condition 1: Multiple declining days with poor performance
            if declining_days >= 3 and profit_percent < 1:
                return (
                    True,
                    f"Gradual decline: {declining_days} declining days, {profit_percent:.1f}% profit",
                )

            # Condition 2: Declining with volume pressure (institutional selling)
            if declining_days >= 2 and volume_pressure > 1.2 and profit_percent < 2:
                return (
                    True,
                    f"Selling pressure: {declining_days} declining days, {volume_pressure:.1f}x volume",
                )

            # Condition 3: RSI momentum breakdown
            if rsi_decline > 10 and current_rsi < 45 and profit_percent < 3:
                return (
                    True,
                    f"RSI breakdown: {current_rsi:.1f} (declined {rsi_decline:.1f} points)",
                )

            # Condition 4: Breaking below key moving average
            if (
                distance_from_sma20 < -2.0 and profit_percent < 2
            ):  # 2%+ below 20-day SMA
                return (
                    True,
                    f"SMA breakdown: {distance_from_sma20:.1f}% below 20-day SMA",
                )

            # Condition 5: Consistent negative daily momentum
            if avg_daily_change < -0.5 and declining_days >= 2 and profit_percent < 1.5:
                return (
                    True,
                    f"Daily momentum death: {avg_daily_change:.2f}% avg daily change",
                )

            # Condition 6: Early warning for new positions (catch ITC-like situations fast)
            if days_held <= 3 and declining_days >= 2 and profit_percent < -2:
                return (
                    True,
                    f"Early momentum failure: {declining_days} declining days in first 3 days",
                )

            # Condition 7: Volume spike with price decline (distribution pattern)
            if (
                declining_days >= 1
                and volume_pressure > 1.5
                and daily_changes.iloc[-1] < -1.5
                and profit_percent < 0
            ):  # Yesterday declined >1.5% with high volume
                return (
                    True,
                    f"Distribution pattern: High volume decline with negative profit",
                )

            return (
                False,
                f"Daily momentum OK: {declining_days} declining days, {profit_percent:.1f}% profit",
            )

        except Exception as e:
            logging.error(f"Error in daily momentum check: {e}")
            return False, f"Error in daily momentum check: {str(e)}"

    def get_portfolio_summary(self) -> Dict:
        """Get current portfolio summary"""
        total_value = 0
        total_pnl = 0

        for stock_code, position in self.positions.items():
            try:
                entry_price = position["entry_price"]
                quantity = position["quantity"]

                current_price = self.api.get_current_price(
                    stock_code, position["exchange"]
                )
                if current_price:
                    position_value = current_price * quantity
                    position_pnl = (current_price - entry_price) * quantity

                    total_value += position_value
                    total_pnl += position_pnl
            except:
                continue

        return {
            "positions_count": len(self.positions),
            "total_value": total_value,
            "unrealized_pnl": total_pnl,
            "daily_trades": len(self.today_trades),
            "positions": self.positions,
        }

    def save_positions(self):
        """Save positions to file"""
        try:
            positions_dir = "positions"
            os.makedirs(positions_dir, exist_ok=True)

            today_str = datetime.datetime.now().strftime("%Y%m%d")
            filename = os.path.join(positions_dir, f"positions_{today_str}.json")

            with open(filename, "w") as f:
                json.dump(self.positions, f, indent=2)

            logging.info(f"Saved {len(self.positions)} positions")

        except Exception as e:
            logging.error(f"Error saving positions: {e}")

    def load_positions(self):
        """Load positions from file"""
        try:
            positions_dir = "positions"
            os.makedirs(positions_dir, exist_ok=True)

            today_str = datetime.datetime.now().strftime("%Y%m%d")
            filename = os.path.join(positions_dir, f"positions_{today_str}.json")

            if os.path.exists(filename):
                with open(filename, "r") as f:
                    self.positions = json.load(f)
                logging.info(
                    f"Loaded {len(self.positions)} positions from today's file"
                )
            else:
                # Look for most recent file
                position_files = sorted(
                    [
                        f
                        for f in os.listdir(positions_dir)
                        if f.startswith("positions_")
                    ],
                    reverse=True,
                )

                if position_files:
                    latest_file = os.path.join(positions_dir, position_files[0])
                    with open(latest_file, "r") as f:
                        self.positions = json.load(f)

                    # Save as today's file
                    with open(filename, "w") as f:
                        json.dump(self.positions, f, indent=2)

                    logging.info(
                        f"Copied {len(self.positions)} positions from {position_files[0]} to today's file"
                    )
                else:
                    self.positions = {}
                    logging.info("No previous positions found, starting fresh")

        except Exception as e:
            logging.error(f"Error loading positions: {e}")
            self.positions = {}
        finally:
            logging.info(f"Current positions loaded: {list(self.positions.keys())}")

    def save_trades(self):
        """Save today's trades"""
        try:
            trades_dir = "trades"
            os.makedirs(trades_dir, exist_ok=True)

            today_str = datetime.datetime.now().strftime("%Y%m%d")
            filename = os.path.join(trades_dir, f"trades_{today_str}.json")

            with open(filename, "w") as f:
                json.dump(self.today_trades, f, indent=2)

            logging.info(f"Saved {len(self.today_trades)} trades")

        except Exception as e:
            logging.error(f"Error saving trades: {e}")

    def load_today_trades(self):
        """Load today's trades"""
        try:
            trades_dir = "trades"
            today_str = datetime.datetime.now().strftime("%Y%m%d")
            filename = os.path.join(trades_dir, f"trades_{today_str}.json")

            if os.path.exists(filename):
                with open(filename, "r") as f:
                    self.today_trades = json.load(f)
                logging.info(f"Loaded {len(self.today_trades)} trades for today")
            else:
                self.today_trades = []
                logging.info("No trades file found for today, starting fresh")

        except Exception as e:
            logging.error(f"Error loading today's trades: {e}")
            self.today_trades = []

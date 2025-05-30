#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock Screening and Selection Module
Handles all stock selection logic for better monthly returns
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Tuple, List, Optional


class StockScreener:
    """Enhanced stock screening for 10% monthly targets"""

    def __init__(self, config, api_client):
        self.config = config
        self.api = api_client
        self.MIN_PRICE = config.getfloat("Screening", "min_price", fallback=100)
        self.MAX_PRICE = config.getfloat("Screening", "max_price", fallback=15000)
        self.MIN_VOLUME = config.getint("Screening", "min_volume", fallback=100000)

    def calculate_relative_strength(
        self, stock_data: pd.DataFrame, index_data: pd.DataFrame, periods: int = 20
    ) -> float:
        """Calculate relative strength of stock vs index"""
        try:
            if len(stock_data) < periods or len(index_data) < periods:
                return 0.5

            stock_return = (
                (stock_data["close"].iloc[-1] / stock_data["close"].iloc[-periods]) - 1
            ) * 100
            index_return = (
                (index_data["close"].iloc[-1] / index_data["close"].iloc[-periods]) - 1
            ) * 100

            if index_return != 0:
                relative_strength = stock_return / index_return
            else:
                relative_strength = 1.0

            logging.debug(
                f"Stock: {stock_return:.2f}%, Index: {index_return:.2f}%, RS: {relative_strength:.2f}"
            )
            return relative_strength

        except Exception as e:
            logging.error(f"Error calculating relative strength: {e}")
            return 0.5

    def check_momentum_cascade(self, data: pd.DataFrame) -> Tuple[bool, str]:
        """Check if price structure shows bullish momentum cascade"""
        try:
            latest = data.iloc[-1]

            required_cols = ["close", "sma_20", "sma_50", "sma_200"]
            for col in required_cols:
                if col not in data.columns or pd.isna(latest[col]):
                    return False, f"Missing {col}"

            # Perfect cascade: price > sma_20 > sma_50 > sma_200
            perfect_cascade = (
                latest["close"]
                > latest["sma_20"]
                > latest["sma_50"]
                > latest["sma_200"]
            )

            if perfect_cascade:
                return True, "Perfect momentum cascade"

            # Acceptable: price > sma_20 > sma_50
            acceptable_cascade = latest["close"] > latest["sma_20"] > latest["sma_50"]

            if acceptable_cascade:
                return True, "Acceptable momentum cascade"

            # Minimum: price above rising 20-day SMA
            if latest["close"] > latest["sma_20"] and len(data) >= 5:
                sma_20_rising = data["sma_20"].iloc[-1] > data["sma_20"].iloc[-5]
                if sma_20_rising:
                    return True, "Price above rising 20-day SMA"

            return False, "No bullish momentum structure"

        except Exception as e:
            return False, f"Error: {str(e)}"

    def check_volume_confirmation(
        self, data: pd.DataFrame, periods: int = 10
    ) -> Tuple[bool, str]:
        """Check for sustained volume increase"""
        try:
            if len(data) < periods * 2:
                return False, "Insufficient volume data"

            recent_avg = data["volume"].tail(periods).mean()
            older_avg = data["volume"].tail(periods * 2).head(periods).mean()

            if older_avg == 0:
                return False, "No historical volume"

            volume_ratio = recent_avg / older_avg

            if volume_ratio > 1.3:
                return True, f"Strong volume: {volume_ratio:.1f}x"
            elif volume_ratio > 1.1:
                return True, f"Good volume: {volume_ratio:.1f}x"
            else:
                return False, f"Weak volume: {volume_ratio:.1f}x"

        except Exception as e:
            return False, f"Volume error: {str(e)}"

    def enhanced_buy_signal(
        self, df: pd.DataFrame, market_condition: Dict, index_data: pd.DataFrame
    ) -> Tuple[bool, str]:
        """Enhanced buy signal with strict filtering for monthly targets"""

        if df is None or df.empty or len(df) < 30:
            return False, "Insufficient data"

        try:
            latest = df.iloc[-1]
            previous = df.iloc[-2]

            # FILTER 1: Market quality
            if market_condition.get("market_quality") == "poor":
                return False, "Poor market conditions"

            # FILTER 2: Stock momentum structure
            momentum_ok, momentum_reason = self.check_momentum_cascade(df)
            if not momentum_ok:
                return False, f"Poor structure: {momentum_reason}"

            # FILTER 3: Relative strength
            if index_data is not None and not index_data.empty:
                relative_strength = self.calculate_relative_strength(df, index_data)
                if relative_strength < 0.8:
                    return False, f"Weak vs index: {relative_strength:.2f}"

            # FILTER 4: Volume confirmation
            volume_ok, volume_reason = self.check_volume_confirmation(df)
            if not volume_ok:
                return False, f"Volume: {volume_reason}"

            # Technical signals (higher standards)
            signal_reasons = []
            score = 0

            # RSI (more selective)
            if 30 < latest["rsi"] < 65:
                if previous["rsi"] < 50 and latest["rsi"] > 50:
                    signal_reasons.append(f"RSI bullish: {latest['rsi']:.1f}")
                    score += 3
                elif latest["rsi"] > previous["rsi"]:
                    signal_reasons.append(f"RSI rising: {latest['rsi']:.1f}")
                    score += 1

            # MACD (stronger requirements)
            if "macd" in df.columns:
                macd_cross = (
                    previous["macd"] < previous["macd_signal"]
                    and latest["macd"] > latest["macd_signal"]
                )
                macd_positive = latest["macd"] > 0 and latest["macd_signal"] > 0

                if macd_cross and macd_positive:
                    signal_reasons.append("Strong MACD cross")
                    score += 4
                elif macd_cross:
                    signal_reasons.append("MACD cross")
                    score += 2

            # Price momentum (critical for monthly targets)
            if len(df) >= 6:
                price_5d = ((latest["close"] / df["close"].iloc[-6]) - 1) * 100
                if price_5d >= 4:
                    signal_reasons.append(f"5-day momentum: {price_5d:.1f}%")
                    score += 3

            # Breakout confirmation
            if latest["close"] > df["high"].rolling(20).max().iloc[-2]:
                signal_reasons.append("20-day breakout")
                score += 2

            # Higher minimum score for quality
            min_score = 7
            if market_condition.get("momentum_direction") == "accelerating":
                min_score = 6
            elif market_condition.get("momentum_direction") == "decelerating":
                min_score = 8

            if score >= min_score:
                return True, f"Strong signals ({score}): {', '.join(signal_reasons)}"
            else:
                return False, f"Weak signals ({score}/{min_score})"

        except Exception as e:
            logging.error(f"Enhanced buy signal error: {e}")
            return False, f"Error: {str(e)}"

    def screen_stocks(
        self,
        stock_universe: List[Dict],
        market_condition: Dict,
        index_data: pd.DataFrame,
        positions: Dict,
    ) -> List[Dict]:
        """Screen stocks with enhanced filtering and detailed logging"""
        
        logging.info(f"Starting stock screening for {len(stock_universe)} stocks in universe")
        
        if market_condition.get("market_quality") == "poor":
            logging.warning("Market quality is poor - skipping stock screening")
            return []
            
        opportunities = []

        for stock in stock_universe[:50]:  # Limit API calls
            stock_code = stock["stock_code"]
            exchange_code = stock["exchange_code"]
            logging.debug(f"\nProcessing {stock_code}")

            # Skip if already in positions
            if stock_code in positions:
                logging.debug(f"Skipping {stock_code} - already in positions")
                continue

            try:
                # Get current price
                current_price = self.api.get_current_price(stock_code, exchange_code)
                if current_price is None:
                    logging.debug(f"Skipping {stock_code} - could not fetch current price")
                    continue
                    
                logging.info(f"{stock_code} - Current price: {current_price:.2f}")

                # Price range check
                if not (self.MIN_PRICE <= current_price <= self.MAX_PRICE):
                    logging.info(f"Skipping {stock_code} - Price {current_price:.2f} outside range [{self.MIN_PRICE}, {self.MAX_PRICE}]")
                    continue
                    
                logging.debug(f"{stock_code} - Price {current_price:.2f} within valid range")

                # Get historical data
                hist_data = self.api.get_historical_data(stock_code, exchange_code)
                if hist_data is None or len(hist_data) < 50:
                    logging.info(f"Skipping {stock_code} - Insufficient historical data")
                    continue
                    
                logging.info(f"{stock_code} - Retrieved {len(hist_data)} days of historical data")

                # Volume check
                avg_volume = hist_data["volume"].tail(10).mean()
                if avg_volume < self.MIN_VOLUME:
                    logging.info(f"Skipping {stock_code} - Average volume {avg_volume:,.0f} below minimum {self.MIN_VOLUME:,.0f}")
                    continue
                    
                logging.info(f"{stock_code} - Volume check passed: {avg_volume:,.0f} (min: {self.MIN_VOLUME:,.0f})")

                # Calculate indicators
                with_indicators = self.api.calculate_indicators(hist_data)
                if with_indicators is None:
                    logging.info(f"Skipping {stock_code} - Failed to calculate indicators")
                    continue
                    
                logging.debug(f"{stock_code} - Indicators calculated successfully")

                # Enhanced buy signal
                buy_signal, reason = self.enhanced_buy_signal(
                    with_indicators, market_condition, index_data
                )
                
                if not buy_signal:
                    logging.info(f"No buy signal for {stock_code} - {reason}")
                    continue
                    
                logging.info(f"Buy signal for {stock_code}: {reason}")

                # Calculate metrics for selected stocks
                latest_atr = with_indicators["atr"].iloc[-1]
                stop_loss = current_price - (2 * latest_atr)

                # Calculate relative strength for ranking
                rel_strength = self.calculate_relative_strength(
                    with_indicators, index_data
                )
                
                logging.info(f"{stock_code} - ATR: {latest_atr:.2f}, Stop Loss: {stop_loss:.2f}, Rel Strength: {rel_strength:.2f}")

                opportunity = {
                    "stock_code": stock_code,
                    "exchange_code": exchange_code,
                    "current_price": current_price,
                    "stop_loss": stop_loss,
                    "relative_strength": rel_strength,
                    "signal_reason": reason,
                    "quality_score": rel_strength * 10,
                }
                opportunities.append(opportunity)
                logging.warning(f"Quality opportunity: {stock_code} - {reason}")

            except Exception as e:
                logging.error(f"Error screening {stock_code}: {e}", exc_info=True)
                continue

        # Sort by quality score
        opportunities.sort(key=lambda x: x["quality_score"], reverse=True)
        
        logging.info(f"Stock screening complete. Found {len(opportunities)} opportunities")
        if opportunities:
            top_opp = opportunities[0]
            logging.info(f"Top opportunity: {top_opp['stock_code']} (Score: {top_opp['quality_score']:.2f}, Reason: {top_opp['signal_reason']})")
            
        return opportunities

    def get_best_opportunity(
        self,
        stock_universe: List[Dict],
        market_condition: Dict,
        index_data: pd.DataFrame,
        positions: Dict,
    ) -> Optional[Dict]:
        """Get single best opportunity"""
        opportunities = self.screen_stocks(
            stock_universe, market_condition, index_data, positions
        )

        if opportunities:
            best = opportunities[0]
            logging.warning(
                f"Best: {best['stock_code']} (Quality: {best['quality_score']:.1f})"
            )
            return best

        return None

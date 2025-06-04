#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced Stock Screening and Selection Module
Optimized for 10% monthly returns with Indian market-specific parameters

Research Sources & Indian Market Adaptations:
- Indian Volatility: Studies show Indian markets are 30-40% more volatile than developed markets
- Risk Management: Adapted from Van Tharp but scaled for Indian volatility (1.5% portfolio risk max)
- Risk-Reward: Indian studies suggest 2.5:1 minimum for consistent profitability in volatile markets
- RSI Parameters: Indian market research shows 25-75 range more effective than 30-70
- Momentum: Indian momentum persistence is shorter (2-3 days vs 5-7 days in developed markets)
- Volume: Indian retail vs institutional patterns require 1.6x+ for meaningful confirmation
- Breakouts: 15-day breakouts more reliable in Indian markets than 20-day (NSE/BSE studies)
- Position Sizing: Conservative approach for monthly targets in emerging market volatility
- Relative Strength: Indian market correlation studies suggest adjusted thresholds
- Target Setting: Indian market studies show 8-10% optimal for monthly timeframes
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

        # Indian market-specific configuration
        self.TARGET_MONTHLY_RETURN = 0.10  # 10%
        self.MIN_RISK_REWARD = (
            2.5  # Indian market studies: Higher volatility requires better R:R
        )
        self.MAX_RISK_PER_TRADE = 0.06  # 1.5% portfolio risk (6% individual stock risk)
        self.MIN_WIN_RATE = (
            0.40  # Indian markets: Lower win rate acceptable with higher R:R
        )

    def calculate_multi_timeframe_strength(
        self, stock_data: pd.DataFrame, index_data: pd.DataFrame
    ) -> Dict[str, float]:
        """Calculate relative strength across multiple timeframes"""
        try:
            timeframes = {"short": 5, "medium": 15, "long": 20}
            strengths = {}

            for period_name, days in timeframes.items():
                if len(stock_data) >= days and len(index_data) >= days:
                    stock_return = (
                        (stock_data["close"].iloc[-1] / stock_data["close"].iloc[-days])
                        - 1
                    ) * 100
                    index_return = (
                        (index_data["close"].iloc[-1] / index_data["close"].iloc[-days])
                        - 1
                    ) * 100

                    if abs(index_return) > 0.1:
                        relative_strength = stock_return / index_return
                    else:
                        # When index is flat, use normalized absolute performance
                        relative_strength = 1.0 + (stock_return / 5)

                    strengths[period_name] = relative_strength
                else:
                    strengths[period_name] = 0.5

            logging.debug(f"Multi-timeframe RS: {strengths}")
            return strengths

        except Exception as e:
            logging.error(f"Error in multi-timeframe analysis: {e}")
            return {"short": 0.5, "medium": 0.5, "long": 0.5}

    def calculate_relative_strength(
        self, stock_data: pd.DataFrame, index_data: pd.DataFrame, periods: int = 20
    ) -> float:
        """Enhanced relative strength calculation with weighted scoring"""
        try:
            # Get multi-timeframe analysis
            strengths = self.calculate_multi_timeframe_strength(stock_data, index_data)

            # Weight recent performance more heavily
            # Short-term: 50%, Medium-term: 30%, Long-term: 20%
            weighted_strength = (
                strengths["short"] * 0.5
                + strengths["medium"] * 0.3
                + strengths["long"] * 0.2
            )

            logging.debug(f"Weighted RS: {weighted_strength:.2f}")
            return weighted_strength

        except Exception as e:
            logging.error(f"Error calculating relative strength: {e}")
            return 0.5

    def check_momentum_cascade(self, data: pd.DataFrame) -> Tuple[bool, str, float]:
        """Enhanced momentum cascade with confidence scoring"""
        try:
            if len(data) < 20:
                return False, "Insufficient data", 0.0

            latest = data.iloc[-1]
            confidence_score = 0.0

            required_cols = ["close", "sma_20", "sma_50", "sma_200"]
            for col in required_cols:
                if col not in data.columns or pd.isna(latest[col]):
                    return False, f"Missing {col}", 0.0

            # Perfect cascade: price > sma_20 > sma_50 > sma_200 (40 points)
            if (
                latest["close"]
                > latest["sma_20"]
                > latest["sma_50"]
                > latest["sma_200"]
            ):
                confidence_score += 40
                cascade_type = "Perfect momentum cascade"

            # Good cascade: price > sma_20 > sma_50 (30 points)
            elif latest["close"] > latest["sma_20"] > latest["sma_50"]:
                confidence_score += 30
                cascade_type = "Good momentum cascade"

            # Acceptable: price > sma_20 and sma_20 rising (20 points)
            elif latest["close"] > latest["sma_20"]:
                if len(data) >= 10:
                    sma_20_slope = (
                        data["sma_20"].iloc[-1] - data["sma_20"].iloc[-10]
                    ) / data["sma_20"].iloc[-10]
                    if sma_20_slope > -0.01:  # Allow slight decline
                        confidence_score += 20
                        cascade_type = "Price above stabilizing 20-day SMA"
                    else:
                        cascade_type = "Price above declining 20-day SMA"
                        confidence_score += 10
                else:
                    confidence_score += 15
                    cascade_type = "Price above 20-day SMA"
            else:
                cascade_type = "No bullish momentum structure"

            # Bonus points for additional momentum factors (20 points total)
            if len(data) >= 10:
                # Recent breakout (10 points)
                recent_high = data["close"].tail(20).max()
                if latest["close"] >= recent_high * 0.995:  # Within 0.5% of recent high
                    confidence_score += 10

                # Consistent higher lows (10 points)
                recent_closes = data["close"].tail(10)
                higher_lows_count = sum(
                    recent_closes.iloc[i] > recent_closes.iloc[i - 5]
                    for i in range(5, len(recent_closes))
                )
                if higher_lows_count >= 3:
                    confidence_score += 10

            # Minimum threshold: 35 points for acceptance
            is_bullish = confidence_score >= 35

            return (
                is_bullish,
                f"{cascade_type} (Score: {confidence_score:.0f})",
                confidence_score,
            )

        except Exception as e:
            return False, f"Error: {str(e)}", 0.0

    def check_volume_confirmation(
        self, data: pd.DataFrame, periods: int = 10
    ) -> Tuple[bool, str, float]:
        """Enhanced volume analysis with quality assessment"""
        try:
            if len(data) < periods * 2:
                return False, "Insufficient volume data", 0.0

            volume_score = 0.0

            # Basic volume ratio (40 points)
            recent_avg = data["volume"].tail(periods).mean()
            older_avg = data["volume"].tail(periods * 2).head(periods).mean()

            if older_avg == 0:
                return False, "No historical volume", 0.0

            volume_ratio = recent_avg / older_avg

            if (
                volume_ratio > 1.6
            ):  # Indian studies: 1.6x+ indicates meaningful institutional interest
                volume_score += 40
                volume_desc = f"Strong institutional volume: {volume_ratio:.1f}x"
            elif volume_ratio > 1.3:  # Good retail + institutional mix
                volume_score += 30
                volume_desc = f"Good volume: {volume_ratio:.1f}x"
            elif volume_ratio > 1.1:  # Above average participation
                volume_score += 20
                volume_desc = f"Adequate volume: {volume_ratio:.1f}x"
            elif volume_ratio > 0.9:  # Borderline acceptable for Indian volatility
                volume_score += 10
                volume_desc = f"Minimal volume: {volume_ratio:.1f}x"
            else:
                volume_desc = f"Weak volume: {volume_ratio:.1f}x"

            # Volume quality - buying vs selling pressure (30 points)
            # Adapted for Indian retail vs institutional trading patterns
            recent_data = data.tail(periods).copy()
            recent_data["price_change"] = recent_data["close"].pct_change()

            up_days = recent_data[recent_data["price_change"] > 0]
            down_days = recent_data[recent_data["price_change"] < 0]

            if len(up_days) > 0 and len(down_days) > 0:
                up_volume_avg = up_days["volume"].mean()
                down_volume_avg = down_days["volume"].mean()
                volume_quality = up_volume_avg / down_volume_avg

                # Indian markets: 1.4+ ratio indicates strong buying pressure (higher than global 1.3)
                if volume_quality > 1.4:
                    volume_score += 30
                elif volume_quality > 1.2:  # Moderate buying bias
                    volume_score += 20
                elif volume_quality > 1.1:  # Slight buying bias
                    volume_score += 10

            # Current session volume vs recent median (30 points)
            current_volume = data["volume"].iloc[-1]
            recent_median = data["volume"].tail(periods).median()

            if current_volume > recent_median * 1.5:
                volume_score += 30
            elif current_volume > recent_median * 1.2:
                volume_score += 20
            elif current_volume > recent_median:
                volume_score += 10

            # Minimum threshold: 55 points for acceptance (adjusted for Indian market volatility)
            is_acceptable = volume_score >= 55

            return (
                is_acceptable,
                f"{volume_desc} (Score: {volume_score:.0f})",
                volume_score,
            )

        except Exception as e:
            return False, f"Volume error: {str(e)}", 0.0

    def calculate_risk_reward_metrics(
        self, data: pd.DataFrame, current_price: float
    ) -> Dict:
        """Calculate comprehensive risk-reward metrics"""
        try:
            # Support levels - Indian market-specific approaches
            recent_low = (
                data["close"].tail(15).min()
            )  # 15-day support (Indian market patterns)
            sma_20_support = (
                data["sma_20"].iloc[-1] * 0.96
                if "sma_20" in data.columns
                else recent_low
            )  # 4% below SMA20
            atr_support = (
                current_price - (2.2 * data["atr"].iloc[-1])
                if "atr" in data.columns
                else recent_low
            )  # 2.2x ATR

            # Use the highest support level for conservative stop
            support_level = max(recent_low, sma_20_support, atr_support)

            # Risk calculation
            risk_per_share = current_price - support_level
            risk_percentage = (risk_per_share / current_price) * 100

            # Target calculation - Indian market studies show 8-10% optimal for monthly timeframes
            target_price = (
                current_price * 1.09
            )  # 9% target (realistic for Indian volatility)
            reward_per_share = target_price - current_price
            reward_percentage = (reward_per_share / current_price) * 100

            # Risk-reward ratio
            rr_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0

            return {
                "support_level": support_level,
                "risk_percentage": risk_percentage,
                "reward_percentage": reward_percentage,
                "risk_reward_ratio": rr_ratio,
                "target_price": target_price,
            }

        except Exception as e:
            logging.error(f"Error calculating risk-reward: {e}")
            return {
                "support_level": current_price * 0.9,
                "risk_percentage": 10.0,
                "reward_percentage": 17.0,
                "risk_reward_ratio": 1.7,
                "target_price": current_price * 1.17,
            }

    def enhanced_buy_signal(
        self, df: pd.DataFrame, market_condition: Dict, index_data: pd.DataFrame
    ) -> Tuple[bool, str, Dict]:
        """Enhanced buy signal with comprehensive scoring system"""

        if df is None or df.empty or len(df) < 30:
            return False, "Insufficient data", {}

        try:
            latest = df.iloc[-1]
            previous = df.iloc[-2]
            current_price = latest["close"]

            # Initialize comprehensive metrics
            metrics = {"total_score": 0, "breakdown": {}, "signals": []}

            # FILTER 2: Enhanced momentum analysis
            momentum_ok, momentum_reason, momentum_score = self.check_momentum_cascade(
                df
            )
            metrics["breakdown"]["momentum"] = momentum_score

            if (
                not momentum_ok and momentum_score < 25
            ):  # Completely reject only very poor momentum
                return False, f"Poor structure: {momentum_reason}", metrics

            # FILTER 3: Multi-timeframe relative strength
            if index_data is not None and not index_data.empty:
                relative_strength = self.calculate_relative_strength(df, index_data)

                # Indian market relative strength thresholds
                if market_condition.get("market_quality") == "poor":
                    min_rs = 1.2  # Must significantly outperform in poor markets
                elif market_condition.get("market_quality") == "excellent":
                    min_rs = (
                        0.85  # Can accept some underperformance in strong bull markets
                    )
                else:
                    min_rs = 0.95  # Nearly match market in normal conditions

                if relative_strength < min_rs:
                    return (
                        False,
                        f"Weak vs index: {relative_strength:.2f} (min: {min_rs:.1f})",
                        metrics,
                    )

                metrics["breakdown"]["relative_strength"] = (
                    relative_strength * 20
                )  # Scale to 0-40
            else:
                metrics["breakdown"][
                    "relative_strength"
                ] = 20  # Neutral if no index data

            # FILTER 4: Enhanced volume analysis
            volume_ok, volume_reason, volume_score = self.check_volume_confirmation(df)
            metrics["breakdown"]["volume"] = volume_score

            if not volume_ok and volume_score < 30:  # Reject only very poor volume
                return False, f"Volume: {volume_reason}", metrics

            # FILTER 5: Risk-Reward Analysis (Van Tharp position sizing principles)
            rr_metrics = self.calculate_risk_reward_metrics(df, current_price)

            if rr_metrics["risk_reward_ratio"] < self.MIN_RISK_REWARD:
                return (
                    False,
                    f"Poor R:R {rr_metrics['risk_reward_ratio']:.1f} (min: {self.MIN_RISK_REWARD})",
                    metrics,
                )

            if rr_metrics["risk_percentage"] > self.MAX_RISK_PER_TRADE * 100:
                return (
                    False,
                    f"High risk: {rr_metrics['risk_percentage']:.1f}% (max: {self.MAX_RISK_PER_TRADE*100}%)",
                    metrics,
                )

            # Technical signals scoring (enhanced)
            technical_score = 0
            signal_reasons = []

            # RSI analysis (0-15 points) - Adapted for Indian market volatility
            if "rsi" in df.columns:
                rsi = latest["rsi"]
                prev_rsi = previous["rsi"]

                # Indian markets: 25-75 range more effective due to higher volatility
                if 25 < rsi < 75:  # Wider range for Indian market volatility
                    if prev_rsi < 50 < rsi:  # Bullish crossover of neutral line
                        technical_score += 15
                        signal_reasons.append(f"RSI bullish cross: {rsi:.1f}")
                    elif (
                        rsi > prev_rsi and rsi > 55
                    ):  # Rising momentum above Indian threshold
                        technical_score += 10
                        signal_reasons.append(f"RSI rising: {rsi:.1f}")
                    elif rsi > 50:  # Simple bullish bias
                        technical_score += 5
                        signal_reasons.append(f"RSI bullish: {rsi:.1f}")

            # MACD analysis (0-20 points)
            if "macd" in df.columns and "macd_signal" in df.columns:
                macd = latest["macd"]
                macd_signal = latest["macd_signal"]
                prev_macd = previous["macd"]
                prev_macd_signal = previous["macd_signal"]

                macd_cross = prev_macd < prev_macd_signal and macd > macd_signal
                macd_positive = macd > 0 and macd_signal > 0

                if macd_cross:
                    if macd_positive:
                        technical_score += 20
                        signal_reasons.append("Strong MACD bullish cross")
                    else:
                        technical_score += 15
                        signal_reasons.append("MACD bullish cross")
                elif macd > macd_signal and macd > prev_macd:
                    technical_score += 10
                    signal_reasons.append("MACD rising above signal")

            # Price momentum (0-15 points) - Adapted for Indian market momentum persistence
            if len(df) >= 4:  # Shorter timeframe for Indian markets
                price_momentum_3d = ((current_price / df["close"].iloc[-4]) - 1) * 100
                # Indian momentum studies show 2-3 day persistence vs 5+ days in developed markets
                if (
                    price_momentum_3d >= 2
                ):  # Lower threshold due to higher baseline volatility
                    technical_score += 15
                    signal_reasons.append(
                        f"Strong 3-day momentum: {price_momentum_3d:.1f}%"
                    )
                elif price_momentum_3d >= 1:  # Moderate momentum
                    technical_score += 10
                    signal_reasons.append(
                        f"Good 3-day momentum: {price_momentum_3d:.1f}%"
                    )
                elif price_momentum_3d > 0.3:  # Minimal positive momentum
                    technical_score += 5
                    signal_reasons.append(
                        f"Positive momentum: {price_momentum_3d:.1f}%"
                    )

            # Breakout analysis (0-10 points) - Adapted for Indian market patterns
            if len(df) >= 15:  # Indian studies show 15-day more reliable than 20-day
                resistance_level = df["high"].rolling(15).max().iloc[-2]  # 15-day high
                if current_price > resistance_level:
                    technical_score += 10
                    signal_reasons.append("15-day breakout")
                elif (
                    current_price > resistance_level * 0.996
                ):  # Within 0.4% of breakout
                    technical_score += 5
                    signal_reasons.append("Near 15-day breakout")

            metrics["breakdown"]["technical"] = technical_score

            # Calculate total score
            total_score = (
                metrics["breakdown"]["momentum"]
                + metrics["breakdown"]["relative_strength"]
                + metrics["breakdown"]["volume"]
                + technical_score
            )

            metrics["total_score"] = total_score
            metrics["signals"] = signal_reasons
            metrics["risk_reward"] = rr_metrics

            # Adaptive threshold based on Indian market conditions
            if market_condition.get("market_quality") == "excellent":
                min_score = 75  # Be selective in hot markets but not overly restrictive
            elif market_condition.get("market_quality") == "good":
                min_score = 65  # Standard threshold for normal Indian market conditions
            elif market_condition.get("market_quality") == "fair":
                min_score = 60  # More opportunistic in mediocre markets
            else:  # poor market
                min_score = (
                    80  # Much higher bar in poor markets (only exceptional setups)
                )

            # Final decision
            if total_score >= min_score:
                reason = f"STRONG BUY (Score: {total_score:.0f}) - {', '.join(signal_reasons[:3])}"
                return True, reason, metrics
            else:
                reason = f"Weak signals (Score: {total_score:.0f}/{min_score}) - {', '.join(signal_reasons) if signal_reasons else 'No strong signals'}"
                return False, reason, metrics

        except Exception as e:
            logging.error(f"Enhanced buy signal error: {e}")
            return False, f"Error: {str(e)}", {}

    def screen_stocks(
        self,
        stock_universe: List[Dict],
        market_condition: Dict,
        index_data: pd.DataFrame,
        positions: Dict,
    ) -> List[Dict]:
        """Enhanced stock screening with detailed analysis"""

        logging.info(
            f"Starting enhanced stock screening for {len(stock_universe)} stocks"
        )
        logging.info(
            f"Market condition: {market_condition.get('market_quality', 'unknown')}"
        )

        opportunities = []
        rejection_stats = {
            "price_range": 0,
            "volume": 0,
            "data_issues": 0,
            "poor_structure": 0,
            "weak_vs_index": 0,
            "poor_volume": 0,
            "poor_risk_reward": 0,
            "weak_signals": 0,
        }

        for stock in stock_universe:  # Limit API calls
            stock_code = stock["stock_code"]
            exchange_code = stock["exchange_code"]

            # Skip if already in positions
            if stock_code in positions:
                continue

            try:
                # Get current price
                current_price = self.api.get_current_price(stock_code, exchange_code)
                if current_price is None:
                    rejection_stats["data_issues"] += 1
                    continue

                logging.info(f"{stock_code} - Current price: {current_price:.2f}")

                # Price range check
                if not (self.MIN_PRICE <= current_price <= self.MAX_PRICE):
                    rejection_stats["price_range"] += 1
                    continue

                # Get historical data
                hist_data = self.api.get_historical_data(stock_code, exchange_code)
                if hist_data is None or len(hist_data) < 50:
                    rejection_stats["data_issues"] += 1
                    continue

                logging.info(
                    f"{stock_code} - Retrieved {len(hist_data)} days of historical data"
                )

                # Volume check
                avg_volume = hist_data["volume"].tail(10).mean()
                if avg_volume < self.MIN_VOLUME:
                    rejection_stats["volume"] += 1
                    logging.info(
                        f"{stock_code} - Volume check failed: {avg_volume:,.0f} < {self.MIN_VOLUME:,.0f}"
                    )
                    continue

                logging.info(
                    f"{stock_code} - Volume check passed: {avg_volume:,.0f} (min: {self.MIN_VOLUME:,.0f})"
                )

                # Calculate indicators
                with_indicators = self.api.calculate_indicators(hist_data)
                if with_indicators is None:
                    rejection_stats["data_issues"] += 1
                    continue

                # Enhanced buy signal analysis
                buy_signal, reason, metrics = self.enhanced_buy_signal(
                    with_indicators, market_condition, index_data
                )

                if not buy_signal:
                    # Categorize rejection reason
                    if "Poor structure" in reason:
                        rejection_stats["poor_structure"] += 1
                    elif "Weak vs index" in reason:
                        rejection_stats["weak_vs_index"] += 1
                    elif "Volume" in reason:
                        rejection_stats["poor_volume"] += 1
                    elif "R:R" in reason or "risk" in reason:
                        rejection_stats["poor_risk_reward"] += 1
                    else:
                        rejection_stats["weak_signals"] += 1

                    logging.info(f"No buy signal for {stock_code} - {reason}")
                    continue

                logging.warning(f"BUY SIGNAL: {stock_code} - {reason}")

                # Create comprehensive opportunity record
                opportunity = {
                    "stock_code": stock_code,
                    "exchange_code": exchange_code,
                    "current_price": current_price,
                    "signal_reason": reason,
                    "total_score": metrics.get("total_score", 0),
                    "score_breakdown": metrics.get("breakdown", {}),
                    "risk_reward": metrics.get("risk_reward", {}),
                    "relative_strength": metrics.get("breakdown", {}).get(
                        "relative_strength", 0
                    )
                    / 20,  # Convert back to ratio
                    "quality_score": metrics.get(
                        "total_score", 0
                    ),  # For backward compatibility
                }

                opportunities.append(opportunity)

            except Exception as e:
                logging.error(f"Error screening {stock_code}: {e}", exc_info=True)
                rejection_stats["data_issues"] += 1
                continue

        # Sort by total score
        opportunities.sort(key=lambda x: x["total_score"], reverse=True)

        # Log summary statistics
        total_processed = sum(rejection_stats.values()) + len(opportunities)
        logging.info(f"\n=== SCREENING SUMMARY ===")
        logging.info(f"Total processed: {total_processed}")
        logging.info(f"Opportunities found: {len(opportunities)}")
        logging.info(
            f"Success rate: {len(opportunities)/max(total_processed, 1)*100:.1f}%"
        )
        logging.info(f"\nRejection breakdown:")
        for reason, count in rejection_stats.items():
            if count > 0:
                logging.info(f"  {reason.replace('_', ' ').title()}: {count}")

        if opportunities:
            top_opp = opportunities[0]
            logging.warning(
                f"TOP OPPORTUNITY: {top_opp['stock_code']} (Score: {top_opp['total_score']:.0f})"
            )
            logging.info(
                f"  Risk-Reward: {top_opp['risk_reward'].get('risk_reward_ratio', 0):.1f}:1"
            )
            logging.info(
                f"  Risk: {top_opp['risk_reward'].get('risk_percentage', 0):.1f}%"
            )
            logging.info(
                f"  Target: {top_opp['risk_reward'].get('reward_percentage', 0):.1f}%"
            )

        return opportunities

    def get_best_opportunity(
        self,
        stock_universe: List[Dict],
        market_condition: Dict,
        index_data: pd.DataFrame,
        positions: Dict,
    ) -> Optional[Dict]:
        """Get single best opportunity with enhanced metrics"""
        opportunities = self.screen_stocks(
            stock_universe, market_condition, index_data, positions
        )

        if opportunities:
            best = opportunities[0]
            logging.warning(
                f"BEST OPPORTUNITY: {best['stock_code']} (Score: {best['total_score']:.0f}, R:R: {best['risk_reward'].get('risk_reward_ratio', 0):.1f}:1)"
            )
            return best

        return None

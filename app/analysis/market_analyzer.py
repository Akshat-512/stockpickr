#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Market Analysis Module
Enhanced market condition analysis for better decision making
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Optional


class MarketAnalyzer:
    """Analyzes overall market conditions"""

    def __init__(self, api_client):
        self.api = api_client
        self.index_data = None

    def get_index_data(self, refresh: bool = False) -> Optional[pd.DataFrame]:
        """Get market index data (cached)"""
        if self.index_data is None or refresh:
            self.index_data = self.api.get_historical_data_index("NIFTY", days=300)
            if self.index_data is not None and not self.index_data.empty:
                self.index_data = self.api.calculate_indicators(self.index_data)

        return self.index_data

    def get_enhanced_market_condition(self) -> Dict:
        """Get comprehensive market condition analysis"""
        try:
            index_data = self.get_index_data()

            if index_data is None or index_data.empty:
                logging.error("No index data available")
                return self._get_default_condition()

            # Basic market condition
            basic_condition = self._analyze_basic_condition(index_data)

            # Enhanced analysis
            momentum_analysis = self._analyze_momentum_direction(index_data)
            quality_assessment = self._assess_market_quality(
                index_data, basic_condition, momentum_analysis
            )

            # Combine all analysis
            enhanced_condition = {
                **basic_condition,
                **momentum_analysis,
                "market_quality": quality_assessment,
            }

            return enhanced_condition

        except Exception as e:
            logging.error(f"Error in enhanced market analysis: {e}")
            return self._get_default_condition()

    def _analyze_basic_condition(self, index_data: pd.DataFrame) -> Dict:
        """Basic market trend and position analysis"""
        try:
            latest = index_data.iloc[-1]

            # Determine trend
            if len(index_data) >= 200 and not pd.isna(latest.get("sma_200")):
                if (
                    latest["close"] > latest["sma_200"]
                    and latest["sma_50"] > latest["sma_200"]
                ):
                    trend = "bullish"
                elif (
                    latest["close"] < latest["sma_200"]
                    and latest["sma_50"] < latest["sma_200"]
                ):
                    trend = "bearish"
                else:
                    trend = "neutral"
            elif len(index_data) >= 50:
                trend = "bullish" if latest["close"] > latest["sma_50"] else "bearish"
            else:
                trend = "neutral"

            # Position relative to 200-day SMA
            above_200_sma = False
            close_vs_sma200 = 0

            if "sma_200" in latest and not pd.isna(latest["sma_200"]):
                above_200_sma = latest["close"] > latest["sma_200"]
                close_vs_sma200 = ((latest["close"] / latest["sma_200"]) - 1) * 100

            # Volatility assessment
            if "atr" in index_data.columns:
                recent_atr = index_data["atr"].tail(5).mean()
                long_atr = index_data["atr"].tail(20).mean()
                volatility_ratio = recent_atr / long_atr if long_atr > 0 else 1

                if volatility_ratio > 1.3:
                    volatility = "high"
                elif volatility_ratio < 0.7:
                    volatility = "low"
                else:
                    volatility = "normal"
            else:
                volatility = "normal"

            return {
                "trend": trend,
                "above_200_sma": above_200_sma,
                "close_vs_sma200": close_vs_sma200,
                "volatility": volatility,
                "rsi": latest.get("rsi", 50),
            }

        except Exception as e:
            logging.error(f"Error in basic market analysis: {e}")
            return {"trend": "neutral", "above_200_sma": False, "close_vs_sma200": 0}

    def _analyze_momentum_direction(self, index_data: pd.DataFrame) -> Dict:
        """Analyze momentum direction and acceleration"""
        try:
            latest = index_data.iloc[-1]

            # Calculate recent momentum changes
            if len(index_data) >= 11:
                recent_5d = ((latest["close"] / index_data["close"].iloc[-6]) - 1) * 100
                older_5d = (
                    (index_data["close"].iloc[-6] / index_data["close"].iloc[-11]) - 1
                ) * 100

                if recent_5d > older_5d * 1.2:  # 20% faster
                    momentum_direction = "accelerating"
                elif recent_5d < older_5d * 0.7:  # 30% slower
                    momentum_direction = "decelerating"
                else:
                    momentum_direction = "steady"
            else:
                momentum_direction = "unknown"

            # Momentum cascade check
            momentum_cascade = self._check_momentum_cascade(index_data)

            return {
                "momentum_direction": momentum_direction,
                "recent_5d_change": recent_5d if len(index_data) >= 6 else 0,
                "momentum_cascade": momentum_cascade[0],
                "momentum_reason": momentum_cascade[1],
            }

        except Exception as e:
            logging.error(f"Error analyzing momentum: {e}")
            return {"momentum_direction": "unknown", "recent_5d_change": 0}

    def _check_momentum_cascade(self, data: pd.DataFrame) -> tuple:
        """Check if market has bullish momentum structure"""
        try:
            latest = data.iloc[-1]

            required_cols = ["close", "sma_20", "sma_50", "sma_200"]
            for col in required_cols:
                if col not in data.columns or pd.isna(latest[col]):
                    return False, f"Missing {col} data"

            # Perfect cascade
            if (
                latest["close"]
                > latest["sma_20"]
                > latest["sma_50"]
                > latest["sma_200"]
            ):
                return True, "Perfect momentum cascade"

            # Good cascade
            if latest["close"] > latest["sma_20"] > latest["sma_50"]:
                return True, "Good momentum structure"

            # Minimal structure
            if latest["close"] > latest["sma_20"]:
                # Check if 20-day SMA is rising
                if len(data) >= 5:
                    sma_rising = data["sma_20"].iloc[-1] > data["sma_20"].iloc[-5]
                    if sma_rising:
                        return True, "Price above rising SMA-20"

            return False, "Weak momentum structure"

        except Exception as e:
            return False, f"Error: {str(e)}"

    def _assess_market_quality(
        self, index_data: pd.DataFrame, basic_condition: Dict, momentum_analysis: Dict
    ) -> str:
        """Assess overall market quality for trading"""
        try:
            # Quality factors
            quality_score = 0

            # Factor 1: Above 200-day SMA (critical)
            if basic_condition.get("above_200_sma", False):
                quality_score += 3

            # Factor 2: Bullish trend
            if basic_condition.get("trend") == "bullish":
                quality_score += 2

            # Factor 3: Momentum cascade
            if momentum_analysis.get("momentum_cascade", False):
                quality_score += 2

            # Factor 4: Momentum direction
            momentum_dir = momentum_analysis.get("momentum_direction", "unknown")
            if momentum_dir == "accelerating":
                quality_score += 2
            elif momentum_dir == "steady":
                quality_score += 1
            elif momentum_dir == "decelerating":
                quality_score -= 1

            # Factor 5: RSI not extreme
            rsi = basic_condition.get("rsi", 50)
            if 30 < rsi < 70:
                quality_score += 1

            # Factor 6: Recent performance
            recent_change = momentum_analysis.get("recent_5d_change", 0)
            if recent_change > 2:  # Strong recent performance
                quality_score += 1
            elif recent_change < -3:  # Weak recent performance
                quality_score -= 2

            # Determine quality
            if quality_score >= 7:
                return "excellent"
            elif quality_score >= 5:
                return "good"
            elif quality_score >= 3:
                return "fair"
            else:
                return "poor"

        except Exception as e:
            logging.error(f"Error assessing market quality: {e}")
            return "unknown"

    def _get_default_condition(self) -> Dict:
        """Default market condition when analysis fails"""
        return {
            "trend": "neutral",
            "above_200_sma": False,
            "close_vs_sma200": 0,
            "volatility": "unknown",
            "momentum_direction": "unknown",
            "recent_5d_change": 0,
            "momentum_cascade": False,
            "momentum_reason": "No data",
            "market_quality": "poor",
            "rsi": 50,
        }

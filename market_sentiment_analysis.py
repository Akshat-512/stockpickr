#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart LLM Integration for Stock Screening
Using local Ollama for qualitative analysis while keeping quantitative decisions
"""

import requests
import json
import logging
import re
from typing import Dict, List, Optional
import feedparser
import yfinance as yf
from datetime import datetime, timedelta


class LocalLLMAnalyzer:
    """
    Smart LLM integration for qualitative stock analysis
    Uses local Ollama for privacy and cost-effectiveness
    """

    def __init__(self, ollama_url="http://localhost:11434", model="llama3.2:latest"):
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = 30  # 30 second timeout

    def _call_ollama(self, prompt: str, max_tokens: int = 200) -> str:
        """Call local Ollama API with error handling"""
        try:
            logging.info(f"Sending request to Ollama with model: {self.model}")
            headers = {"Content-Type": "application/json"}
            data = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.3,
                },
            }

            logging.debug(f"Request data: {json.dumps(data, indent=2)}")

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=data,
                headers=headers,
                timeout=self.timeout,
            )

            logging.info(f"Ollama response status: {response.status_code}")

            if response.status_code == 200:
                response_data = response.json()
                logging.debug(f"Ollama response: {json.dumps(response_data, indent=2)}")
                return response_data.get("response", "")
            else:
                error_msg = (
                    f"Ollama API error ({response.status_code}): {response.text}"
                )
                logging.error(error_msg)
                return ""

        except requests.exceptions.RequestException as e:
            error_msg = f"Ollama connection error: {str(e)}"
            logging.error(error_msg)
            return ""
        except Exception as e:
            error_msg = f"Unexpected error in _call_ollama: {str(e)}"
            logging.error(error_msg, exc_info=True)
            return ""

    def analyze_news_sentiment(self, stock_code: str, max_headlines: int = 5) -> Dict:
        """
        Analyze recent news sentiment for a stock
        Returns sentiment score and key themes
        """
        try:
            # Get recent news headlines
            headlines = self._get_recent_headlines(stock_code, max_headlines)
            # logging.info(
            #     f"Analyzing sentiment for {stock_code} with headlines: {headlines}"
            # )

            if not headlines:
                return {"sentiment": "NEUTRAL", "confidence": 0, "themes": []}

            prompt = f"""
            Analyze the sentiment of these recent news headlines for {stock_code} stock.
            Consider the overall tone, specific events, and market implications.
            
            Headlines:
            {chr(10).join([f"- {h}" for h in headlines])}
            
            Provide your analysis in this exact format (include all sections):
            
            SENTIMENT: [POSITIVE/NEGATIVE/NEUTRAL]
            CONFIDENCE: [0-100]
            KEY_THEMES: [comma-separated list of 2-3 key themes or topics]
            
            Be specific and focus on actionable insights. If unsure, mark as NEUTRAL with 50 confidence.
            """

            # logging.info(f"Sending prompt to LLM: {prompt}")
            response = self._call_ollama(prompt, max_tokens=200)
            logging.info(f"Received LLM response: {response}")

            result = self._parse_sentiment_response(response)
            logging.info(f"Parsed sentiment result: {result}")
            return result

        except Exception as e:
            logging.error(
                f"Error analyzing sentiment for {stock_code}: {e}", exc_info=True
            )
            return {"sentiment": "NEUTRAL", "confidence": 0, "themes": []}

    def analyze_earnings_tone(self, stock_code: str, transcript_snippet: str) -> Dict:
        """
        Analyze management tone from earnings calls
        Focus on confidence and guidance
        """
        try:
            prompt = f"""
            Analyze this earnings call snippet for {stock_code}:
            
            "{transcript_snippet}"
            
            Evaluate:
            1. Management confidence level (LOW/MEDIUM/HIGH)
            2. Future outlook tone (PESSIMISTIC/NEUTRAL/OPTIMISTIC) 
            3. Key concerns mentioned
            
            Format:
            CONFIDENCE: [LOW/MEDIUM/HIGH]
            OUTLOOK: [PESSIMISTIC/NEUTRAL/OPTIMISTIC]
            CONCERNS: [brief list]
            """

            response = self._call_ollama(prompt, max_tokens=200)
            return self._parse_earnings_response(response)

        except Exception as e:
            logging.warning(f"Error analyzing earnings for {stock_code}: {e}")
            return {"confidence": "MEDIUM", "outlook": "NEUTRAL", "concerns": []}

    def sector_narrative_analysis(self, sector: str) -> Dict:
        """
        Analyze broader sector narratives and themes
        Useful for sector rotation strategies
        """
        try:
            prompt = f"""
            Analyze the current market narrative for {sector} sector in Indian markets.
            
            Consider:
            1. Recent regulatory changes
            2. Economic factors affecting the sector
            3. Global trends impact
            4. Investment themes
            
            Provide:
            SECTOR_OUTLOOK: [BULLISH/BEARISH/NEUTRAL]
            KEY_DRIVERS: [driver1, driver2, driver3]
            RISKS: [risk1, risk2]
            
            Keep analysis current and India-focused.
            """

            response = self._call_ollama(prompt, max_tokens=250)
            print("Sector response: ", response)
            return self._parse_sector_response(response)

        except Exception as e:
            logging.warning(f"Error analyzing sector {sector}: {e}")
            return {"outlook": "NEUTRAL", "drivers": [], "risks": []}

    def _get_recent_headlines(self, stock_code: str, max_headlines: int) -> List[str]:
        """
        Get recent news headlines for a stock from multiple sources.

        Args:
            stock_code (str): The stock ticker (e.g., "RELIANCE.NS")
            max_headlines (int): Maximum number of headlines to return

        Returns:
            List[str]: List of news headlines
        """
        # Clean stock code (remove .NS for searching)
        # clean_code = stock_code.replace(".NS", "")
        headlines = []

        # Try Yahoo Finance first
        try:
            ticker = yf.Ticker(stock_code)
            logging.info(f"Fetching news for ticker: {stock_code}")

            # Get news using the get_news() method
            try:
                news = ticker.get_news()
                logging.info(f"Found {len(news)} total news items from Yahoo Finance")

                # Process news items
                for i, item in enumerate(news):
                    if not isinstance(item, dict):
                        continue

                    # Try to extract content in order of preference
                    content = None
                    if "content" in item and item["content"]:
                        content = item["content"]
                    elif "summary" in item and item["summary"]:
                        content = item["summary"]
                    elif "title" in item and item["title"]:
                        content = item["title"]

                    if content:
                        # Convert content to string for consistent processing
                        content_str = str(content).lower()
                        stock_lower = stock_code.lower()

                        # Define company name variations for matching
                        # company_variations = {
                        #     "RELIANCE.NS": ["reliance", "reliance industries", "ril"],
                        #     "TCS.NS": [
                        #         "tcs",
                        #         "tata consultancy",
                        #         "tata consultancy services",
                        #     ],
                        #     "HDFCBANK.NS": ["hdfc bank", "hdfc", "hdfc bank ltd"],
                        # }

                        # # Check for matches
                        # matches = (
                        #     stock_lower in content_str  # Exact stock code match
                        #     or stock_lower.replace(".ns", "")
                        #     in content_str  # Without .NS
                        #     or any(
                        #         variation in content_str
                        #         for variation in company_variations.get(
                        #             stock_code.upper(), []
                        #         )
                        #     )  # Company name variations
                        # )
                        headline = item.get("title", str(content))
                        # logging.info(f"Found headline: {headline}")
                        headlines.append(headline)
                        if len(headlines) >= max_headlines:
                            break
            except Exception as e:
                logging.warning(f"Error getting news: {e}")
                news = []

            # Process news items
            for item in news[:max_headlines]:
                title = item.get("title", "").strip()
                if title and (stock_code.lower() in title.lower()):
                    headlines.append(title)
                    if len(headlines) >= max_headlines:
                        break

            if headlines:
                logging.info(
                    f"Found {len(headlines)} relevant headlines from Yahoo Finance for {stock_code}"
                )
                return headlines

            logging.info(
                f"No relevant headlines found in {len(news)} news items for {stock_code}"
            )
        except Exception as e:
            logging.warning(f"Yahoo Finance failed for {stock_code}: {e}")

        # Try MoneyControl RSS feed
        try:
            search_url = (
                "https://www.moneycontrol.com/rss/buzzingstocks.xml"  # Valid RSS feed
            )
            feed = feedparser.parse(search_url)
            for entry in feed.entries[:max_headlines]:
                title = entry.get("title", "").strip()
                if title and stock_code.lower() in title.lower():
                    headlines.append(title)
                    if len(headlines) >= max_headlines:
                        break
            if headlines:
                logging.info(
                    f"Found {len(headlines)} headlines from MoneyControl for {stock_code}"
                )
                return headlines
        except Exception as e:
            logging.warning(f"MoneyControl RSS failed for {stock_code}: {e}")

        # Try Economic Times RSS
        try:
            et_url = "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"
            feed = feedparser.parse(et_url)
            for entry in feed.entries[:max_headlines]:
                title = entry.get("title", "").strip()
                if title and stock_code.lower() in title.lower():
                    headlines.append(title)
                    if len(headlines) >= max_headlines:
                        break
            if headlines:
                logging.info(
                    f"Found {len(headlines)} headlines from Economic Times for {stock_code}"
                )
                return headlines
        except Exception as e:
            logging.warning(f"Economic Times RSS failed for {stock_code}: {e}")

        # If no headlines are found
        logging.info(f"No real news found for {stock_code}")
        return []

    def _parse_sentiment_response(self, response: str) -> Dict:
        """Parse LLM sentiment analysis response"""
        result = {"sentiment": "NEUTRAL", "confidence": 50, "themes": []}

        if not response:
            logging.warning("Empty response from LLM")
            return result

        try:
            # Clean up the response by removing any extra whitespace and normalizing newlines
            lines = [line.strip() for line in response.split("\n") if line.strip()]

            # Process each line to find the key components
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Check for sentiment
                if line.upper().startswith("SENTIMENT:"):
                    sentiment = line.split(":", 1)[1].strip().upper()
                    if sentiment in ["POSITIVE", "NEGATIVE", "NEUTRAL"]:
                        result["sentiment"] = sentiment

                # Check for confidence
                elif line.upper().startswith("CONFIDENCE:"):
                    try:
                        confidence = int(line.split(":", 1)[1].strip())
                        if 0 <= confidence <= 100:
                            result["confidence"] = confidence
                    except (ValueError, IndexError):
                        pass

                # Check for themes - this might be a multi-line section
                elif line.upper().startswith("KEY_THEMES:"):
                    # Get everything after KEY_THEMES:
                    themes_str = line.split(":", 1)[1].strip()

                    # If themes are on subsequent lines, include them
                    next_line_idx = lines.index(line) + 1
                    while next_line_idx < len(lines) and not any(
                        lines[next_line_idx].upper().startswith(x)
                        for x in ["SENTIMENT:", "CONFIDENCE:", "ANALYSIS:"]
                    ):
                        themes_str += " " + lines[next_line_idx].strip()
                        next_line_idx += 1

                    # Clean up and parse themes
                    themes_str = themes_str.strip()
                    if themes_str:
                        # Remove any trailing Analysis: or other markers
                        for marker in ["ANALYSIS:", "Analysis:"]:
                            if marker in themes_str:
                                themes_str = themes_str.split(marker)[0].strip()

                        # Handle different theme formats
                        if '"' in themes_str or "'" in themes_str:
                            # Handle quoted themes
                            try:
                                import shlex

                                themes = [
                                    t.strip("'\"")
                                    for t in shlex.split(themes_str)
                                    if t.strip()
                                ]
                            except Exception as e:
                                logging.warning(f"Error parsing quoted themes: {e}")
                                themes = [
                                    t.strip("\"' ")
                                    for t in themes_str.split(",")
                                    if t.strip()
                                ]
                        else:
                            # Simple comma-separated themes
                            themes = [
                                t.strip() for t in themes_str.split(",") if t.strip()
                            ]

                        # Clean and deduplicate themes
                        seen = set()
                        result["themes"] = []
                        for theme in themes:
                            clean_theme = theme.strip("\"' ,.-_")
                            if clean_theme and clean_theme.lower() not in seen:
                                seen.add(clean_theme.lower())
                                result["themes"].append(clean_theme)

                        # Limit to top 3 themes
                        result["themes"] = result["themes"][:3]
                        logging.debug(f"Parsed themes: {result['themes']}")
                    break  # Found themes, no need to process more lines

        except Exception as e:
            logging.error(f"Error parsing sentiment response: {e}", exc_info=True)

        return result

    def _parse_earnings_response(self, response: str) -> Dict:
        """Parse earnings analysis response"""
        result = {"confidence": "MEDIUM", "outlook": "NEUTRAL", "concerns": []}

        try:
            lines = response.strip().split("\n")

            for line in lines:
                line = line.strip()
                if line.startswith("CONFIDENCE:"):
                    confidence = line.split(":", 1)[1].strip().upper()
                    if confidence in ["LOW", "MEDIUM", "HIGH"]:
                        result["confidence"] = confidence

                elif line.startswith("OUTLOOK:"):
                    outlook = line.split(":", 1)[1].strip().upper()
                    if outlook in ["PESSIMISTIC", "NEUTRAL", "OPTIMISTIC"]:
                        result["outlook"] = outlook

                elif line.startswith("CONCERNS:"):
                    concerns_str = line.split(":", 1)[1].strip()
                    concerns = [c.strip() for c in concerns_str.split(",")]
                    result["concerns"] = [c for c in concerns if c]

        except Exception as e:
            logging.warning(f"Error parsing earnings response: {e}")

        return result

    def _parse_sector_response(self, response: str) -> Dict:
        """Parse sector analysis response"""
        result = {"outlook": "NEUTRAL", "drivers": [], "risks": []}

        try:
            lines = response.strip().split("\n")

            for line in lines:
                line = line.strip()
                if line.startswith("SECTOR_OUTLOOK:"):
                    outlook = line.split(":", 1)[1].strip().upper()
                    if outlook in ["BULLISH", "BEARISH", "NEUTRAL"]:
                        result["outlook"] = outlook

                elif line.startswith("KEY_DRIVERS:"):
                    drivers_str = line.split(":", 1)[1].strip()
                    drivers = [d.strip() for d in drivers_str.split(",")]
                    result["drivers"] = [d for d in drivers if d][:3]  # Max 3

                elif line.startswith("RISKS:"):
                    risks_str = line.split(":", 1)[1].strip()
                    risks = [r.strip() for r in risks_str.split(",")]
                    result["risks"] = [r for r in risks if r][:2]  # Max 2

        except Exception as e:
            logging.warning(f"Error parsing sector response: {e}")

        return result


class SmartScreeningWithLLM:
    """
    Integrate LLM analysis with quantitative screening
    LLM provides qualitative overlay, not trading decisions
    """

    def __init__(self, llm_analyzer: LocalLLMAnalyzer):
        self.llm = llm_analyzer
        self.sentiment_cache = {}  # Cache to avoid repeated calls

    def enhanced_stock_screening(
        self, quantitative_opportunities: List[Dict]
    ) -> List[Dict]:
        """
        Add LLM-based qualitative analysis to quantitative screening results

        Args:
            quantitative_opportunities: Results from your existing screening

        Returns:
            Enhanced opportunities with sentiment scores
        """
        enhanced_opportunities = []

        for opp in quantitative_opportunities:
            stock_code = opp["stock_code"]

            try:
                # Add sentiment analysis
                sentiment_data = self._get_cached_sentiment(stock_code)

                # Calculate sentiment adjustment
                sentiment_adjustment = self._calculate_sentiment_adjustment(
                    sentiment_data
                )

                # Apply adjustment to existing score
                original_score = opp.get("overall_score", opp.get("risk_reward", 0))
                adjusted_score = original_score + sentiment_adjustment

                # Create enhanced opportunity
                enhanced_opp = opp.copy()
                enhanced_opp.update(
                    {
                        "sentiment": sentiment_data["sentiment"],
                        "sentiment_confidence": sentiment_data["confidence"],
                        "sentiment_themes": sentiment_data["themes"],
                        "sentiment_adjustment": sentiment_adjustment,
                        "final_score": adjusted_score,
                        "llm_analysis_timestamp": datetime.now().isoformat(),
                    }
                )

                enhanced_opportunities.append(enhanced_opp)

            except Exception as e:
                logging.warning(f"Error enhancing {stock_code} with LLM: {e}")
                # Fallback: use original opportunity without LLM enhancement
                enhanced_opportunities.append(opp)

        # Re-sort by final score
        enhanced_opportunities.sort(key=lambda x: x.get("final_score", 0), reverse=True)

        return enhanced_opportunities

    def _get_cached_sentiment(self, stock_code: str) -> Dict:
        """Get sentiment with caching to avoid repeated API calls"""
        cache_key = f"{stock_code}_{datetime.now().strftime('%Y%m%d')}"

        if cache_key not in self.sentiment_cache:
            sentiment_data = self.llm.analyze_news_sentiment(stock_code)
            self.sentiment_cache[cache_key] = sentiment_data

        return self.sentiment_cache[cache_key]

    def _calculate_sentiment_adjustment(self, sentiment_data: Dict) -> float:
        """
        Convert sentiment analysis to numerical adjustment
        Conservative approach - small adjustments only
        """
        sentiment = sentiment_data.get("sentiment", "NEUTRAL")
        confidence = sentiment_data.get("confidence", 0)

        # Base adjustment (small to avoid over-weighting sentiment)
        if sentiment == "POSITIVE" and confidence > 70:
            return 2.0  # Small positive boost
        elif sentiment == "POSITIVE" and confidence > 50:
            return 1.0
        elif sentiment == "NEGATIVE" and confidence > 70:
            return -2.0  # Small negative adjustment
        elif sentiment == "NEGATIVE" and confidence > 50:
            return -1.0
        else:
            return 0.0  # Neutral or low confidence

    def sector_rotation_insight(self, sectors: List[str]) -> Dict[str, Dict]:
        """
        Get LLM insights on sector rotation
        Helps prioritize which sectors to focus screening on
        """
        sector_insights = {}

        for sector in sectors:
            try:
                analysis = self.llm.sector_narrative_analysis(sector)
                sector_insights[sector] = analysis
            except Exception as e:
                logging.warning(f"Error analyzing sector {sector}: {e}")
                sector_insights[sector] = {
                    "outlook": "NEUTRAL",
                    "drivers": [],
                    "risks": [],
                }

        return sector_insights


# Integration with your existing trader.py
def integrate_llm_with_existing_screening():
    """
    Example integration with your existing screen_stocks function
    """
    integration_example = '''
    # Add to your trader.py
    
    # Initialize LLM analyzer (only if Ollama is running)
    try:
        llm_analyzer = LocalLLMAnalyzer()
        smart_screening = SmartScreeningWithLLM(llm_analyzer)
        USE_LLM = True
        logging.info("LLM analyzer initialized successfully")
    except:
        USE_LLM = False
        logging.warning("LLM analyzer not available, using quantitative-only screening")
    
    def screen_stocks_with_llm(stock_universe, market_condition, max_stocks=5):
        """Enhanced screening with optional LLM analysis"""
        
        # Step 1: Run your existing quantitative screening
        quantitative_opportunities = screen_stocks(stock_universe, market_condition, max_stocks)
        
        # Step 2: Add LLM analysis if available
        if USE_LLM and quantitative_opportunities:
            try:
                enhanced_opportunities = smart_screening.enhanced_stock_screening(quantitative_opportunities)
                logging.info(f"Enhanced {len(enhanced_opportunities)} opportunities with LLM analysis")
                return enhanced_opportunities
            except Exception as e:
                logging.warning(f"LLM enhancement failed: {e}, using quantitative results")
        
        # Fallback: return quantitative results
        return quantitative_opportunities
    '''

    return integration_example


# Example usage and testing
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("sentiment_analysis.log"),
        ],
    )

    logger = logging.getLogger(__name__)

    # Test LLM connectivity
    try:
        logger.info("Starting sentiment analysis test...")
        llm = LocalLLMAnalyzer()

        # Test with multiple stocks for better debugging
        test_stocks = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]

        for stock in test_stocks:
            logger.info(f"\n{'='*50}")
            logger.info(f"Testing sentiment analysis for {stock}")
            logger.info(f"{'='*50}")

            # Test sentiment analysis
            test_sentiment = llm.analyze_news_sentiment(stock, max_headlines=5)
            logger.info("\nSentiment Analysis Results:")
            logger.info(f"Stock: {stock}")
            logger.info(f"Sentiment: {test_sentiment['sentiment']}")
            logger.info(f"Confidence: {test_sentiment['confidence']}")
            logger.info(
                f"Themes: {', '.join(test_sentiment['themes']) if test_sentiment['themes'] else 'None'}"
            )

            # Small delay between requests
            import time

            time.sleep(2)

        # Test sector analysis
        LlmSmartScreening = SmartScreeningWithLLM(llm)
        logger.info("\nTesting sector analysis...")
        test_sector = LlmSmartScreening.sector_rotation_insight(
            ["Technology", "Banking", "Pharma", "Auto", "Energy", "IT"]
        )
        logger.info("\nSector Analysis Results:")
        logger.info(f"Sector: Technology")
        logger.info(f"Outlook: {test_sector['Technology']['outlook']}")
        logger.info(
            f"Drivers: {', '.join(test_sector['Technology']['drivers']) if test_sector['Technology']['drivers'] else 'None'}"
        )
        logger.info(
            f"Risks: {', '.join(test_sector['Technology']['risks']) if test_sector['Technology']['risks'] else 'None'}"
        )

    except Exception as e:
        logger.error(f"LLM test failed: {e}", exc_info=True)
        logger.error("Make sure Ollama is running: ollama serve")
    finally:
        logger.info("\nTest completed. Check sentiment_analysis.log for detailed logs.")

# Trading System for ICICI Direct Breeze API

## 📋 Overview
A Python-based automated trading system that connects to ICICI Direct's Breeze API to execute trades based on technical indicators and risk management rules.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- ICICI Direct trading account with API access

### Installation
1. Clone the repository
2. Create and activate virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure your API credentials in `config.ini`

### Usage
#### Run as a service:
```bash
.service/setup_service.sh
service/trader_service.sh start
```

#### Or run directly:
```bash
python continuous_trading.py
```

## ⚙️ Configuration
Edit `config.ini` to set:
- API credentials (api_key, api_secret, session_token)
- Trading parameters (capital, risk settings)
- Strategy settings (RSI periods, position limits)
- Email notifications

## 📈 Strategy

### Entry Conditions
- RSI-based oversold conditions
- Volume analysis
- Market trend confirmation
- ATR-based position sizing

### Exit Conditions
- Trailing stop losses (2x ATR)
- Time-based exits (max 2 days)
- RSI overbought conditions
- Manual override available

### Risk Management
- 2% risk per trade
- Max 2 concurrent positions
- 20% minimum cash reserve
- 80% maximum portfolio exposure
- Automatic position sizing

## 📊 Performance Tracking
- Detailed trade logging
- Daily performance reports
- Email notifications for important events
- Position tracking in JSON format

## 🔄 Daily Operations
1. **Pre-Market (9:00 AM)**
   - System startup and initialization
   - Market status check
   - Load previous positions

2. **Trading Hours (9:15 AM - 3:30 PM)**
   - 15-minute interval scanning
   - Position management
   - Real-time monitoring

3. **Post-Market (3:30 PM - 4:00 PM)**
   - Close remaining positions
   - Generate daily report
   - Save position data

## 📂 Project Structure
- `trader.py` - Main trading logic
- `config.ini` - Configuration file
- `requirements.txt` - Python dependencies
- `positions/` - Position tracking files
- `logs/` - System and trade logs

## ⚠️ Risk Warning
This is an automated trading system that involves substantial risk of loss. Always test with paper trading before using real capital.

## 📝 License
[Specify License]
Implement statistical monitoring of results
Define clear criteria for strategy adjustments


## Expected Results and Metrics
1. Performance Targets
Win Rate: 55-60%
Average Win: 3-5% per trade
Average Loss: 1.5-2% per trade (controlled by stop loss)
Profit Factor: 1.5+ (total profits / total losses)
2. Capital Growth Benchmarks
Phase 1: ₹5,000 → ₹5,500 (10% growth)
Phase 2: ₹5,500 → ₹6,500 (18% additional growth)
Phase 3: ₹6,500 → ₹8,000 (23% additional growth)
Overall: 60% return in 30 days
3. Risk Management Metrics
Maximum Drawdown Target: <10% of capital
Daily VaR (Value at Risk): <5% of capital
Sharpe Ratio Target: >1.5
Conclusion
The ₹5,000 starter strategy provides a structured approach to building trading capital using the ICICI Direct Breeze API. By focusing on high-probability setups, strict risk management, and a phased growth approach, the system aims to steadily increase capital while protecting against significant drawdowns.

## Starting with a smaller capital base allows for:

Learning the API system with minimal risk
Testing the strategy effectiveness in real market conditions
Building confidence in the approach before scaling up
Creating a track record of consistent results
As the strategy proves successful and capital grows, it can be scaled up systematically toward the ultimate goal of generating ₹10,000 profit from a larger capital base within the 30-day timeframe.


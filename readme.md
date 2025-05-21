## Steps to setup trade4u bot:

1. Create an API Account:
Visit https://api.icicidirect.com/apiuser/home
Login with your ICICI Direct credentials
Click on "Register an App" and follow the prompts
Note your API key and secret key
Generate Session Token:
The system will direct you to login via a URL containing your API key
After login, you'll receive a session token
This token is needed to authenticate API calls

2. setup virtual env
source venv/bin/activate

3. install required packages
pip install -r requirements.txt

4. either run the trader_service in the background : execute .service/setup_service.sh 
use the service using service/trader_service.sh start/stop/status

or

run the continuous_trading.py file - python continuous_trading.py


## What the trading system/ program aims to do:
1. Setup

2. System Initialization
The system follows these steps on startup:

Configuration:
Set up logging to track all system actions
Initialize global variables for capital management
Define risk parameters (max position size, risk per trade)
API Connection:
Create BreezeConnect instance with your API key
Generate session using secret key and session token
Connect to websocket for real-time data
Initial Checks:
Verify market status (open/closed)
Check available capital
Initialize tracking dictionaries for positions

3. Core Strategy Execution
The trading system runs on a 15-minute cycle with the following workflow:

Position Management:
First priority is managing existing positions
Check profit levels and adjust trailing stops if needed
Execute time-based exits for older positions
Opportunity Scanning:
Only scan for new opportunities if:
Current exposure is below 80% of capital
Currently holding fewer than 2 positions
Have sufficient available balance above min reserve
Trade Execution:
For new entries:
Place market buy order
Immediately place stop loss order
Log entry details and update position trackers
For exits:
Cancel existing stop loss order
Place market sell order
Log profit/loss and update capital trackers


4. Risk Management Implementation
The system implements multiple layers of risk management:

Position Level Protection:
ATR-based stop loss placement (2x ATR below entry)
Position size calculated to risk exactly 2% of capital
Maximum position size capped at 50% of capital
Time-based exit after 2 days maximum
Portfolio Level Protection:
Maximum 2 concurrent positions
Minimum 20% cash reserve at all times
Maximum 80% total exposure
Daily review and position closure
System Level Protection:
Comprehensive error handling and logging
Automatic shutdown procedures if errors occur
End-of-day position closure
Regular capital assessment


5. Monitoring and Scaling
As the system generates profits, it follows a phased approach to scaling:

Phase 1 (Days 1-10):
Focus on consistent small wins
Strict adherence to position sizing rules
Target 5% gains with minimal drawdown
Phase 2 (Days 11-20):
Gradually increase position sizes as capital grows
Continue with same stock universe
Slightly more aggressive trailing stops
Phase 3 (Days 21-30):
Leverage accumulated capital for larger positions
Consider expanding to additional stocks if appropriate
More active management of winning positions


6. Performance Tracking
The system maintains detailed logs for performance tracking:

Trade Journal:
Entry and exit prices for all trades
Profit/loss per trade
Reason for entry and exit
Capital Growth:
Daily capital assessment
Cumulative performance tracking
Drawdown measurement
Strategy Effectiveness:
Win/loss ratio
Average profit per winning trade
Average loss per losing trade
Practical Execution Guide
Daily Operations
Morning Setup (9:00 AM):
Start the system before market open
Verify API connection and authentication
Check for any system updates or issues
Trading Hours (9:15 AM - 3:30 PM):
System automatically scans for opportunities every 15 minutes
Manages existing positions in real-time
Logs all activities for review
End of Day (3:30 PM - 4:00 PM):
Close any remaining positions
Generate daily performance report
Prepare for next trading day
Weekly Review
Every weekend, perform a comprehensive review:

## Performance Analysis:

Calculate weekly P&L
Review all trades for adherence to strategy
Identify any issues or opportunities for improvement
Capital Assessment:
Track capital growth against plan
Adjust position sizing if needed
Verify progress toward 30-day goals
System Optimization:
Fine-tune technical parameters if needed
Review stock universe for potential changes
Update risk parameters based on performance
Scaling Up Process
As the strategy proves successful and capital grows, follow this approach to scale up:

Capital Increase Steps:
₹5,000 → ₹8,000 (Phase 1 & 2)
₹8,000 → ₹15,000 (Phase 3)
₹15,000 → ₹30,000
₹30,000 → ₹60,000 (Full deployment)
Position Size Scaling:
Maintain the same risk percentage (2%)
Gradually increase max position size with capital growth
Maintain diversification with multiple positions
Stock Universe Expansion:
Start with 5 stocks (initial ₹5,000)
Expand to 8 stocks (₹15,000+)
Full universe of 10-12 stocks (₹30,000+)



## Potential Challenges and Solutions

1. Execution Slippage
Challenge: Market orders may execute at prices different from expected, affecting stop loss placement.

Solution:

Use limit orders where possible
Account for additional slippage in position sizing
Monitor bid-ask spreads for selected stocks
2. Stop Loss Failures
Challenge: Stop losses may fail to execute in fast-moving markets.

Solution:

Include safety buffer in position sizing calculations
Implement additional monitoring for volatile periods
Have backup exit procedures ready
3. API Connection Issues
Challenge: Connection failures could prevent order execution.

Solution:

Implement robust error handling
Set up automatic reconnection procedures
Monitor connection status actively
4. Strategy Performance Monitoring
Challenge: Determining if the strategy is performing as expected.

Solution:

Set clear performance benchmarks (win rate, avg profit)
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


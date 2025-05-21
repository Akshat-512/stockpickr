#!/bin/bash
# trader_service.sh - Manage the ICICI Trader macOS service

PLIST_NAME="com.user.icicitrader.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
LOG_PATH="$ROOT_DIR/logs/launchd_output.log"
ERROR_LOG_PATH="$ROOT_DIR/logs/launchd_error.log"
TRADER_LOG_PATH="$ROOT_DIR/continuous_trader.log"

# Function to show usage information
show_usage() {
    echo "Usage: $0 [start|stop|restart|status|logs]"
    echo ""
    echo "Commands:"
    echo "  start   - Start the ICICI Trader service"
    echo "  stop    - Stop the ICICI Trader service"
    echo "  restart - Restart the ICICI Trader service"
    echo "  status  - Show the current status of the service"
    echo "  logs    - Display recent log entries"
    echo ""
}

# Check if launch agent plist exists
check_plist() {
    if [ ! -f "$PLIST_PATH" ]; then
        echo "Error: Service plist file not found at $PLIST_PATH"
        echo "Please run the install_service.sh script first."
        exit 1
    fi
}

# Check service status
check_status() {
    if launchctl list | grep "com.user.icicitrader" > /dev/null; then
        echo "Service is running."
        return 0
    else
        echo "Service is not running."
        return 1
    fi
}

# Start service
start_service() {
    check_plist
    echo "Starting ICICI Trader service..."
    launchctl load -w "$PLIST_PATH"
    sleep 2
    check_status
}

# Stop service
stop_service() {
    check_plist
    echo "Stopping ICICI Trader service..."
    launchctl unload -w "$PLIST_PATH"
    sleep 2
    check_status
}

# Restart service
restart_service() {
    stop_service
    start_service
}

# Show logs
show_logs() {
    echo "=== Launch Agent Output Logs ==="
    if [ -f "$LOG_PATH" ]; then
        tail -n 10 "$LOG_PATH"
    else
        echo "Log file not found at $LOG_PATH"
    fi
    
    echo ""
    echo "=== Launch Agent Error Logs ==="
    if [ -f "$ERROR_LOG_PATH" ]; then
        tail -n 10 "$ERROR_LOG_PATH"
    else
        echo "Error log file not found at $ERROR_LOG_PATH"
    fi
    
    echo ""
    echo "=== Trader Application Logs ==="
    if [ -f "$TRADER_LOG_PATH" ]; then
        tail -n 50 "$TRADER_LOG_PATH"
    else
        echo "Trader log file not found at $TRADER_LOG_PATH"
    fi
}

# Process command line arguments
if [ $# -eq 0 ]; then
    show_usage
    exit 0
fi

case "$1" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        check_status
        ;;
    logs)
        show_logs
        ;;
    *)
        show_usage
        exit 1
        ;;
esac

exit 0
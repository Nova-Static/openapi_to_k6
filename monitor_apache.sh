#!/bin/bash
# Apache/PHP Memory Monitoring Script
# Run this while your k6 load test is running

echo "Apache/PHP Memory Monitor"
echo "========================"
echo "Press Ctrl+C to stop"
echo ""

# Function to display process info
show_processes() {
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="
    echo ""
    
    # Apache processes
    echo "--- Apache Processes (RES memory in KB) ---"
    ps aux | grep -E 'apache2|httpd' | grep -v grep | awk '{printf "PID: %-8s RES: %8s KB (%.1f MB)  CMD: %s\n", $2, $6, $6/1024, $11}' | sort -k3 -rn | head -10
    echo ""
    
    # PHP-FPM processes (if using PHP-FPM)
    if pgrep -x php-fpm > /dev/null; then
        echo "--- PHP-FPM Processes (RES memory in KB) ---"
        ps aux | grep php-fpm | grep -v grep | awk '{printf "PID: %-8s RES: %8s KB (%.1f MB)  CMD: %s\n", $2, $6, $6/1024, $11}' | sort -k3 -rn | head -10
        echo ""
    fi
    
    # Total memory usage
    echo "--- Total Memory Usage ---"
    ps aux | grep -E 'apache2|httpd|php-fpm' | grep -v grep | awk '{sum+=$6} END {printf "Total RES: %d KB (%.1f MB)\n", sum, sum/1024}'
    echo ""
    
    # Apache status (if mod_status is enabled)
    if command -v curl > /dev/null; then
        echo "--- Apache Server Status (if mod_status enabled) ---"
        curl -s http://localhost/server-status 2>/dev/null | grep -E "Total accesses|Total kBytes|CPU|ReqPerSec|BytesPerSec|BusyWorkers|IdleWorkers" | head -10 || echo "mod_status not available or not accessible"
        echo ""
    fi
}

# Continuous monitoring
if [ "$1" == "--continuous" ] || [ "$1" == "-c" ]; then
    while true; do
        clear
        show_processes
        sleep 5
    done
else
    show_processes
fi


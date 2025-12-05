#!/bin/bash
# Track memory growth of Apache/PHP processes over time
# This helps identify which processes are leaking memory

OUTPUT_FILE="memory_growth_$(date +%Y%m%d_%H%M%S).csv"
INTERVAL=${1:-5}  # Default 5 seconds

echo "Tracking memory growth..."
echo "Output file: $OUTPUT_FILE"
echo "Interval: ${INTERVAL} seconds"
echo "Press Ctrl+C to stop"
echo ""

# CSV header
echo "timestamp,pid,res_kb,res_mb,command" > "$OUTPUT_FILE"

# Function to log process memory
log_processes() {
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    ps aux | grep -E 'apache2|httpd|php-fpm' | grep -v grep | while read line; do
        pid=$(echo "$line" | awk '{print $2}')
        res_kb=$(echo "$line" | awk '{print $6}')
        res_mb=$(echo "scale=2; $res_kb/1024" | bc)
        cmd=$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/ $//')
        echo "$timestamp,$pid,$res_kb,$res_mb,\"$cmd\"" >> "$OUTPUT_FILE"
    done
}

# Signal handler
trap 'echo ""; echo "Stopped. Data saved to $OUTPUT_FILE"; exit' INT TERM

# Main loop
while true; do
    log_processes
    sleep "$INTERVAL"
done


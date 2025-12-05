# Debugging Apache/PHP Memory Leaks During Load Testing

## Quick Monitoring

Run the monitoring script while your k6 test is running:

```bash
# One-time snapshot
./monitor_apache.sh

# Continuous monitoring (updates every 5 seconds)
./monitor_apache.sh --continuous
```

## Common Causes of Memory Growth

### 1. PHP Memory Leaks
- **Symptoms**: RES keeps growing, never decreases
- **Check**: PHP error logs, memory_limit settings
- **Tools**: 
  - `strace -p <PID>` to see system calls
  - `valgrind --leak-check=full` (development only)

### 2. Apache KeepAlive Connections
- **Symptoms**: Many connections stay open
- **Check**: `netstat -an | grep :80 | wc -l`
- **Fix**: Adjust `KeepAlive` and `MaxKeepAliveRequests` in Apache config

### 3. PHP-FPM Process Management
- **Symptoms**: Too many PHP processes, each consuming memory
- **Check**: PHP-FPM pool config (`pm.max_children`, `pm.max_requests`)
- **Fix**: Set `pm.max_requests` to recycle processes periodically

### 4. Symfony Cache/Doctrine
- **Symptoms**: Memory grows with request count
- **Check**: Symfony profiler, Doctrine query cache
- **Fix**: Clear cache between requests, limit query result caching

## Detailed Debugging Steps

### Step 1: Monitor Process Memory Over Time

```bash
# Log memory usage to file
while true; do
    echo "$(date): $(ps aux | grep apache2 | grep -v grep | awk '{sum+=$6} END {print sum/1024 " MB"}')" >> memory_log.txt
    sleep 1
done
```

### Step 2: Check Apache Configuration

```bash
# Check Apache config for memory-related settings
apache2ctl -S
apache2ctl -M | grep -E 'worker|prefork|event'
```

Key settings to check:
- `MaxRequestWorkers` / `MaxClients`
- `ThreadsPerChild`
- `MaxConnectionsPerChild` (should be > 0 to recycle processes)

### Step 3: Check PHP Configuration

```bash
# Check PHP memory settings
php -i | grep -E 'memory_limit|max_execution_time'
```

Key settings:
- `memory_limit` - per-request limit
- `max_execution_time` - request timeout
- PHP-FPM `pm.max_requests` - recycle workers after N requests

### Step 4: Enable Apache Error Logging

Add to Apache config:
```apache
LogLevel debug
ErrorLog /var/log/apache2/error.log
```

### Step 5: Monitor with System Tools

```bash
# Real-time process monitoring
top -p $(pgrep -d',' apache2)

# Or use htop for better visualization
htop -p $(pgrep -d',' apache2)

# Monitor system calls
strace -p <PID> -e trace=mmap,munmap,brk 2>&1 | grep -E 'mmap|munmap|brk'
```

### Step 6: Check for Memory Leaks in PHP Code

Enable Xdebug or use Blackfire:

```bash
# Install Xdebug (development)
pecl install xdebug

# Or use Blackfire for profiling
blackfire curl http://localhost/your-endpoint
```

### Step 7: Check Symfony Profiler

If Symfony profiler is enabled in production (not recommended), disable it:
```php
// config/packages/dev/web_profiler.yaml
web_profiler:
    toolbar: false
    intercept_redirects: false
```

### Step 8: Monitor Database Connections

```bash
# Check MySQL connections
mysql -e "SHOW PROCESSLIST;"

# Check PostgreSQL connections
psql -c "SELECT count(*) FROM pg_stat_activity;"
```

## Quick Fixes to Try

1. **Restart Apache workers periodically**:
   ```apache
   MaxConnectionsPerChild 1000
   ```

2. **Limit PHP-FPM workers**:
   ```ini
   pm.max_children = 50
   pm.max_requests = 500  # Recycle after 500 requests
   ```

3. **Disable OPcache in development** (if causing issues):
   ```ini
   opcache.enable=0
   ```

4. **Clear Symfony cache between tests**:
   ```bash
   php bin/console cache:clear
   ```

5. **Reduce KeepAlive timeout**:
   ```apache
   KeepAlive On
   KeepAliveTimeout 2
   MaxKeepAliveRequests 100
   ```

## Advanced: Memory Profiling

### Using Valgrind (Development Only)
```bash
valgrind --leak-check=full --show-leak-kinds=all \
  --track-origins=yes apache2 -X
```

### Using PHP Memory Profiler
```bash
# Install memprof extension
pecl install memprof

# Enable in php.ini
extension=memprof.so
memprof.enabled=1
```

## Monitoring During k6 Test

Run these in separate terminals:

```bash
# Terminal 1: Run k6 test
k6 run test.js

# Terminal 2: Monitor memory
./monitor_apache.sh --continuous

# Terminal 3: Monitor connections
watch -n 1 'netstat -an | grep :80 | wc -l'

# Terminal 4: Monitor Apache access logs
tail -f /var/log/apache2/access.log
```

## Expected Behavior

- **Normal**: Memory increases during load, then stabilizes or decreases when load stops
- **Problem**: Memory continuously increases and never decreases, even after load stops

If memory never decreases after stopping the load test, you likely have a memory leak in:
1. PHP code (unclosed resources, circular references)
2. Symfony/Doctrine caching
3. Apache module configuration
4. PHP extensions


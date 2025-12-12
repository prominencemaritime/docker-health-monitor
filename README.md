# Multi-Project Docker Health Monitor

A centralized health monitoring system that watches all Docker containers with healthchecks across multiple projects and sends email alerts when containers become unhealthy.

**Complete Guide:** See [README_LONG.md](README_LONG.md) for comprehensive documentation

## Quickstart
```bash
# From your master folder containing all alert projects
cd /srv/repos/alerts
mkdir -p _docker_health_monitor/logs
cp /path/to/docker_health_monitor.py _docker_health_monitor/
cd _docker_health_monitor

# Create .env file with your SMTP settings
vim .env
chmod 600 .env

# Install dependencies and test
pip3 install docker python-decouple --break-system-packages
python3 docker_health_monitor.py

# When working correctly, install as systemd service
sudo vim /etc/systemd/system/docker-health-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now docker-health-monitor
sudo systemctl status docker-health-monitor
```

## Quick Configuration

Create `.env` file:
```bash
# Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your-email@example.com
SMTP_PASS=your-app-password

# Alert Recipients (required)
HEALTH_CHECK_ALERT_EMAILS=ops-team@example.com,admin@example.com

# Optional: Project-specific routing
CONTAINER_ALERT_ROUTING=passage-plan:maritime@ex.com;vessel-cert:compliance@ex.com

# Monitoring Configuration
HEALTH_CHECK_INTERVAL_SEC=30        # Check every 30 seconds
WAIT_AND_CHECK_AGAIN_MIN=10         # Wait 10 min before alerting (filters transients)
HEALTH_USE_BACKOFF=false            # Simple retry (set true for exponential backoff)
HEALTH_MAX_ATTEMPTS=1               # One retry before alert
MONITOR_MAX_WORKERS=30              # Parallel worker threads (scales to 50+ containers)
HEALTH_CHECK_LOG_LINES=50
SERVER_NAME=Production Server
MONITOR_LOG_FILE=/srv/repos/alerts/_docker_health_monitor/logs/monitor.log
```

### Advanced Settings (Optional)

For larger deployments or flapping containers:
```bash
# Enable these for more sophisticated retry behavior
WAIT_AND_CHECK_AGAIN_MIN=5          # Faster first check
HEALTH_USE_BACKOFF=true             # Exponential backoff (5min → 10min → 20min)
HEALTH_MAX_ATTEMPTS=3               # Multiple retries
HEALTH_BACKOFF_MULTIPLIER=2.0
HEALTH_BACKOFF_MAX_MIN=30.0
HEALTH_RETRY_JITTER_SEC=5.0
```

## How It Works

**Smart Retry Logic (Reduces False Positives):**
1. Container becomes unhealthy at 12:00
2. Monitor waits 10 minutes (configurable)
3. Re-checks at 12:10
4. Only sends alert if still unhealthy
5. Prevents alerts for transient failures

**Key Features:**
- ✓ Parallel container checks (fast even with 50+ containers)
- ✓ Thread-safe state management
- ✓ Prevents duplicate retry tasks
- ✓ Configurable retry strategy (simple or exponential backoff)
- ✓ Graceful shutdown (waits for pending checks)
- ✓ Auto-discovers new containers
- ✓ Project-aware alerting

## Systemd Service

Create `/etc/systemd/system/docker-health-monitor.service`:
```ini
[Unit]
Description=Multi-Project Docker Health Monitor
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=prominence
Group=prominence
WorkingDirectory=/srv/repos/alerts/_docker_health_monitor
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 /srv/repos/alerts/_docker_health_monitor/docker_health_monitor.py
Restart=always
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now docker-health-monitor
```

## Quick Commands
```bash
# View container health status
docker ps --format "table {{.Names}}\t{{.Status}}"

# View only unhealthy containers
docker ps --filter health=unhealthy

# Check specific container health
docker inspect <container-name> --format='{{.State.Health.Status}}'

# View monitor logs
tail -f /srv/repos/alerts/_docker_health_monitor/logs/monitor.log

# Restart monitor
sudo systemctl restart docker-health-monitor
```

## Per-Project Health Monitoring Setup

Each alert project needs health status monitoring configured.

### Files to Modify

**Required for all projects:**
1. `src/core/base_alert.py` - Writes health status after each run
2. `Dockerfile` - Reads health status in HEALTHCHECK

**Additional for time-based scheduling (SCHEDULE_TIMES):**
3. `src/core/scheduler.py` - Writes health after scheduler runs
4. `src/main.py` - Passes logs_dir to scheduler

### Quick Setup (Frequency-Based Projects)

**1. Update `src/core/base_alert.py`:**

Add import:
```python
from pathlib import Path
```

Add method after `_send_notifications`:
```python
def _write_health_status(self, status: str, run_time: datetime, error_msg: str = "") -> None:
    """Write health status for Docker healthcheck."""
    try:
        health_file = Path("/app/logs/health_status.txt")
        health_file.parent.mkdir(parents=True, exist_ok=True)
        with open(health_file, 'w') as f:
            f.write(f"{status} {run_time.isoformat()}\n")
            if error_msg:
                f.write(f"ERROR_MSG: {error_msg}\n")
        self.logger.debug(f"Health status written: {status}")
    except Exception as e:
        self.logger.error(f"Failed to write health status: {e}")
```

Add health writes in `run()` method:
```python
# After successful notifications
self._write_health_status("OK", run_time)

# In exception handler
self._write_health_status("ERROR", run_time, str(e))

# Before each early return False (3 locations)
self._write_health_status("OK", run_time)
```

**2. Update `Dockerfile`:**

Replace HEALTHCHECK with:
```dockerfile
HEALTHCHECK --interval=30m --timeout=10s --start-period=30s --retries=3 \
  CMD test -f /app/logs/health_status.txt && \
      MINUTES=$(python3 -c "import os; schedule_times = os.getenv('SCHEDULE_TIMES', ''); print(1440 if schedule_times else int(float(os.getenv('SCHEDULE_FREQUENCY_HOURS', '1')) * 60 + 10))") && \
      test $(find /app/logs/health_status.txt -mmin -${MINUTES} | wc -l) -eq 1 && \
      grep -q "^OK" /app/logs/health_status.txt || exit 1
```

**3. Deploy:**
```bash
docker compose build --no-cache && docker compose up -d
```

### Time-Based Projects (SCHEDULE_TIMES)

If your `.env` has `SCHEDULE_TIMES=12:00,18:00`, also modify:

**`src/core/scheduler.py`:**
```python
# Add import
from pathlib import Path

# Update __init__ to accept logs_dir
def __init__(self, frequency_hours: float, timezone: str, schedule_times_timezone: str = 'Europe/Athens', 
             schedule_times: List[str] = None, logs_dir: Path = None):
    # ... existing code ...
    self.logs_dir = logs_dir or Path('/app/logs')  # ADD THIS LINE

# Add method after register_alert()
def _write_health_status(self, logs_dir: Path, timezone: ZoneInfo) -> None:
    health_file = logs_dir / 'health_status.txt'
    timestamp = datetime.now(tz=timezone).isoformat()
    try:
        health_file.write_text(f"OK {timestamp}\n")
    except Exception as e:
        logger.error(f"Failed to write health status: {e}")

# Add at end of _run_all_alerts()
self._write_health_status(self.logs_dir, self.timezone)
```

**`src/main.py`:**
```python
# Add logs_dir parameter when creating scheduler
scheduler = AlertScheduler(
    frequency_hours=config.schedule_frequency_hours,
    timezone=config.timezone,
    schedule_times_timezone=config.schedule_times_timezone,
    schedule_times=config.schedule_times,
    logs_dir=config.logs_dir  # ADD THIS
)
```

## Remove Project from Monitoring

**Option 1: Remove healthcheck (recommended)**
```bash
# Edit Dockerfile - delete HEALTHCHECK line
vim Dockerfile
docker compose build --no-cache && docker compose up -d
```

**Option 2: Stop container**
```bash
docker compose down
```

## Troubleshooting
```bash
# Health file not created
docker exec <container> cat /app/logs/health_status.txt

# Test healthcheck manually
docker exec <container> sh -c 'test -f /app/logs/health_status.txt && grep -q "^OK" /app/logs/health_status.txt && echo "PASS" || echo "FAIL"'

# Check monitor logs
tail -f /srv/repos/alerts/_docker_health_monitor/logs/monitor.log

# Check if health monitoring code applied
docker exec <container> grep "_write_health_status" /app/src/core/base_alert.py
```

## What Gets Detected

**Application Failures:**
- Database connection errors
- API authentication failures
- Query execution errors
- Unhandled exceptions

**Container Failures:**
- Process crashes
- Container stops
- Healthcheck failures

## Retry Behavior

**Simple mode (default):**
```
12:00 - Unhealthy detected
12:10 - Check again → Still unhealthy → Send alert
Total: 10 minutes to alert
```

**With backoff (HEALTH_USE_BACKOFF=true):**
```
12:00 - Unhealthy detected
12:05 - Check again (attempt 1) → Still unhealthy
12:15 - Check again (attempt 2, 5*2=10min) → Still unhealthy
12:35 - Check again (attempt 3, 10*2=20min) → Send alert
Total: 35 minutes, but catches persistent issues
```

## Scaling

- ✓ 5 containers: Works great
- ✓ 10-20 containers: Parallel checks keep it fast
- ✓ 50+ containers: No slowdown, designed for scale

## Backward Compatibility

✓ All changes are backward compatible  
✓ Existing functionality preserved  
✓ Health monitoring adds capability without breaking anything  
✓ 5-minute rollback if needed

## Support

- **Logs:** `tail -f /srv/repos/alerts/_docker_health_monitor/logs/monitor.log`
- **Status:** `sudo systemctl status docker-health-monitor`
- **Health:** `docker ps --format "table {{.Names}}\t{{.Status}}"`
- **Full Guide:** See [README_LONG.md](README_LONG.md)

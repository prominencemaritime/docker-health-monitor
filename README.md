# Multi-Project Docker Health Monitor

A centralized health monitoring system that watches all Docker containers with healthchecks across multiple projects and sends email alerts when containers become unhealthy.
## Quick Start: Health Monitoring Setup

### One-Time Setup Per Project

**Files to modify:** `src/core/base_alert.py`, `Dockerfile`, and for time-based scheduling also `src/core/scheduler.py` + `src/main.py`

#### 1. Update `src/core/base_alert.py`

Add to imports:
```python
from pathlib import Path
```

Add this method after `_send_notifications`:
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

In `run()` method, add health status writes:
```python
# After successful notifications (around line 195)
success = self._send_notifications(notification_jobs, run_time)
self._write_health_status("OK", run_time)  # ADD THIS
return success

# In exception handler (around line 208)
except Exception as e:
    self.logger.exception(f"Error in {self.__class__.__name__}.run(): {e}")
    self._write_health_status("ERROR", run_time, str(e))  # ADD THIS
    return False

# On early returns - add to all 3 locations (around lines 161, 173, 182)
self._write_health_status("OK", run_time)  # ADD BEFORE each return False
```

#### 2. Update `Dockerfile`

Replace HEALTHCHECK line with:
```dockerfile
HEALTHCHECK --interval=30m --timeout=10s --start-period=30s --retries=3 \
  CMD test -f /app/logs/health_status.txt && \
      MINUTES=$(python3 -c "import os; schedule_times = os.getenv('SCHEDULE_TIMES', ''); print(1440 if schedule_times else int(float(os.getenv('SCHEDULE_FREQUENCY_HOURS', '1')) * 60 + 10))") && \
      test $(find /app/logs/health_status.txt -mmin -${MINUTES} | wc -l) -eq 1 && \
      grep -q "^OK" /app/logs/health_status.txt || exit 1
```

#### 3. For Time-Based Scheduling Only (SCHEDULE_TIMES set)

**Check if needed:** `grep SCHEDULE_TIMES .env` - if set and not empty, apply these:

**In `src/core/scheduler.py`:**
```python
# Add to imports
from pathlib import Path

# Update __init__ (add logs_dir parameter)
def __init__(self, frequency_hours: float, timezone: str, schedule_times_timezone: str = 'Europe/Athens', 
             schedule_times: List[str] = None, logs_dir: Path = None):
    # ... existing code ...
    self.logs_dir = logs_dir or Path('/app/logs')  # ADD THIS LINE
    # ... rest stays same ...

# Add method after register_alert()
def _write_health_status(self, logs_dir: Path, timezone: ZoneInfo) -> None:
    """Write health status for Docker healthcheck."""
    health_file = logs_dir / 'health_status.txt'
    timestamp = datetime.now(tz=timezone).isoformat()
    try:
        health_file.write_text(f"OK {timestamp}\n")
        logger.debug(f"Health status written: {timestamp}")
    except Exception as e:
        logger.error(f"Failed to write health status: {e}")

# Update _run_all_alerts() - add at end
def _run_all_alerts(self) -> None:
    # ... existing code ...
    self._write_health_status(self.logs_dir, self.timezone)  # ADD AT END
```

**In `src/main.py`:**
```python
# Update scheduler creation (around line 207)
scheduler = AlertScheduler(
    frequency_hours=config.schedule_frequency_hours,
    timezone=config.timezone,
    schedule_times_timezone=config.schedule_times_timezone,
    schedule_times=config.schedule_times,
    logs_dir=config.logs_dir  # ADD THIS
)
```

---

### Deploy Checklist
```bash
# 1. Backup
cp src/core/base_alert.py src/core/base_alert.py.backup
cp Dockerfile Dockerfile.backup

# 2. Make changes above

# 3. Deploy
docker compose build --no-cache && docker compose up -d

# 4. Verify (wait for next scheduled run first)
docker exec <container-name> cat /app/logs/health_status.txt
# Should show: OK <timestamp>

# 5. Check health (wait 30 min after health file created)
docker compose ps
# Should show: (healthy)
```

---

### Quick Reference

**Backward compatible?** Yes - all changes safe to deploy  
**Rollback:** Restore `.backup` files, rebuild, restart (5 min)  
**Applies to:** All projects with `src/core/base_alert.py`  
**Extra steps for:** Projects with `SCHEDULE_TIMES` in `.env`  

**What it does:**
- Detects app-level failures (DB errors, exceptions)
- Writes health status after each run
- Docker monitors health file freshness + content
- Email alerts on health changes

**Timeline to healthy:**
- Frequency-based: ~1 hour after deploy
- Time-based: Next scheduled run time

---

### Troubleshooting
```bash
# Health file not created
docker exec <container> grep "_write_health_status" /app/src/core/base_alert.py
# If empty: rebuild with --no-cache

# Container unhealthy
docker exec <container> cat /app/logs/health_status.txt
# Check for "ERROR" - if present, fix underlying issue
# Check timestamp - if old, alerts not running

# Test healthcheck manually
docker exec <container> sh -c 'test -f /app/logs/health_status.txt && grep -q "^OK" /app/logs/health_status.txt && echo "PASS" || echo "FAIL"'
```

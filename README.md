# Multi-Project Docker Health Monitor

A robust, production-ready Docker container health monitoring system that tracks containers across multiple projects and sends intelligent email alerts when issues are detected.

## Quickstart Guide

Get your entire monitoring system up and running in 15 minutes.

### Prerequisites Check

```bash
# Verify you have the requirements
python3 --version  # Should be 3.7+
docker --version   # Should be 19.03+
docker ps          # Should list running containers

# Verify you have SMTP credentials ready
# - SMTP server hostname
# - SMTP port (usually 587 or 465)
# - Username/email
# - Password (or app password for Gmail)
```

### Step 1: Set Up the Monitor (5 minutes)

**On your Ubuntu server:**

```bash
# 1. Create monitoring directory
sudo mkdir -p /srv/repos/_docker_monitoring/logs
cd /srv/repos/_docker_monitoring

# 2. Download the monitor script
# (Upload docker_health_monitor.py to this directory via SCP, Git, or copy-paste)
wget https://your-repo/docker_health_monitor.py
# OR
scp docker_health_monitor.py user@server:/srv/repos/_docker_monitoring/

# 3. Make it executable
chmod +x docker_health_monitor.py

# 4. Install Python dependencies
pip3 install docker python-decouple

# 5. Create .env configuration
cat > .env << 'EOF'
# SMTP Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password

# Alert Recipients
HEALTH_CHECK_ALERT_EMAILS=admin@example.com,ops@example.com

# Server Identification
SERVER_NAME=Production Server

# Monitoring Intervals (adjust as needed)
HEALTH_CHECK_INTERVAL_SEC=30
WAIT_AND_CHECK_AGAIN_MIN=15
HEALTH_CHECK_LOG_LINES=50
EOF

# 6. Edit .env with your actual credentials
vim .env
# Press 'i' to edit, update values, then ESC + :wq to save

# 7. Test the configuration
python3 -c "from decouple import config; print('SMTP:', config('SMTP_HOST')); print('Emails:', config('HEALTH_CHECK_ALERT_EMAILS'))"
```

### Step 2: Add Healthchecks to Your Projects (5 minutes per project)

For **each** of your Docker projects (e.g., `passage_plan`, `vessel_certificates`, `hot_works_alerts`):

```bash
# Navigate to project directory
cd /srv/repos/passage_plan  # Or your project path

# Create scripts directory if it doesn't exist
mkdir -p scripts

# Create healthcheck.py
cat > scripts/healthcheck.py << 'EOFHC'
#!/usr/bin/env python3
"""
Healthcheck script for Docker containers with flexible scheduling.
Supports both SCHEDULE_FREQUENCY_HOURS and SCHEDULE_TIMES modes.

This script checks if /app/logs/health_status.txt exists, contains "OK",
and has been updated recently enough based on the schedule configuration.

Environment Variables:
    SCHEDULE_FREQUENCY_HOURS: Run every N hours (e.g., "2" for every 2 hours)
    SCHEDULE_TIMES: Run at specific times (e.g., "12:00,18:00")

At least one must be set. If both are set, SCHEDULE_FREQUENCY_HOURS takes precedence.

Exit Codes:
    0: Healthy
    1: Unhealthy
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def main():
    """
    Main healthcheck logic.

    Validates the health_status.txt file by checking:
    1. File exists
    2. File contains valid structured data
    3. Status is OK or ERROR is recent
    4. Timestamp is recent enough based on schedule

    Exit codes:
        0: Healthy
        1: Unhealthy
    """
    health_file = Path("/app/logs/health_status.txt")

    # Validate file structure first
    try:
        validate_health_file_structure(health_file)
    except Exception as e:
        print(f"Health file validation failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Read and parse health status
    try:
        health_data = parse_health_file(health_file)
    except Exception as e:
        print(f"Cannot parse health status: {e}", file=sys.stderr)
        sys.exit(1)

    # Get the timezone to use for time calculations
    tz_name = get_effective_timezone()

    # Calculate maximum age based on schedule mode
    max_age_minutes = calculate_max_age()

    # Calculate file age using the parsed timestamp (timezone-aware)
    try:
        now = datetime.now(tz=ZoneInfo(tz_name))
        file_age_seconds = (now - health_data['timestamp']).total_seconds()
        file_age_minutes = file_age_seconds / 60
    except Exception as e:
        print(f"Cannot calculate file age: {e}", file=sys.stderr)
        sys.exit(1)

    # Check status and age
    if health_data['status'] == "ERROR":
        # For ERROR status, check if it's a recent error
        if file_age_minutes > max_age_minutes:
            print(
                f"Health status is ERROR and stale: {file_age_minutes:.1f} minutes old "
                f"(max: {max_age_minutes:.1f} minutes). "
                f"Error: {health_data.get('error_msg', 'No error message')}",
                file=sys.stderr
            )
            sys.exit(1)
        else:
            # Recent error - still fail but with different message
            print(
                f"Health status is ERROR (recent): {health_data.get('error_msg', 'No error message')}",
                file=sys.stderr
            )
            sys.exit(1)

    elif health_data['status'] == "OK":
        # Check if OK status is recent enough
        if file_age_minutes > max_age_minutes:
            print(
                f"Health status file is too old: {file_age_minutes:.1f} minutes "
                f"(max: {max_age_minutes:.1f} minutes)",
                file=sys.stderr
            )
            sys.exit(1)

    else:
        print(f"Unknown health status: {health_data['status']}", file=sys.stderr)
        sys.exit(1)

    # All checks passed
    print(
        f"Healthy (status: {health_data['status']}, "
        f"alert: {health_data.get('alert_type', 'unknown')}, "
        f"age: {file_age_minutes:.1f}/{max_age_minutes:.1f} minutes)"
    )
    sys.exit(0)


def parse_health_file(health_file: Path) -> dict:
    """
    Parse the structured health status file.

    Expected format:
        Line 1: STATUS YYYY-MM-DDTHH:MM:SS.ffffff+HH:MM
        Line 2: ALERT_TYPE: ClassName
        Line 3: TIMEZONE: timezone_name
        Line 4: ERROR_MSG: message (optional, only if ERROR)

    Args:
        health_file: Path to health_status.txt

    Returns:
        Dictionary with parsed health data:
            - status: "OK" or "ERROR"
            - timestamp: timezone-aware datetime object
            - alert_type: Alert class name
            - timezone: Timezone name from file
            - error_msg: Error message (only if status is ERROR)

    Raises:
        ValueError: If file format is invalid
        Exception: If file cannot be read or parsed
    """
    content = health_file.read_text().strip()
    lines = content.split('\n')

    if len(lines) < 3:
        raise ValueError(f"Health file has insufficient lines: {len(lines)} (expected at least 3)")

    # Parse line 1: STATUS TIMESTAMP
    status_line = lines[0].strip()
    parts = status_line.split(' ', 1)

    if len(parts) != 2:
        raise ValueError(f"Invalid status line format: '{status_line}'")

    status = parts[0]
    timestamp_str = parts[1]

    if status not in ["OK", "ERROR"]:
        raise ValueError(f"Invalid status: '{status}' (expected OK or ERROR)")

    # Parse timestamp (ISO format with timezone)
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
    except ValueError as e:
        raise ValueError(f"Invalid timestamp format: '{timestamp_str}': {e}")

    # Ensure timestamp is timezone-aware
    if timestamp.tzinfo is None:
        raise ValueError(f"Timestamp is not timezone-aware: '{timestamp_str}'")

    # Parse line 2: ALERT_TYPE
    if not lines[1].startswith("ALERT_TYPE: "):
        raise ValueError(f"Invalid ALERT_TYPE line: '{lines[1]}'")
    alert_type = lines[1].replace("ALERT_TYPE: ", "").strip()

    # Parse line 3: TIMEZONE
    if not lines[2].startswith("TIMEZONE: "):
        raise ValueError(f"Invalid TIMEZONE line: '{lines[2]}'")
    timezone = lines[2].replace("TIMEZONE: ", "").strip()

    result = {
        'status': status,
        'timestamp': timestamp,
        'alert_type': alert_type,
        'timezone': timezone
    }

    # Parse line 4 (optional): ERROR_MSG
    if len(lines) >= 4 and lines[3].startswith("ERROR_MSG: "):
        error_msg = lines[3].replace("ERROR_MSG: ", "").strip()
        result['error_msg'] = error_msg

    return result


def get_effective_timezone() -> str:
    """
    Determine which timezone to use for time calculations.

    Precedence:
        1. SCHEDULE_TIMES_TIMEZONE (if set)
        2. TIMEZONE (if set)
        3. UTC (default fallback)

    Returns:
        Timezone name (e.g., "Europe/Athens", "UTC")
    """
    schedule_tz = os.getenv('SCHEDULE_TIMES_TIMEZONE', '').strip()
    if schedule_tz:
        return schedule_tz

    general_tz = os.getenv('TIMEZONE', '').strip()
    if general_tz:
        return general_tz

    return 'UTC'


def validate_health_file_structure(health_file: Path) -> None:
    """
    Perform initial validation of health file structure before parsing.

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is empty or has invalid structure
    """
    if not health_file.exists():
        raise FileNotFoundError(f"Health file not found: {health_file}")

    stat = health_file.stat()
    if stat.st_size == 0:
        raise ValueError("Health file is empty")

    if stat.st_size > 10000:  # 10KB limit
        raise ValueError(f"Health file is too large: {stat.st_size} bytes (max 10KB)")


def calculate_max_age() -> float:
    """
    Calculate maximum allowed age for health_status.txt based on schedule mode.

    Returns:
        Maximum age in minutes
    """
    freq_hours = os.getenv('SCHEDULE_FREQUENCY_HOURS', '').strip()
    schedule_times = os.getenv('SCHEDULE_TIMES', '').strip()

    # Mode 1: Frequency-based (e.g., every 2 hours)
    if freq_hours:
        try:
            hours = float(freq_hours)
            # Allow schedule interval + 10 minute buffer
            return hours * 60 + 10
        except (ValueError, TypeError):
            print(f"Invalid SCHEDULE_FREQUENCY_HOURS: {freq_hours}", file=sys.stderr)
            return 70  # Default fallback: 1 hour + 10 min buffer

    # Mode 2: Specific times (e.g., 12:00,18:00)
    elif schedule_times:
        try:
            return calculate_max_age_from_times(schedule_times)
        except Exception as e:
            print(f"Error calculating age from SCHEDULE_TIMES: {e}", file=sys.stderr)
            return 70  # Default fallback

    # Mode 3: No schedule defined (default to hourly + buffer)
    else:
        print("Warning: Neither SCHEDULE_FREQUENCY_HOURS nor SCHEDULE_TIMES set", file=sys.stderr)
        return 70  # 1 hour + 10 minute buffer


def calculate_max_age_from_times(schedule_times: str) -> float:
    """
    Calculate maximum age based on SCHEDULE_TIMES.

    For times like "12:00,18:00", the health file should be updated within
    10 minutes after the most recent scheduled time.

    Uses the effective timezone (SCHEDULE_TIMES_TIMEZONE or TIMEZONE) for
    determining "now" and calculating schedule times.

    Args:
        schedule_times: Comma-separated list of times (HH:MM format)

    Returns:
        Maximum age in minutes (time since most recent scheduled time + 10 min buffer)

    Note:
        This function uses timezone-aware datetime calculations to ensure
        correct behavior across different timezones.
    """
    # Get timezone-aware "now"
    tz_name = get_effective_timezone()
    try:
        now = datetime.now(tz=ZoneInfo(tz_name))
    except Exception as e:
        print(f"Invalid timezone '{tz_name}': {e}, falling back to UTC", file=sys.stderr)
        now = datetime.now(tz=ZoneInfo('UTC'))

    # Parse all scheduled times
    time_list = [t.strip() for t in schedule_times.split(',')]
    scheduled_datetimes = []

    for time_str in time_list:
        try:
            hour, minute = map(int, time_str.split(':'))

            # Create timezone-aware datetime for today
            scheduled_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            scheduled_datetimes.append(scheduled_today)

            # Also consider yesterday's schedule
            scheduled_yesterday = scheduled_today - timedelta(days=1)
            scheduled_datetimes.append(scheduled_yesterday)

        except (ValueError, IndexError) as e:
            print(f"Invalid time format '{time_str}': {e}", file=sys.stderr)
            continue

    if not scheduled_datetimes:
        print("No valid times found in SCHEDULE_TIMES", file=sys.stderr)
        return 70

    # Find the most recent scheduled time that has passed
    past_times = [dt for dt in scheduled_datetimes if dt <= now]

    if not past_times:
        # No scheduled time has passed yet today - use most recent from yesterday
        past_times = sorted(scheduled_datetimes)

    most_recent = max(past_times)

    # Calculate minutes since most recent scheduled time
    minutes_since = (now - most_recent).total_seconds() / 60

    # Allow the time since last schedule + 10 minute buffer
    return minutes_since + 10


if __name__ == "__main__":
    main()
EOFHC

# Make it executable
chmod +x scripts/healthcheck.py
```

### Step 3: Update Dockerfiles (2 minutes per project)

For each project, add healthcheck to your Dockerfile:

```bash
# Edit your Dockerfile
vim Dockerfile
```

Add these lines **after** your `COPY` commands but **before** `CMD`:

```dockerfile
# Ensure scripts are copied (if not already)
COPY scripts/ ./scripts/

# Make healthcheck executable
RUN chmod +x /app/scripts/*.py

# Add healthcheck - choose interval based on your schedule
# For SCHEDULE_TIMES (e.g., 12:00,18:00):
HEALTHCHECK --interval=5m --timeout=10s --start-period=2m --retries=2 \
  CMD python3 /app/scripts/healthcheck.py

# For SCHEDULE_FREQUENCY_HOURS=1 (hourly):
# HEALTHCHECK --interval=2m --timeout=10s --start-period=2m --retries=2 \
#   CMD python3 /app/scripts/healthcheck.py

# For SCHEDULE_FREQUENCY_HOURS=0.25 (every 15 min):
# HEALTHCHECK --interval=1m --timeout=10s --start-period=1m --retries=3 \
#   CMD python3 /app/scripts/healthcheck.py
```

**Choose the right interval:**
- If using `SCHEDULE_TIMES=12:00,18:00` → `--interval=5m`
- If using `SCHEDULE_FREQUENCY_HOURS=1` → `--interval=2m`
- If using `SCHEDULE_FREQUENCY_HOURS=0.25` → `--interval=1m`

### Step 4: Rebuild and Restart Containers (2 minutes per project)

```bash
# Still in project directory (e.g., /srv/repos/passage_plan)

# Rebuild the image
docker compose build

# Restart containers
docker compose up -d

# Verify healthcheck is working
docker ps
# You should see "healthy" or "starting" in the STATUS column

# Check detailed health status
docker inspect <container-name> | grep -A 20 Health

# Test healthcheck manually
docker exec <container-name> python3 /app/scripts/healthcheck.py
# Expected output: Healthy (status: OK, alert: AlertClassName, age: X/Y minutes)

# Check the health file directly
docker exec <container-name> cat /app/logs/health_status.txt
# Should show structured format with OK/ERROR, timestamp, alert type, timezone

# Verify environment variables
docker exec <container-name> env | grep SCHEDULE
# Should show SCHEDULE_FREQUENCY_HOURS or SCHEDULE_TIMES
```

**Repeat Step 2-4 for each project:**
- `/srv/repos/passage_plan`
- `/srv/repos/vessel_certificates`
- `/srv/repos/hot_works_alerts`
- Any other projects

### Step 5: Set Up Monitor as System Service (3 minutes)

```bash
# Create systemd service file (on remote ubuntu, macOS does not use systemd)
sudo vim /etc/systemd/system/docker-health-monitor.service
```

Paste this content:

```ini
[Unit]
Description=Multi-Project Docker Health Monitor
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/srv/repos/_docker_monitoring
ExecStart=/usr/bin/python3 /srv/repos/_docker_monitoring/docker_health_monitor.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**If running as non-root user:**
```bash
# Add your user to docker group
sudo usermod -aG docker your-username

# Then change User=root to User=your-username in service file
```

**Enable and start the service:**

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable (start on boot)
sudo systemctl enable docker-health-monitor

# Start now
sudo systemctl start docker-health-monitor

# Check status
sudo systemctl status docker-health-monitor
# Should show: "active (running)"

# View logs
sudo journalctl -u docker-health-monitor -f
# Press Ctrl+C to exit
```

### Step 6: Verify Everything Works (5 minutes)

**1. Check monitor logs:**
```bash
tail -f /srv/repos/_docker_monitoring/logs/monitor.log
```

You should see:
```
======================================================================
▶ MULTI-PROJECT DOCKER HEALTH MONITOR STARTED
======================================================================
```

**2. Check container health statuses:**
```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

All containers should show `healthy` or `starting` (will become healthy after `start_period`).

**3. Test with intentional failure:**
```bash
# Pick one project to test
cd /srv/repos/passage_plan

# Break the container (e.g., wrong DB password in .env)
vim .env
# Change DB_PASS to something wrong, save

# Restart container
docker compose up -d

# Watch it become unhealthy
watch -n 5 'docker ps --format "table {{.Names}}\t{{.Status}}"'
# After 2-5 minutes, should show "unhealthy"

# Monitor logs - you should see Phase 2 activity after 15 minutes
tail -f /srv/repos/_docker_monitoring/logs/monitor.log

# You should receive an email alert after ~15 minutes!

# Fix it
vim .env
# Restore correct DB_PASS
docker compose up -d

# Should become healthy again
```

### Testing Healthcheck Failures

**Method 1: Simulate old timestamp (recommended):**
```bash
docker exec <container-name> python3 << 'EOF'
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

health_file = Path("/app/logs/health_status.txt")
old_time = datetime.now(tz=ZoneInfo("Europe/Athens")) - timedelta(hours=2)

with open(health_file, 'w') as f:
    f.write(f"OK {old_time.isoformat()}\n")
    f.write(f"ALERT_TYPE: YourAlertClassName\n")
    f.write(f"TIMEZONE: Europe/Athens\n")

print(f"Set timestamp to 2 hours ago")
EOF

# Test healthcheck - should fail
docker exec <container-name> python3 /app/scripts/healthcheck.py
```

**Method 2: Simulate ERROR status:**
```bash
docker exec <container-name> python3 << 'EOF'
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

health_file = Path("/app/logs/health_status.txt")
now = datetime.now(tz=ZoneInfo("Europe/Athens"))

with open(health_file, 'w') as f:
    f.write(f"ERROR {now.isoformat()}\n")
    f.write(f"ALERT_TYPE: YourAlertClassName\n")
    f.write(f"TIMEZONE: Europe/Athens\n")
    f.write(f"ERROR_MSG: Simulated database failure\n")
EOF

# Test healthcheck - should fail
docker exec <container-name> python3 /app/scripts/healthcheck.py
```

### Step 7: Optional - Configure Project-Specific Routing

If you want different teams to receive alerts for different projects:

```bash
# Edit monitor .env
cd /srv/repos/_docker_monitoring
vim .env
```

Add this line:
```bash
CONTAINER_ALERT_ROUTING=passage-plan:maritime-team@example.com;vessel-cert:compliance@example.com;hot-works:safety@example.com
```

Restart monitor:
```bash
sudo systemctl restart docker-health-monitor
```

### Quick Reference Commands

```bash
# Monitor status
sudo systemctl status docker-health-monitor

# Monitor logs (live)
sudo journalctl -u docker-health-monitor -f
tail -f /srv/repos/_docker_monitoring/logs/monitor.log

# Container health statuses
docker ps --format "table {{.Names}}\t{{.Status}}"

# Check specific container healthcheck
docker exec <container-name> python3 /app/scripts/healthcheck.py

# Restart monitor
sudo systemctl restart docker-health-monitor

# Stop monitor
sudo systemctl stop docker-health-monitor

# View monitor configuration
cat /srv/repos/_docker_monitoring/.env
```

### Troubleshooting Quick Fixes

**Container shows "starting" forever:**
```bash
# Increase start_period in Dockerfile
HEALTHCHECK --start-period=5m ...
docker compose build && docker compose up -d
```

**Monitor not starting:**
```bash
# Check configuration
python3 -c "from decouple import config; print(config('SMTP_HOST'))"

# Check Docker permissions
docker ps

# Check service logs
sudo journalctl -u docker-health-monitor -n 50
```

**No emails arriving:**
```bash
# Test SMTP
cd /srv/repos/_docker_monitoring
python3 << 'EOF'
import smtplib
from decouple import config

server = smtplib.SMTP(config('SMTP_HOST'), int(config('SMTP_PORT', 587)))
server.starttls()
server.login(config('SMTP_USER'), config('SMTP_PASS'))
print('✓ SMTP works')
server.quit()
EOF
```

### Success Checklist

- [ ] Monitor service running: `systemctl status docker-health-monitor`
- [ ] All containers show "healthy": `docker ps`
- [ ] Monitor logs show activity: `tail -f logs/monitor.log`
- [ ] Test email received (after breaking a container)
- [ ] All projects have healthcheck.py
- [ ] All Dockerfiles have HEALTHCHECK line
- [ ] .env configured with correct SMTP settings

** Your monitoring system is now active and will alert you of any container issues.**

---

## Overview

This monitor watches all Docker containers with healthchecks across multiple docker-compose projects, implements a two-phase verification pattern to avoid false positives, and sends contextual email alerts with actionable troubleshooting steps.

**Key Features:**
- **Two-phase health verification** - confirms issues before alerting
- **Concurrent health checks** using ThreadPoolExecutor (30 workers)
- **Project-aware alerting** - groups containers by project with context
- **Thread-safe** state management
- **Graceful shutdown** handling for clean stops
- **Zero false positives** - only alerts after confirmation
- **Scales efficiently** to any number of containers
- **Cross-platform** - works on Mac, Ubuntu, and other Linux distributions

## Architecture

### High-Level Two-Phase Flow
```mermaid
flowchart TD
    Start([Monitor Starts]) --> Init[Initialize Monitor<br/>Load Config from .env]
    Init --> StartLoop[Start Main Loop]
    
    StartLoop --> MainLoop{Shutdown<br/>Requested?}
    
    MainLoop -->|No| Phase1[Phase 1: Check All Containers<br/>Concurrent Health Checks]
    MainLoop -->|Yes| Shutdown([Graceful Shutdown])
    
    Phase1 --> GetContainers[Get All Running Containers<br/>from Docker API]
    
    GetContainers --> SubmitChecks[Submit Health Checks<br/>to Thread Pool<br/>Max 30 Concurrent]
    
    SubmitChecks --> C1[Worker: Check Container 1]
    SubmitChecks --> C2[Worker: Check Container 2]
    SubmitChecks --> C3[Worker: Check Container 3]
    SubmitChecks --> Cn[Worker: Check Container N]
    
    C1 --> Result1[Return: ContainerHealthCheck]
    C2 --> Result2[Return: ContainerHealthCheck]
    C3 --> Result3[Return: ContainerHealthCheck]
    Cn --> Resultn[Return: ContainerHealthCheck]
    
    Result1 --> Collect[Collect All Results]
    Result2 --> Collect
    Result3 --> Collect
    Resultn --> Collect
    
    Collect --> Categorize[Categorize Results:<br/>1. Needs Retry<br/>2. Immediate Alerts<br/>3. No Change]
    
    Categorize --> UpdateStates[Update Container States<br/>Thread-Safe]
    
    UpdateStates --> CheckMissing[Check for Disappeared<br/>Containers]
    
    CheckMissing --> Missing{Any Containers<br/>Disappeared?}
    Missing -->|Yes| AlertMissing[Send not_found Alerts<br/>Synchronously]
    Missing -->|No| HandleImmediate
    AlertMissing --> HandleImmediate
    
    HandleImmediate[Handle Immediate Alerts<br/>Recoveries]
    
    HandleImmediate --> Decision{Any Containers<br/>Need Retry?}
    
    Decision -->|No| Sleep[Sleep check_interval_sec<br/>Default: 30 seconds]
    Decision -->|Yes| WaitMsg[Log: Waiting Before Recheck]
    
    WaitMsg --> MainSleep[Main Thread Sleep<br/>wait_and_check_again_min<br/>Default: 15 minutes]
    
    MainSleep --> Phase2[Phase 2: Recheck Unhealthy<br/>Concurrent Rechecks]
    
    Phase2 --> SubmitRechecks[Submit Rechecks<br/>to Thread Pool<br/>Max 30 Concurrent]
    
    SubmitRechecks --> RC1[Worker: Recheck Container X]
    SubmitRechecks --> RC2[Worker: Recheck Container Y]
    SubmitRechecks --> RCn[Worker: Recheck Container Z]
    
    RC1 --> Status1{Still<br/>Unhealthy?}
    RC2 --> Status2{Still<br/>Unhealthy?}
    RCn --> Statusn{Still<br/>Unhealthy?}
    
    Status1 -->|Yes| Alert1[Get Logs<br/>Send Alert Email]
    Status1 -->|No| Log1[Log: Container Recovered]
    
    Status2 -->|Yes| Alert2[Get Logs<br/>Send Alert Email]
    Status2 -->|No| Log2[Log: Container Recovered]
    
    Statusn -->|Yes| Alertn[Get Logs<br/>Send Alert Email]
    Statusn -->|No| Logn[Log: Container Recovered]
    
    Alert1 --> UpdateFinal
    Alert2 --> UpdateFinal
    Alertn --> UpdateFinal
    Log1 --> UpdateFinal
    Log2 --> UpdateFinal
    Logn --> UpdateFinal
    
    UpdateFinal[Update Container States<br/>Mark as Checked]
    
    UpdateFinal --> Sleep
    Sleep --> MainLoop
    
    Shutdown --> WaitThreads[Wait for Active<br/>Thread Pool Tasks]
    WaitThreads --> Stop([Monitor Stopped])
    
    style Phase1 fill:#e1f5ff
    style Phase2 fill:#fff4e1
    style MainSleep fill:#ffe1e1
    style Decision fill:#f0e1ff
    style Sleep fill:#e1ffe1
```

### Detailed Phase 1 Flow
```mermaid
flowchart TD
    Start([Phase 1 Begins]) --> Submit[Submit All Containers<br/>to Thread Pool]
    
    Submit --> Worker[Worker Thread:<br/>check_single_container]
    
    Worker --> GetHealth[Call Docker API<br/>get_container_health]
    
    GetHealth --> HasHealth{Has<br/>Healthcheck?}
    HasHealth -->|No| Skip[Skip Container<br/>Return None]
    HasHealth -->|Yes| GetPrevious[Get Previous State<br/>Thread-Safe Read]
    
    GetPrevious --> Compare{Status<br/>Changed?}
    
    Compare -->|No| JustUpdate[Update last_check<br/>Thread-Safe Write]
    Compare -->|Yes| LogChange[Log Status Change]
    
    LogChange --> WhichChange{What<br/>Changed?}
    
    WhichChange -->|Became Unhealthy| AddRetry[Add to needs_retry List<br/>Return ContainerHealthCheck]
    WhichChange -->|Became Healthy| AddImmediate[Add to immediate_alerts List<br/>Return ContainerHealthCheck]
    WhichChange -->|Other Change| UpdateState[Update State<br/>Return ContainerHealthCheck]
    
    Skip --> End
    JustUpdate --> End
    AddRetry --> End
    AddImmediate --> End
    UpdateState --> End
    
    End([Return to Collector])
    
    style Worker fill:#e1f5ff
    style AddRetry fill:#ffcccc
    style AddImmediate fill:#ccffcc
```

### Detailed Phase 2 Flow
```mermaid
flowchart TD
    Start([Phase 2 Begins]) --> HasRetries{Any Containers<br/>to Recheck?}
    
    HasRetries -->|No| Skip([Skip Phase 2])
    HasRetries -->|Yes| LogWait[Log: Rechecking N containers<br/>after M minutes]
    
    LogWait --> Sleep[Main Thread Sleeps<br/>wait_and_check_again_min × 60 seconds<br/>Interruptible every 1 second]
    
    Sleep --> Submit[Submit Rechecks<br/>to Thread Pool]
    
    Submit --> Worker[Worker Thread:<br/>recheck_single_container]
    
    Worker --> TryGet[Try to Get Container<br/>from Docker API]
    
    TryGet --> Exists{Container<br/>Exists?}
    
    Exists -->|No| ReturnNotFound[Return: not_found Status]
    Exists -->|Yes| GetHealth[Get Current Health Status]
    
    GetHealth --> ReturnStatus[Return: Current Status]
    
    ReturnNotFound --> Collect
    ReturnStatus --> Collect
    
    Collect[Collect All Recheck Results]
    
    Collect --> Process[Process Each Result]
    
    Process --> CheckStatus{Current<br/>Status?}
    
    CheckStatus -->|healthy| LogRecovery[Log: Container Recovered<br/>Update State<br/>No Alert]
    CheckStatus -->|unhealthy| GetLogs[Fetch Container Logs<br/>Last N Lines]
    CheckStatus -->|not_found| PrepareNotFound[Prepare not_found Alert]
    
    GetLogs --> SendAlert[Send Alert Email<br/>with Logs]
    PrepareNotFound --> SendAlert
    
    SendAlert --> UpdateState[Update Container State]
    LogRecovery --> UpdateState
    
    UpdateState --> End([Phase 2 Complete])
    
    style Sleep fill:#ffe1e1
    style SendAlert fill:#ff9999
    style LogRecovery fill:#99ff99
```

### Thread Pool Usage Pattern
```mermaid
flowchart LR
    Main[Main Thread] --> Loop[Monitoring Loop]
    
    Loop --> Phase1Call[Phase 1: check_all_containers]
    Phase1Call --> Pool[Thread Pool<br/>30 Workers]
    
    Pool --> Check1[check_single_container<br/>Container 1]
    Pool --> Check2[check_single_container<br/>Container 2]
    Pool --> CheckN[check_single_container<br/>Container N]
    
    Check1 --> Docker1[Docker API Call]
    Check2 --> Docker2[Docker API Call]
    CheckN --> DockerN[Docker API Call]
    
    Docker1 --> Return1[Return Result]
    Docker2 --> Return2[Return Result]
    DockerN --> ReturnN[Return Result]
    
    Return1 --> Collect1[Main Thread<br/>Collects Results]
    Return2 --> Collect1
    ReturnN --> Collect1
    
    Collect1 --> MainSleep[Main Thread<br/>Sleeps if Needed]
    
    MainSleep --> Phase2Call[Phase 2: recheck_unhealthy]
    Phase2Call --> Pool
    
    Pool --> Recheck1[recheck_single_container<br/>Container X]
    Pool --> Recheck2[recheck_single_container<br/>Container Y]
    
    Recheck1 --> RDocker1[Docker API Call]
    Recheck2 --> RDocker2[Docker API Call]
    
    RDocker1 --> RReturn1[Return Result]
    RDocker2 --> RReturn2[Return Result]
    
    RReturn1 --> Collect2[Main Thread<br/>Collects Results]
    RReturn2 --> Collect2
    
    Collect2 --> NextLoop[Sleep check_interval_sec]
    NextLoop --> Loop
    
    State[(Container States<br/>Dict - Thread-Safe)]
    
    Check1 -.Read/Write.-> State
    Check2 -.Read/Write.-> State
    CheckN -.Read/Write.-> State
    Recheck1 -.Read.-> State
    Recheck2 -.Read.-> State
    
    style Pool fill:#e1f5ff
    style MainSleep fill:#ffe1e1
    style State fill:#fff4e1
```

## Installation

### Prerequisites

- Python 3.7+
- Docker Engine with API access
- SMTP server credentials for email alerts

### Setup

**For Ubuntu/Linux:**
```bash
sudo mkdir -p /srv/repos/_docker_monitoring/logs
cd /srv/repos/_docker_monitoring
```

**For Mac/Development:**
```bash
mkdir -p ~/dev/alerts/_docker_monitoring/logs
cd ~/dev/alerts/_docker_monitoring
```

**Common steps:**

1. **Download the scripts:**
   - `docker_health_monitor.py` (main script)
   - `.env` (configuration file)

2. **Install dependencies:**
   ```bash
   pip3 install docker python-decouple
   ```

3. **Set permissions:**
   ```bash
   chmod +x docker_health_monitor.py
   ```

4. **Add healthcheck scripts to your projects** (see Container Healthcheck section)

## Configuration

Create a `.env` file in the same directory as `docker_health_monitor.py`:

```bash
# ============================================
# REQUIRED CONFIGURATION
# ============================================

# SMTP Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password

# Alert Recipients (comma-separated)
HEALTH_CHECK_ALERT_EMAILS=admin@example.com,ops@example.com

# ============================================
# OPTIONAL CONFIGURATION
# ============================================

# Server Identification
SERVER_NAME=Production Server

# Monitoring Intervals
HEALTH_CHECK_INTERVAL_SEC=30
WAIT_AND_CHECK_AGAIN_MIN=15

# Logging
HEALTH_CHECK_LOG_LINES=50

# Project-Specific Alert Routing
# Format: pattern1:email1,email2;pattern2:email3
CONTAINER_ALERT_ROUTING=passage-plan:maritime@example.com;vessel-cert:compliance@example.com
```

### Configuration Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SMTP_HOST` | **Yes** | - | SMTP server hostname |
| `SMTP_PORT` | No | 587 | SMTP server port (587=STARTTLS, 465=SSL) |
| `SMTP_USER` | **Yes** | - | SMTP username/email |
| `SMTP_PASS` | **Yes** | - | SMTP password or app-specific password |
| `HEALTH_CHECK_ALERT_EMAILS` | **Yes** | - | Comma-separated list of default alert recipients |
| `SERVER_NAME` | No | `Production` | Server identifier shown in alert emails |
| `HEALTH_CHECK_INTERVAL_SEC` | No | `30` | Seconds between health check cycles |
| `WAIT_AND_CHECK_AGAIN_MIN` | No | `15` | Minutes to wait before rechecking unhealthy containers |
| `HEALTH_CHECK_LOG_LINES` | No | `50` | Number of log lines to include in alert emails |
| `CONTAINER_ALERT_ROUTING` | No | - | Project-specific email routing (see below) |

### SMTP Port Configuration

**Port 587 (STARTTLS) - Recommended:**
- Most common and widely supported
- Uses STARTTLS encryption
- Works with Gmail, most email providers

```bash
SMTP_PORT=587
```

**Port 465 (SSL/TLS) - Alternative:**
- Direct SSL connection
- Some servers prefer this
- May be required for internal SMTP servers

```bash
SMTP_PORT=465
```

The script automatically detects which method to use based on the port number.

### Hardcoded Settings

These values are **hardcoded in the script** but use relative paths:

- **Log directory:** `./logs/` (relative to script location)
- **Log file:** `./logs/monitor.log`
- **Log file max size:** 10 MB
- **Log backup count:** 5 files
- **Thread pool workers:** 30

The script automatically creates the `logs/` directory if it doesn't exist.

## Container Healthchecks

Every container must have a healthcheck defined. The monitor **only tracks containers with healthchecks**.

### Adding Healthchecks to Your Projects

#### Step 1: Create `scripts/healthcheck.py` in Each Project

Create a file at `<project>/scripts/healthcheck.py`:
```python
#!/usr/bin/env python3
"""
Healthcheck script for Docker containers with flexible scheduling.
Supports both SCHEDULE_FREQUENCY_HOURS and SCHEDULE_TIMES modes.

This script checks if /app/logs/health_status.txt exists, contains "OK",
and has been updated recently enough based on the schedule configuration.

Environment Variables:
    SCHEDULE_FREQUENCY_HOURS: Run every N hours (e.g., "2" for every 2 hours)
    SCHEDULE_TIMES: Run at specific times (e.g., "12:00,18:00")

At least one must be set. If both are set, SCHEDULE_FREQUENCY_HOURS takes precedence.

Exit Codes:
    0: Healthy
    1: Unhealthy
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def main():
    """
    Main healthcheck logic.

    Validates the health_status.txt file by checking:
    1. File exists
    2. File contains valid structured data
    3. Status is OK or ERROR is recent
    4. Timestamp is recent enough based on schedule

    Exit codes:
        0: Healthy
        1: Unhealthy
    """
    health_file = Path("/app/logs/health_status.txt")

    # Validate file structure first
    try:
        validate_health_file_structure(health_file)
    except Exception as e:
        print(f"Health file validation failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Read and parse health status
    try:
        health_data = parse_health_file(health_file)
    except Exception as e:
        print(f"Cannot parse health status: {e}", file=sys.stderr)
        sys.exit(1)

    # Get the timezone to use for time calculations
    tz_name = get_effective_timezone()

    # Calculate maximum age based on schedule mode
    max_age_minutes = calculate_max_age()

    # Calculate file age using the parsed timestamp (timezone-aware)
    try:
        now = datetime.now(tz=ZoneInfo(tz_name))
        file_age_seconds = (now - health_data['timestamp']).total_seconds()
        file_age_minutes = file_age_seconds / 60
    except Exception as e:
        print(f"Cannot calculate file age: {e}", file=sys.stderr)
        sys.exit(1)

    # Check status and age
    if health_data['status'] == "ERROR":
        # For ERROR status, check if it's a recent error
        if file_age_minutes > max_age_minutes:
            print(
                f"Health status is ERROR and stale: {file_age_minutes:.1f} minutes old "
                f"(max: {max_age_minutes:.1f} minutes). "
                f"Error: {health_data.get('error_msg', 'No error message')}",
                file=sys.stderr
            )
            sys.exit(1)
        else:
            # Recent error - still fail but with different message
            print(
                f"Health status is ERROR (recent): {health_data.get('error_msg', 'No error message')}",
                file=sys.stderr
            )
            sys.exit(1)

    elif health_data['status'] == "OK":
        # Check if OK status is recent enough
        if file_age_minutes > max_age_minutes:
            print(
                f"Health status file is too old: {file_age_minutes:.1f} minutes "
                f"(max: {max_age_minutes:.1f} minutes)",
                file=sys.stderr
            )
            sys.exit(1)

    else:
        print(f"Unknown health status: {health_data['status']}", file=sys.stderr)
        sys.exit(1)

    # All checks passed
    print(
        f"Healthy (status: {health_data['status']}, "
        f"alert: {health_data.get('alert_type', 'unknown')}, "
        f"age: {file_age_minutes:.1f}/{max_age_minutes:.1f} minutes)"
    )
    sys.exit(0)


def parse_health_file(health_file: Path) -> dict:
    """
    Parse the structured health status file.

    Expected format:
        Line 1: STATUS YYYY-MM-DDTHH:MM:SS.ffffff+HH:MM
        Line 2: ALERT_TYPE: ClassName
        Line 3: TIMEZONE: timezone_name
        Line 4: ERROR_MSG: message (optional, only if ERROR)

    Args:
        health_file: Path to health_status.txt

    Returns:
        Dictionary with parsed health data:
            - status: "OK" or "ERROR"
            - timestamp: timezone-aware datetime object
            - alert_type: Alert class name
            - timezone: Timezone name from file
            - error_msg: Error message (only if status is ERROR)

    Raises:
        ValueError: If file format is invalid
        Exception: If file cannot be read or parsed
    """
    content = health_file.read_text().strip()
    lines = content.split('\n')

    if len(lines) < 3:
        raise ValueError(f"Health file has insufficient lines: {len(lines)} (expected at least 3)")

    # Parse line 1: STATUS TIMESTAMP
    status_line = lines[0].strip()
    parts = status_line.split(' ', 1)

    if len(parts) != 2:
        raise ValueError(f"Invalid status line format: '{status_line}'")

    status = parts[0]
    timestamp_str = parts[1]

    if status not in ["OK", "ERROR"]:
        raise ValueError(f"Invalid status: '{status}' (expected OK or ERROR)")

    # Parse timestamp (ISO format with timezone)
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
    except ValueError as e:
        raise ValueError(f"Invalid timestamp format: '{timestamp_str}': {e}")

    # Ensure timestamp is timezone-aware
    if timestamp.tzinfo is None:
        raise ValueError(f"Timestamp is not timezone-aware: '{timestamp_str}'")

    # Parse line 2: ALERT_TYPE
    if not lines[1].startswith("ALERT_TYPE: "):
        raise ValueError(f"Invalid ALERT_TYPE line: '{lines[1]}'")
    alert_type = lines[1].replace("ALERT_TYPE: ", "").strip()

    # Parse line 3: TIMEZONE
    if not lines[2].startswith("TIMEZONE: "):
        raise ValueError(f"Invalid TIMEZONE line: '{lines[2]}'")
    timezone = lines[2].replace("TIMEZONE: ", "").strip()

    result = {
        'status': status,
        'timestamp': timestamp,
        'alert_type': alert_type,
        'timezone': timezone
    }

    # Parse line 4 (optional): ERROR_MSG
    if len(lines) >= 4 and lines[3].startswith("ERROR_MSG: "):
        error_msg = lines[3].replace("ERROR_MSG: ", "").strip()
        result['error_msg'] = error_msg

    return result


def get_effective_timezone() -> str:
    """
    Determine which timezone to use for time calculations.

    Precedence:
        1. SCHEDULE_TIMES_TIMEZONE (if set)
        2. TIMEZONE (if set)
        3. UTC (default fallback)

    Returns:
        Timezone name (e.g., "Europe/Athens", "UTC")
    """
    schedule_tz = os.getenv('SCHEDULE_TIMES_TIMEZONE', '').strip()
    if schedule_tz:
        return schedule_tz

    general_tz = os.getenv('TIMEZONE', '').strip()
    if general_tz:
        return general_tz

    return 'UTC'


def validate_health_file_structure(health_file: Path) -> None:
    """
    Perform initial validation of health file structure before parsing.

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is empty or has invalid structure
    """
    if not health_file.exists():
        raise FileNotFoundError(f"Health file not found: {health_file}")

    stat = health_file.stat()
    if stat.st_size == 0:
        raise ValueError("Health file is empty")

    if stat.st_size > 10000:  # 10KB limit
        raise ValueError(f"Health file is too large: {stat.st_size} bytes (max 10KB)")


def calculate_max_age() -> float:
    """
    Calculate maximum allowed age for health_status.txt based on schedule mode.

    Returns:
        Maximum age in minutes
    """
    freq_hours = os.getenv('SCHEDULE_FREQUENCY_HOURS', '').strip()
    schedule_times = os.getenv('SCHEDULE_TIMES', '').strip()

    # Mode 1: Frequency-based (e.g., every 2 hours)
    if freq_hours:
        try:
            hours = float(freq_hours)
            # Allow schedule interval + 10 minute buffer
            return hours * 60 + 10
        except (ValueError, TypeError):
            print(f"Invalid SCHEDULE_FREQUENCY_HOURS: {freq_hours}", file=sys.stderr)
            return 70  # Default fallback: 1 hour + 10 min buffer

    # Mode 2: Specific times (e.g., 12:00,18:00)
    elif schedule_times:
        try:
            return calculate_max_age_from_times(schedule_times)
        except Exception as e:
            print(f"Error calculating age from SCHEDULE_TIMES: {e}", file=sys.stderr)
            return 70  # Default fallback

    # Mode 3: No schedule defined (default to hourly + buffer)
    else:
        print("Warning: Neither SCHEDULE_FREQUENCY_HOURS nor SCHEDULE_TIMES set", file=sys.stderr)
        return 70  # 1 hour + 10 minute buffer


def calculate_max_age_from_times(schedule_times: str) -> float:
    """
    Calculate maximum age based on SCHEDULE_TIMES.

    For times like "12:00,18:00", the health file should be updated within
    10 minutes after the most recent scheduled time.

    Uses the effective timezone (SCHEDULE_TIMES_TIMEZONE or TIMEZONE) for
    determining "now" and calculating schedule times.

    Args:
        schedule_times: Comma-separated list of times (HH:MM format)

    Returns:
        Maximum age in minutes (time since most recent scheduled time + 10 min buffer)

    Note:
        This function uses timezone-aware datetime calculations to ensure
        correct behavior across different timezones.
    """
    # Get timezone-aware "now"
    tz_name = get_effective_timezone()
    try:
        now = datetime.now(tz=ZoneInfo(tz_name))
    except Exception as e:
        print(f"Invalid timezone '{tz_name}': {e}, falling back to UTC", file=sys.stderr)
        now = datetime.now(tz=ZoneInfo('UTC'))

    # Parse all scheduled times
    time_list = [t.strip() for t in schedule_times.split(',')]
    scheduled_datetimes = []

    for time_str in time_list:
        try:
            hour, minute = map(int, time_str.split(':'))

            # Create timezone-aware datetime for today
            scheduled_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            scheduled_datetimes.append(scheduled_today)

            # Also consider yesterday's schedule
            scheduled_yesterday = scheduled_today - timedelta(days=1)
            scheduled_datetimes.append(scheduled_yesterday)

        except (ValueError, IndexError) as e:
            print(f"Invalid time format '{time_str}': {e}", file=sys.stderr)
            continue

    if not scheduled_datetimes:
        print("No valid times found in SCHEDULE_TIMES", file=sys.stderr)
        return 70

    # Find the most recent scheduled time that has passed
    past_times = [dt for dt in scheduled_datetimes if dt <= now]

    if not past_times:
        # No scheduled time has passed yet today - use most recent from yesterday
        past_times = sorted(scheduled_datetimes)

    most_recent = max(past_times)

    # Calculate minutes since most recent scheduled time
    minutes_since = (now - most_recent).total_seconds() / 60

    # Allow the time since last schedule + 10 minute buffer
    return minutes_since + 10


if __name__ == "__main__":
    main()
```

#### Step 2: Update Your Dockerfile

Ensure these lines exist in your Dockerfile (typically after `COPY` commands):
```dockerfile
# Copy project structure including healthcheck
COPY scripts/ ./scripts/

# Make healthcheck script executable
RUN chmod +x /app/scripts/*.py

# Add healthcheck - interval depends on your schedule
HEALTHCHECK --interval=2m --timeout=10s --start-period=2m --retries=2 \
  CMD python3 /app/scripts/healthcheck.py
```

#### Step 3: Rebuild and Restart Containers
```bash
cd /path/to/your/project
docker compose build
docker compose up -d
```

### Healthcheck Configuration by Schedule Type

**For `SCHEDULE_TIMES` (specific times like 12:00,18:00):**
```dockerfile
HEALTHCHECK --interval=5m --timeout=10s --start-period=2m --retries=2 \
  CMD python3 /app/scripts/healthcheck.py
```

**For `SCHEDULE_FREQUENCY_HOURS=1` (hourly):**
```dockerfile
HEALTHCHECK --interval=2m --timeout=10s --start-period=2m --retries=2 \
  CMD python3 /app/scripts/healthcheck.py
```

**For `SCHEDULE_FREQUENCY_HOURS=0.25` (every 15 minutes):**
```dockerfile
HEALTHCHECK --interval=1m --timeout=10s --start-period=1m --retries=3 \
  CMD python3 /app/scripts/healthcheck.py
```

**For web applications (always running):**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
```

### Verifying Healthchecks
```bash
# Check healthcheck status
docker ps

# Detailed health information
docker inspect <container-name> | grep -A 20 Health

# Test healthcheck manually
docker exec <container-name> python3 /app/scripts/healthcheck.py

# Watch healthcheck in real-time
watch -n 5 'docker ps --format "table {{.Names}}\t{{.Status}}"'
```

## Health Status File Format

The `base_alert.py` writes a structured health status file that the healthcheck script validates:
```
OK 2025-12-16T12:05:30+02:00
ALERT_TYPE: MastersNavigationAuditAlert
TIMEZONE: Europe/Athens
```

Or for errors:
```
ERROR 2025-12-16T12:05:30+02:00
ALERT_TYPE: MastersNavigationAuditAlert
TIMEZONE: Europe/Athens
ERROR_MSG: Database connection timeout after 30 seconds
```

**Format rules:**
- Line 1: `STATUS TIMESTAMP` (STATUS is "OK" or "ERROR", TIMESTAMP is ISO 8601 with timezone)
- Line 2: `ALERT_TYPE: ClassName` (name of the alert class)
- Line 3: `TIMEZONE: timezone_name` (e.g., "Europe/Athens", "UTC")
- Line 4 (optional): `ERROR_MSG: message` (only present if STATUS is ERROR)

**Timezone handling:**
- The timestamp in line 1 is timezone-aware (includes +HH:MM offset)
- The healthcheck uses `SCHEDULE_TIMES_TIMEZONE` (if set), then `TIMEZONE`, then defaults to UTC
- File age is calculated using timezone-aware datetime arithmetic

## Usage

### Running the Monitor

**Foreground (for testing):**
```bash
# Ubuntu/Linux
cd /srv/repos/_docker_monitoring
python3 docker_health_monitor.py

# Mac/Development
cd ~/dev/alerts/_docker_monitoring
python3 docker_health_monitor.py
```

You should see output like:
```
======================================================================
Multi-Project Docker Health Monitor initialized
Server: Production Server
Default alert recipients: admin@example.com, ops@example.com
Check interval: 30 seconds
Retry delay: 15.0 minutes
======================================================================
======================================================================
▶ MULTI-PROJECT DOCKER HEALTH MONITOR STARTED
======================================================================
```

**Background with nohup:**
```bash
nohup python3 docker_health_monitor.py > /dev/null 2>&1 &
```

**As a systemd service (Ubuntu/Linux - recommended for production):**

Create `/etc/systemd/system/docker-health-monitor.service`:

```ini
[Unit]
Description=Multi-Project Docker Health Monitor
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/srv/repos/_docker_monitoring
ExecStart=/usr/bin/python3 /srv/repos/_docker_monitoring/docker_health_monitor.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Important:** If running as non-root user:
```bash
# Add user to docker group
sudo usermod -aG docker your-username

# Then use this in the service file
User=your-username
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable docker-health-monitor
sudo systemctl start docker-health-monitor
```

Check status:
```bash
sudo systemctl status docker-health-monitor
sudo journalctl -u docker-health-monitor -f
```

### Viewing Logs
```bash
# Real-time monitoring (from script directory)
tail -f logs/monitor.log

# View recent activity
tail -100 logs/monitor.log

# Search for specific container
grep "container-name" logs/monitor.log

# View all status changes
grep "→" logs/monitor.log
```

## How It Works

### Two-Phase Verification Pattern

The monitor uses a two-phase approach to eliminate false positives:

**Phase 1: Initial Health Checks (Concurrent)**
1. Monitor fetches all running Docker containers
2. Submits each container to thread pool (max 30 concurrent checks)
3. Workers call `get_container_health()` via Docker API
4. Results are categorized:
   - **No change:** Update last_check timestamp only
   - **Became unhealthy:** Add to retry queue (includes unknown→unhealthy, starting→unhealthy, healthy→unhealthy)
   - **Became healthy:** Add to immediate alert queue (recovery notification)

**Transition: Main Thread Sleep**
- If retry queue is empty: Sleep for `check_interval_sec` (30s default), then restart loop
- If retry queue has containers: Log count, then sleep for `wait_and_check_again_min` (15 min default)
- Sleep is interruptible every 1 second to allow graceful shutdown

**Phase 2: Recheck Unhealthy (Concurrent)**
1. Submit all queued containers to thread pool for recheck
2. Workers call `recheck_single_container()` via Docker API
3. For each result:
   - **Still unhealthy:** Fetch logs, send alert email
   - **Now healthy:** Log recovery, update state, no alert
   - **Not found:** Send not_found alert

**After Phase 2:**
- Sleep for `check_interval_sec` (30s)
- Return to Phase 1

### Why This Pattern Works

**Eliminates False Positives:**
- Transient failures during deployments won't trigger alerts
- Network hiccups are given time to resolve
- Container restarts are given time to complete
- Only persistent issues (lasting 15+ minutes) generate alerts

**Efficient Resource Usage:**
- Thread pool limits concurrent Docker API calls to 30
- Main thread sleeps during wait (no wasted CPU)
- Interruptible sleep allows clean shutdown
- Scales to hundreds of containers efficiently

**Simple and Reliable:**
- No complex background task scheduling
- No retry futures to track
- Single main loop is easy to reason about
- Thread-safe state management
- Works across platforms (Mac, Ubuntu, other Linux)

### Example Timeline
```
00:00 - Phase 1: Check 50 containers (concurrent)
00:05 - Results: 48 healthy, 2 unhealthy (app-1, db-1)
00:05 - Main thread sleeps for 15 minutes (interruptible)
00:20 - Phase 2: Recheck app-1 and db-1 (concurrent)
00:20 - Results: app-1 recovered, db-1 still unhealthy
00:20 - Actions: Log app-1 recovery, send alert for db-1 with logs
00:20 - Sleep for 30 seconds
00:20:30 - Return to Phase 1
```

## Project-Specific Routing

Route alerts to different teams based on container or project names:
```bash
# In .env
CONTAINER_ALERT_ROUTING=passage-plan:maritime@example.com;vessel-cert:compliance@example.com;hot-works:safety@example.com
```

**How it works:**
- Pattern matching against container name OR project name
- First match wins
- Falls back to `HEALTH_CHECK_ALERT_EMAILS` if no match
- Multiple recipients per pattern supported (comma-separated)

**Example:**
```bash
# Container: passage-plan-web-1
# Project: passage-plan
# Pattern: passage-plan
# Result: Email sent to maritime@example.com
```

## Alert Examples

### Critical Alert (Unhealthy Container)
```
Subject: CRITICAL!! CRITICAL: [passage-plan] passage-plan-web-1 - Health Status Changed

Docker Container Health Alert
==============================

Server:          Production Server
Project:         passage-plan
Container:       passage-plan-web-1
Status Change:   healthy → unhealthy
Severity:        CRITICAL
Time:            2025-12-15 14:23:45

Details:
--------
Container remained unhealthy after 15.0 minute(s).

Recent logs:

[2025-12-15 14:20:12] ERROR: Database connection failed
[2025-12-15 14:20:13] ERROR: Retrying in 5 seconds...
[2025-12-15 14:20:18] ERROR: Still cannot connect
...

Action Required:
----------------
1. Check container logs:
   docker logs passage-plan-web-1

2. Inspect container:
   docker inspect passage-plan-web-1

3. Restart container:
   docker restart passage-plan-web-1
   
   Or navigate to project and restart:
   cd /path/to/passage-plan
   docker compose restart

4. Check application health endpoint

5. Review recent code changes or deployments


Project Context:
----------------
Container name: passage-plan-web-1
Project name:   passage-plan
Status:         unhealthy

---
Automated alert from Multi-Project Docker Health Monitor
Server: Production Server
Monitoring all containers with healthchecks
```

### Recovery Alert
```
Subject: INFO INFO: [passage-plan] passage-plan-web-1 - Health Status Changed

Docker Container Health Alert
==============================

Server:          Production Server
Project:         passage-plan
Container:       passage-plan-web-1
Status Change:   unhealthy → healthy
Severity:        INFO
Time:            2025-12-15 14:25:30

Details:
--------
Container recovered to healthy status.

Action Required:
----------------
Monitor the situation and check logs for more information.
```

### Container Not Found Alert
```
Subject: ERROR! ERROR: [passage-plan] passage-plan-worker-1 - Health Status Changed

Docker Container Health Alert
==============================

Server:          Production Server
Project:         passage-plan
Container:       passage-plan-worker-1
Status Change:   healthy → not_found
Severity:        ERROR
Time:            2025-12-15 14:30:15

Details:
--------
Container is no longer running or has been removed.

Action Required:
----------------
1. Check if container is running:
   docker ps -a | grep passage-plan-worker-1

2. Navigate to project directory:
   cd /path/to/passage-plan

3. Check docker-compose status:
   docker compose ps

4. Restart services:
   docker compose up -d

5. Check docker-compose.yml configuration
```

## Troubleshooting

### Monitor Not Starting

**1. Check configuration loading:**
```bash
python3 -c "from decouple import config; print('SMTP_HOST:', config('SMTP_HOST')); print('EMAILS:', config('HEALTH_CHECK_ALERT_EMAILS'))"
```

**2. Verify Docker access:**
```bash
docker ps
# If this fails, you don't have Docker permissions
```

**3. Check Python dependencies:**
```bash
python3 -c "import docker; import decouple; print('Dependencies OK')"
```

### Containers Not Being Monitored

**Check if container has healthcheck:**
```bash
docker inspect <container-name> | grep -A 20 Health
```

**If no healthcheck found:**
- Add `scripts/healthcheck.py` to your project
- Update Dockerfile with HEALTHCHECK line
- Rebuild: `docker compose build`
- Restart: `docker compose up -d`

**If healthcheck exists but shows "starting" status:**
```bash
# Increase start_period in Dockerfile
HEALTHCHECK --start-period=5m ...

# Or check if healthcheck script has errors
docker exec <container> python3 /app/scripts/healthcheck.py
```

### Emails Not Sending

**Test SMTP connection (port 587 - STARTTLS):**
```bash
python3 << 'EOF'
import smtplib
from decouple import config

try:
    server = smtplib.SMTP(config('SMTP_HOST'), int(config('SMTP_PORT', 587)))
    server.starttls()
    server.login(config('SMTP_USER'), config('SMTP_PASS'))
    print('✓ SMTP connection successful (STARTTLS)')
    server.quit()
except Exception as e:
    print(f'✗ SMTP connection failed: {e}')
EOF
```

**Test SMTP connection (port 465 - SSL):**
```bash
python3 << 'EOF'
import smtplib
from decouple import config

try:
    server = smtplib.SMTP_SSL(config('SMTP_HOST'), int(config('SMTP_PORT', 465)))
    server.login(config('SMTP_USER'), config('SMTP_PASS'))
    print('✓ SMTP connection successful (SSL)')
    server.quit()
except Exception as e:
    print(f'✗ SMTP connection failed: {e}')
EOF
```

**Common SMTP issues:**
- `[SSL: WRONG_VERSION_NUMBER]` → Wrong port for connection type (try changing port 465↔587)
- `Authentication failed` → Wrong username/password, or app password required
- `Connection refused` → Wrong SMTP_HOST or firewall blocking

**For Gmail users:**
1. Enable 2-Factor Authentication
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Use App Password in `SMTP_PASS` (not regular password)
4. Use `SMTP_PORT=587`

**For custom SMTP servers:**
- Contact your email admin for correct settings
- Port 587 (STARTTLS) is more common than 465 (SSL)
- Some servers require different authentication methods

### False Positives During Deployments

**Increase retry wait time:**
```bash
# In .env
WAIT_AND_CHECK_AGAIN_MIN=20
```

**Or improve healthcheck `start_period`:**
```dockerfile
HEALTHCHECK --start-period=5m ...
```

### Healthcheck Script Errors

**Test the healthcheck script:**
```bash
# Inside container
docker exec <container> python3 /app/scripts/healthcheck.py

# Check health file exists
docker exec <container> ls -lh /app/logs/health_status.txt

# Check health file content
docker exec <container> cat /app/logs/health_status.txt

# Check environment variables
docker exec <container> env | grep SCHEDULE
```

## Best Practices

### Healthcheck Design Principles

**Good healthcheck characteristics:**
- Checks actual application functionality
- Completes in < 1 second
- Has appropriate start_period for slow-starting apps
- Uses reasonable interval (1-5 minutes for scheduled tasks)
- Includes retry logic (retries: 2-3)

**Bad healthcheck characteristics:**
- Only checks if port is open
- Takes too long to execute (> 5 seconds)
- No start_period (fails during boot)
- Too frequent interval (< 30s for scheduled tasks)

### Alert Tuning

**For frequently restarting containers:**
```bash
WAIT_AND_CHECK_AGAIN_MIN=20
HEALTH_CHECK_INTERVAL_SEC=60
```

**For critical services:**
```bash
WAIT_AND_CHECK_AGAIN_MIN=5
HEALTH_CHECK_INTERVAL_SEC=15
```

**For development environments:**
```bash
WAIT_AND_CHECK_AGAIN_MIN=1  # Fast testing
HEALTH_CHECK_INTERVAL_SEC=60
```

### Production Deployment Checklist

- [ ] Test in staging environment first
- [ ] Start with longer retry delays (15-20 minutes)
- [ ] Monitor logs daily for first week
- [ ] Verify SMTP credentials work (test both ports if needed)
- [ ] Test with intentional container failure
- [ ] Set up systemd service for automatic restart (Ubuntu)
- [ ] Configure project-specific routing
- [ ] Add monitor email to allow-list
- [ ] Document alert response procedures
- [ ] Verify all containers have healthchecks

## Graceful Shutdown

The monitor handles `SIGTERM` and `SIGINT` signals properly:

**Shutdown behavior:**
1. Signal received (SIGTERM, SIGINT, or Ctrl+C)
2. `shutdown_requested` flag set
3. Current operation completes:
   - If in Phase 1: Finishes collecting results
   - If sleeping: Interrupts sleep within 1 second
   - If in Phase 2: Finishes rechecks and alerts
4. ThreadPoolExecutor shutdown initiated
5. Waits for in-flight Docker API calls
6. Exits cleanly

**The interruptible sleep ensures:**
- Quick response to shutdown signals
- No alerts lost during shutdown
- Clean exit without hanging

## FAQ

**Q: Does this work with Docker Swarm?**  
A: Yes, monitors all containers visible to Docker API.

**Q: Can I monitor containers without healthchecks?**  
A: No. Containers must have healthchecks defined. Monitor skips containers without them.

**Q: How many containers can this monitor?**  
A: Tested with 100+ containers. Scales efficiently with 30 concurrent workers.

**Q: What happens during deployments?**  
A: The 15-minute retry prevents false alerts. Containers that recover within retry window won't trigger alerts.

**Q: Can I get Slack notifications instead of email?**  
A: Yes, modify `send_alert_email()` method to call your webhook.

**Q: Why doesn't my container appear in monitoring?**  
A: Three common reasons:
1. No healthcheck defined in Dockerfile
2. Container just started (wait 30 seconds for first check)
3. Healthcheck script has errors (test manually)

**Q: Can I test without waiting 15 minutes?**  
A: Yes, temporarily set `WAIT_AND_CHECK_AGAIN_MIN=1` in .env

**Q: Does it work on Mac?**  
A: Yes! The script uses relative paths and works on Mac, Ubuntu, and other Linux distributions.

**Q: What's the difference between port 465 and 587?**  
A: Port 587 uses STARTTLS (most common), port 465 uses direct SSL. The script detects and uses the appropriate method automatically.

**Q: How do I find my container name for `docker exec`?**
A: Run `docker ps --format "{{.Names}}"` to list all container names. Use the name from the NAMES column, not the service name from docker-compose.yml.

**Q: Why does my healthcheck show a different max age than expected?**
A: The max age is calculated as: `SCHEDULE_FREQUENCY_HOURS × 60 + 10 minutes buffer`. For time-based schedules, it's `minutes since last scheduled time + 10 minutes`. Check your `SCHEDULE_FREQUENCY_HOURS` or `SCHEDULE_TIMES` environment variable.

**Q: What timezone does the healthcheck use?**
A: Priority order: `SCHEDULE_TIMES_TIMEZONE` > `TIMEZONE` > UTC (default). Set `SCHEDULE_TIMES_TIMEZONE=Europe/Athens` in your project's `.env` for time-based schedules.

**Q: Can I test the healthcheck without waiting for it to fail naturally?**
A: Yes, use the Python method in "Testing Healthcheck Failures" to write an old timestamp or ERROR status to the health file, then run the healthcheck script manually.

## Performance Characteristics

**CPU:**
- Idle: ~0-1%
- Phase 1: 5-15% (depends on container count)
- Phase 2: 2-10%

**Memory:**
- Base: ~50-80 MB
- Per container: ~1-2 MB
- 100 containers: ~150-250 MB total

**Disk:**
- Log files: Max 50 MB (10 MB × 5 rotated files)
- Relative to script location

**Timing (50 containers, 30 workers):**
- Phase 1: ~2-3 seconds
- Sleep: 15 minutes (configurable)
- Phase 2: ~1 second
- Total cycle: ~15 minutes 6 seconds

## Support

For issues:

1. Check logs: `tail -f logs/monitor.log` (from script directory)
2. Verify configuration: `python3 -c "from decouple import config; print(config('SMTP_HOST'))"`
3. Test SMTP: See Troubleshooting section (test both ports if needed)
4. Ensure healthchecks: `docker inspect <container> | grep -A 10 Health`
5. Check Docker permissions: `docker ps`

## Changes from Previous Versions

**Version 2.2 (Current):**
- Added timezone-aware healthcheck with structured file parsing
- Added `parse_health_file()` for robust health status validation
- Added `get_effective_timezone()` for timezone precedence
- Improved error messages with status, alert type, and age information
- Added atomic write in `base_alert.py` to prevent file corruption
- Enhanced documentation for testing and troubleshooting

**Version 2.1:**
- Fixed `became_unhealthy` logic to trigger on `unknown→unhealthy` transitions
- Added interruptible sleep with 1-second intervals
- Fixed SMTP port handling (auto-detects 587 vs 465)
- Made log paths relative and cross-platform compatible
- Improved shutdown handling

**Version 2.0:**
- Initial two-phase verification pattern
- Thread pool for concurrent health checks
- Project-aware alerting

---

**Version:** 2.2  
**Last Updated:** December 2025  
**Python Version:** 3.7+  
**Docker API Version:** Compatible with Docker Engine 19.03+  
**Platforms:** Ubuntu, Mac, other Linux distributions

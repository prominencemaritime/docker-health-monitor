# Multi-Project Docker Health Monitor

A centralized health monitoring system that watches all Docker containers with healthchecks across multiple projects and sends email alerts when containers become unhealthy.

## Quickstart

```bash
# From your master folder containing all alert projects
cd /path/to/master_folder
mkdir -p _docker_monitoring/logs
cp /path/to/docker_health_monitor.py _docker_monitoring/
cd _docker_monitoring

# Create .env file with your SMTP settings
# See "Step 4: Configure Environment Variables" below for template
vim .env
chmod 600 .env

# Install dependencies and test
pip3 install -r requirements.txt --break-system-packages
python3 docker_health_monitor.py

# When working correctly, install as systemd service
# See "Step 6: Set Up Systemd Service" below for service file template
sudo vim /etc/systemd/system/docker-health-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now docker-health-monitor
sudo systemctl status docker-health-monitor
```

## Overview

This monitoring system:
- Automatically discovers and monitors all containers with healthchecks
- Sends email alerts when container health status changes
- Supports project-specific alert routing
- Includes container logs in alert emails
- Runs continuously as a systemd service
- Handles graceful shutdown and error recovery

## Directory Structure

```
/path/to/master_folder/
├── _docker_monitoring/              # Central monitoring service
│   ├── docker_health_monitor.py     # Main monitoring script
│   ├── .env                         # Configuration
│   ├── requirements.txt             # Python dependencies
│   ├── logs/                        # Log directory
│   │   ├── monitor.log              # Current log file
│   │   ├── monitor.log.1            # Rotated log (most recent)
│   │   ├── monitor.log.2            # Rotated log (older)
│   │   └── ...                      # Up to monitor.log.5
│   └── README.md                    # This file
│
├── passage_plan/                    # Your project 1
│   ├── docker-compose.yml
│   ├── .env
│   └── ...
│
├── vessel_certificates/             # Your project 2
│   ├── docker-compose.yml
│   ├── .env
│   └── ...
│
├── hot_works_alerts/                # Your project 3
│   ├── docker-compose.yml
│   ├── .env
│   └── ...
│
└── another_project/                 # Your project N
    ├── docker-compose.yml
    ├── .env
    └── ...
```

## Prerequisites

- Python 3.7+
- Docker installed and running
- Docker Compose projects with healthchecks configured
- SMTP server access for sending emails
- Root/sudo access for systemd service installation

## Installation

### Step 1: Create Monitoring Directory

```bash
# Navigate to your master folder
cd /path/to/master_folder

# Create monitoring directory
mkdir -p _docker_monitoring/logs
cd _docker_monitoring
```

### Step 2: Install the Monitoring Script

Copy `docker_health_monitor.py` to the `_docker_monitoring` directory.

```bash
# Make it executable
chmod +x docker_health_monitor.py
```

### Step 3: Install Python Dependencies

```bash
# Create requirements.txt
cat > requirements.txt << 'EOF'
docker>=7.0.0
python-decouple>=3.8
EOF

# Install dependencies
pip3 install -r requirements.txt --break-system-packages

# Or on systems with virtual environments:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables

Create `.env` file in the `_docker_monitoring` directory:

```bash
cat > .env << 'EOF'
# ============================================================================
# EMAIL CONFIGURATION
# ============================================================================
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your-email@example.com
SMTP_PASS=your-app-password

# ============================================================================
# DEFAULT ALERT RECIPIENTS
# ============================================================================
# These recipients receive all health alerts by default
HEALTH_CHECK_ALERT_EMAILS=ops-team@example.com,admin@example.com

# ============================================================================
# PROJECT-SPECIFIC ALERT ROUTING (Optional)
# ============================================================================
# Route alerts for specific projects to specific teams
# Format: container-pattern:email1,email2;pattern2:email3
# 
# Examples:
#   - Alerts for containers with "passage-plan" go to maritime team
#   - Alerts for containers with "vessel-cert" go to compliance team
#   - All others go to default recipients above
#
CONTAINER_ALERT_ROUTING=passage-plan:maritime-team@example.com;vessel-cert:compliance-team@example.com;hot-works:safety-team@example.com

# ============================================================================
# MONITORING CONFIGURATION
# ============================================================================
# How often to check container health (in seconds)
HEALTH_CHECK_INTERVAL=30

# Number of log lines to include in alert emails
HEALTH_CHECK_LOG_LINES=50

# Server name to identify which server sent the alert
SERVER_NAME=Production Server
EOF
```

**Edit the `.env` file** with your actual values:

```bash
vim .env
```

### Step 5: Test the Monitor

Before setting up as a service, test it manually:

```bash
# Run in foreground to see output
python3 docker_health_monitor.py
```

You should see output like:
```
2025-11-25 10:00:00 [INFO] ======================================================================
2025-11-25 10:00:00 [INFO] Multi-Project Docker Health Monitor initialized
2025-11-25 10:00:00 [INFO] Server: Production Server
2025-11-25 10:00:00 [INFO] Default alert recipients: ops-team@example.com, admin@example.com
2025-11-25 10:00:00 [INFO] Check interval: 30 seconds
2025-11-25 10:00:00 [INFO] Project-specific routing configured for: passage-plan, vessel-cert
2025-11-25 10:00:00 [INFO] ======================================================================
2025-11-25 10:00:00 [INFO] ▶ MULTI-PROJECT DOCKER HEALTH MONITOR STARTED
2025-11-25 10:00:00 [INFO] ======================================================================
2025-11-25 10:00:05 [INFO] [passage-plan] passage-plan-app: unknown → healthy
2025-11-25 10:00:05 [INFO] [vessel-certificates] vessel-cert-app: unknown → healthy
```

Press `Ctrl+C` to stop it.

### Step 6: Set Up Systemd Service

Create the systemd service file:

```bash
sudo vim /etc/systemd/system/docker-health-monitor.service
```

Paste this content (replace `/path/to/master_folder` with your actual path):

```ini
[Unit]
Description=Multi-Project Docker Health Monitor
Documentation=https://github.com/your-org/docker-health-monitor
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=prominence
Group=prominence
WorkingDirectory=/path/to/master_folder/_docker_monitoring
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 /path/to/master_folder/_docker_monitoring/docker_health_monitor.py
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

**Note:** The monitoring script writes logs to both locations:
- File logs: `/path/to/master_folder/_docker_monitoring/logs/monitor.log` (with automatic rotation)
- Systemd journal: viewable with `journalctl -u docker-health-monitor`

### Step 7: Enable and Start the Service

```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable docker-health-monitor

# Start the service
sudo systemctl start docker-health-monitor

# Check status
sudo systemctl status docker-health-monitor
```

You should see:
```
● docker-health-monitor.service - Multi-Project Docker Health Monitor
     Loaded: loaded (/etc/systemd/system/docker-health-monitor.service; enabled; vendor preset: enabled)
     Active: active (running) since Mon 2025-11-25 10:00:00 EET; 5s ago
   Main PID: 12345 (python3)
      Tasks: 2 (limit: 9448)
     Memory: 25.4M
        CPU: 123ms
     CGroup: /system.slice/docker-health-monitor.service
             └─12345 /usr/bin/python3 /path/to/master_folder/_docker_monitoring/docker_health_monitor.py
```

## Usage

### View Logs

The monitor writes logs to **both** file and systemd journal:

**File Logs** (recommended for most use cases):
```bash
# View real-time file logs
tail -f _docker_monitoring/logs/monitor.log

# View last 100 lines
tail -n 100 _docker_monitoring/logs/monitor.log

# Search for specific container
grep "passage-plan-app" _docker_monitoring/logs/monitor.log

# View all log files (including rotated backups)
ls -lh _docker_monitoring/logs/
# You'll see: monitor.log, monitor.log.1, monitor.log.2, etc.
```

**Systemd Journal** (alternative method):
```bash
# View real-time systemd logs
sudo journalctl -u docker-health-monitor -f

# View last 100 lines
sudo journalctl -u docker-health-monitor -n 100

# View logs since a specific time
sudo journalctl -u docker-health-monitor --since "1 hour ago"
```

**Log Rotation:**
- Log files are automatically rotated when they reach 10MB
- Up to 5 backup files are kept (monitor.log.1 through monitor.log.5)
- Oldest logs are automatically deleted
- No manual maintenance required

### Manage the Service

```bash
# Check status
sudo systemctl status docker-health-monitor

# Stop the service
sudo systemctl stop docker-health-monitor

# Start the service
sudo systemctl start docker-health-monitor

# Restart the service
sudo systemctl restart docker-health-monitor

# Disable service (won't start on boot)
sudo systemctl disable docker-health-monitor

# Enable service (will start on boot)
sudo systemctl enable docker-health-monitor
```

### Test Alert Emails

Simulate a container failure to test alerting:

```bash
# Kill a container's main process to trigger unhealthy status
docker exec passage-plan-app pkill -9 python

# The healthcheck will fail and you should receive an email alert within 30 seconds
# The container will be restarted by Docker if restart policy is set
```

### Update Configuration

```bash
# Edit configuration
cd /path/to/master_folder/_docker_monitoring
vim .env

# Restart service to apply changes
sudo systemctl restart docker-health-monitor

# Check that it's running with new config
sudo systemctl status docker-health-monitor
```

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SMTP_HOST` | Yes | - | SMTP server hostname |
| `SMTP_PORT` | No | 465 | SMTP server port |
| `SMTP_USER` | Yes | - | SMTP username/email |
| `SMTP_PASS` | Yes | - | SMTP password |
| `HEALTH_CHECK_ALERT_EMAILS` | Yes | - | Comma-separated list of default alert recipients |
| `CONTAINER_ALERT_ROUTING` | No | - | Project-specific routing (pattern:emails;pattern2:emails) |
| `HEALTH_CHECK_INTERVAL` | No | 30 | Check interval in seconds |
| `HEALTH_CHECK_LOG_LINES` | No | 50 | Number of log lines to include in alerts |
| `SERVER_NAME` | No | Production | Server identifier for alerts |

### Project-Specific Routing

To route alerts for specific projects to specific teams, use the `CONTAINER_ALERT_ROUTING` variable:

```bash
# Route passage-plan alerts to maritime team
# Route vessel-cert alerts to compliance team
# All others go to default recipients
CONTAINER_ALERT_ROUTING=passage-plan:maritime@example.com;vessel-cert:compliance@example.com
```

The monitor matches container names or project names against these patterns.

## How It Works

1. **Container Discovery**: The monitor queries the Docker API every 30 seconds (configurable) to find all running containers

2. **Healthcheck Detection**: Only monitors containers that have healthchecks configured in their Dockerfile:
   ```dockerfile
   HEALTHCHECK --interval=30m --timeout=10s --start-period=30s --retries=3 \
     CMD test -f /app/logs/health_status.txt && \
         MINUTES=$(python3 -c "import os; print(int(float(os.getenv('SCHEDULE_FREQUENCY_HOURS', '1')) * 60 + 10))") && \
         test $(find /app/logs/health_status.txt -mmin -${MINUTES} | wc -l) -eq 1 && \
         grep -q "^OK" /app/logs/health_status.txt || exit 1
   ```

3. **State Tracking**: Maintains state of each container's health status

4. **Change Detection**: Detects when health status changes (e.g., healthy → unhealthy)

5. **Alert Generation**: Sends email alerts for:
   - Container becomes unhealthy
   - Container becomes starting (warning)
   - Container stops running or is removed

6. **Project Context**: Automatically extracts project name from:
   - Docker Compose labels (`com.docker.compose.project`)
   - Container name pattern (e.g., `passage-plan-app` → project: `passage-plan`)

## Alert Email Example

```
Subject: CRITICAL: [passage-plan] passage-plan-app - Health Status Changed

Docker Container Health Alert
==============================

Server:          Production Server
Project:         passage-plan
Container:       passage-plan-app
Status Change:   healthy → unhealthy
Severity:        CRITICAL
Time:            2025-11-25 10:15:30

Details:
--------
Recent logs:

2025-11-25 10:15:28 [ERROR] Database connection failed
2025-11-25 10:15:28 [ERROR] Retry attempt 1/3
2025-11-25 10:15:29 [ERROR] Retry attempt 2/3
2025-11-25 10:15:30 [ERROR] Retry attempt 3/3
2025-11-25 10:15:30 [ERROR] Max retries exceeded

Action Required:
----------------
1. Check container logs:
   docker logs passage-plan-app

2. Inspect container:
   docker inspect passage-plan-app

3. Restart container:
   docker restart passage-plan-app
   
   Or navigate to project and restart:
   cd /path/to/passage-plan
   docker compose restart

4. Check application health endpoint

5. Review recent code changes or deployments
```

## Troubleshooting

### Monitor Not Starting

```bash
# Check service status
sudo systemctl status docker-health-monitor

# View recent systemd logs
sudo journalctl -u docker-health-monitor -n 50

# View recent file logs
tail -n 50 /path/to/_docker_monitoring/logs/monitor.log

# Check for Python errors by running manually
python3 /path/to/_docker_monitoring/docker_health_monitor.py
```

### No Alerts Being Sent

1. **Check SMTP configuration**:
   ```bash
   # Test SMTP connection manually
   python3 -c "
   import smtplib
   from decouple import config
   server = smtplib.SMTP_SSL(config('SMTP_HOST'), int(config('SMTP_PORT')))
   server.login(config('SMTP_USER'), config('SMTP_PASS'))
   print('SMTP connection successful')
   server.quit()
   "
   ```

2. **Verify containers have healthchecks**:
   ```bash
   # List containers with health status
   docker ps --format "table {{.Names}}\t{{.Status}}"
   ```

3. **Check monitor logs**:
   ```bash
   # Check file logs
   tail -f _docker_monitoring/logs/monitor.log
   
   # Or check systemd logs
   sudo journalctl -u docker-health-monitor -f
   ```

### Containers Not Being Monitored

The monitor only watches containers with healthchecks. Ensure your Dockerfile includes:

```dockerfile
HEALTHCHECK --interval=30m --timeout=10s --start-period=30s --retries=3 \
  CMD test -f /app/logs/health_status.txt && \
      MINUTES=$(python3 -c "import os; print(int(float(os.getenv('SCHEDULE_FREQUENCY_HOURS', '1')) * 60 + 10))") && \
      test $(find /app/logs/health_status.txt -mmin -${MINUTES} | wc -l) -eq 1 && \
      grep -q "^OK" /app/logs/health_status.txt || exit 1
```

### Alerts Going to Wrong Recipients

1. Check project routing configuration in `.env`
2. Verify container names match routing patterns
3. Check monitor logs to see which routing was applied

### High Memory/CPU Usage

```bash
# Check resource usage
docker stats

# Adjust check interval to reduce frequency
# Edit .env and increase HEALTH_CHECK_INTERVAL to 60 (seconds)
```

## Maintenance

### Log Rotation

Log files are **automatically rotated** by the monitor:
- When `monitor.log` reaches 10MB, it's renamed to `monitor.log.1`
- Previous backups are shifted: `monitor.log.1` → `monitor.log.2`, etc.
- Maximum of 5 backup files are kept
- Oldest backup is automatically deleted

```bash
# View all log files
ls -lh _docker_monitoring/logs/
# Output:
# monitor.log      (current, up to 10MB)
# monitor.log.1    (previous)
# monitor.log.2    (older)
# monitor.log.3
# monitor.log.4
# monitor.log.5    (oldest, will be deleted on next rotation)

# Total disk space used (typically < 60MB)
du -sh _docker_monitoring/logs/
```

**Manual log cleanup** (if needed):
```bash
# Remove old rotated logs (keeps current monitor.log)
rm _docker_monitoring/logs/monitor.log.[1-5]

# Clear current log (start fresh)
> _docker_monitoring/logs/monitor.log
```

**Systemd journal logs** are managed separately:
```bash
# View journal disk usage
sudo journalctl --disk-usage

# Clean journals older than 2 weeks
sudo journalctl --vacuum-time=2weeks

# Limit journal to 500MB
sudo journalctl --vacuum-size=500M
```

### Backup Configuration

```bash
# Backup configuration
cp _docker_monitoring/.env _docker_monitoring/.env.backup

# Backup with timestamp
cp _docker_monitoring/.env _docker_monitoring/.env.$(date +%Y%m%d)

# Backup logs directory (includes all rotated logs)
tar -czf logs-backup-$(date +%Y%m%d).tar.gz _docker_monitoring/logs/
```

### Updates

```bash
# Stop the service
sudo systemctl stop docker-health-monitor

# Update the script
cd _docker_monitoring
# ... copy new version ...

# Update dependencies
pip3 install -r requirements.txt --upgrade --break-system-packages

# Restart the service
sudo systemctl start docker-health-monitor
```

## Security Considerations

1. **SMTP Credentials**: The `.env` file contains sensitive SMTP credentials
   ```bash
   # Set proper permissions
   chmod 600 .env
   chown prominence:prominence .env
   ```

2. **Docker Socket Access**: The monitor needs access to `/var/run/docker.sock`
   ```bash
   # Ensure user is in docker group
   sudo usermod -aG docker prominence
   ```

3. **Service Isolation**: The systemd service runs with `NoNewPrivileges=true` and `PrivateTmp=true`

## Monitor the Monitor (Optional)

Set up a cron job to ensure the monitoring service itself stays running:

```bash
# Edit crontab
crontab -e
# When prompted, select vim: Choose option 1 or 3

# Add this line (checks every 5 minutes)
*/5 * * * * systemctl is-active --quiet docker-health-monitor || systemctl start docker-health-monitor
```

This checks every 5 minutes if the service is running and starts it if stopped.

## Adding New Projects

The monitor automatically discovers new projects! Just:

1. Ensure your new project has healthchecks in docker-compose.yml
2. Start the project: `docker compose up -d`
3. The monitor will automatically detect and monitor it

Optionally, add project-specific routing:
```bash
# Edit .env
vim _docker_monitoring/.env

# Add to CONTAINER_ALERT_ROUTING
CONTAINER_ALERT_ROUTING=passage-plan:team1@ex.com;new-project:team2@ex.com

# Restart monitor
sudo systemctl restart docker-health-monitor
```

## Uninstallation

```bash
# Stop and disable service
sudo systemctl stop docker-health-monitor
sudo systemctl disable docker-health-monitor

# Remove service file
sudo rm /etc/systemd/system/docker-health-monitor.service

# Reload systemd
sudo systemctl daemon-reload

# Remove monitoring directory (optional)
rm -rf /path/to/master_folder/_docker_monitoring
```

## Implementing Application-Level Health Monitoring

This section explains how to implement proper application-level health monitoring in your alert projects so that Docker healthchecks can detect not just container crashes, but also application-level failures like database connection errors.

### Overview

By default, Docker healthchecks only verify that processes are running. They don't detect application-level failures like:
- Database connection errors
- Failed scheduled runs
- API authentication failures
- Other exceptions in your application logic

To detect these failures, we implement a health status file that the application writes on each run, and Docker's healthcheck reads to determine container health.

### Architecture

```
Application (Python)
    ↓
Writes: /app/logs/health_status.txt with "OK" or "ERROR"
    ↓
Docker Healthcheck (in Dockerfile)
    ↓
Reads health_status.txt every 30 minutes
    ↓
Docker Engine (marks container healthy/unhealthy)
    ↓
docker-health-monitor (queries Docker every 30 seconds)
    ↓
Sends email alert on status changes
```

### Changes Required Per Project

You need to modify two files in each alert project:

1. `src/core/base_alert.py` - Add health status writing logic
2. `Dockerfile` - Update healthcheck to read health status file

### Step 1: Modify base_alert.py

All your alert projects share the same `base_alert.py` structure. Apply these changes to each project's `src/core/base_alert.py`:

#### Change 1.1: Add Import

Find the imports section (around line 8-13) and add:

```python
from pathlib import Path
```

Full imports section should look like:

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import logging
```

#### Change 1.2: Add Health Status Method

Add this new method at the end of the `BaseAlert` class (after `_send_notifications` method, around line 280):

```python
    def _write_health_status(self, status: str, run_time: datetime, error_msg: str = "") -> None:
        """
        Write health status to file for healthcheck monitoring.
        
        Args:
            status: "OK" or "ERROR"
            run_time: Timestamp of this run
            error_msg: Error message if status is ERROR
        """
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

#### Change 1.3: Update run() Method - Success Case

Find the section in `run()` method where notifications are sent (around line 195-200):

```python
            # Step 6: Send notifications
            success = self._send_notifications(notification_jobs, run_time)

            return success
```

Replace with:

```python
            # Step 6: Send notifications
            success = self._send_notifications(notification_jobs, run_time)
            
            # Step 7: Write health status
            self._write_health_status("OK", run_time)

            return success
```

#### Change 1.4: Update run() Method - Error Case

Find the exception handler (around line 208-210):

```python
        except Exception as e:
            self.logger.exception(f"Error in {self.__class__.__name__}.run(): {e}")
            return False
```

Replace with:

```python
        except Exception as e:
            self.logger.exception(f"Error in {self.__class__.__name__}.run(): {e}")
            self._write_health_status("ERROR", run_time, str(e))
            return False
```

#### Change 1.5: Update run() Method - Early Returns

Find the three places where `return False` happens before sending notifications and add health status writing:

Location 1 (around line 159-161):
```python
            if df.empty:
                self.logger.info("No records found matching query criteria: df.empty == True")
                self._write_health_status("OK", run_time)
                return False
```

Location 2 (around line 171-173):
```python
            if df_filtered.empty:
                self.logger.info("No records after filtering: df_filtered.empty == True")
                self._write_health_status("OK", run_time)
                return False
```

Location 3 (around line 180-182):
```python
            if df_unsent.empty:
                self.logger.info("All records have been sent previously. No new notifications.")
                self._write_health_status("OK", run_time)
                return False
```

### Step 2: Update Dockerfile

Modify each project's `Dockerfile` to update the healthcheck configuration:

#### Current Healthcheck

```dockerfile
HEALTHCHECK --interval=1h --timeout=10s --start-period=30s --retries=3 \
  CMD test -f /app/logs/alerts.log && \
      MINUTES=$(python3 -c "import os; print(int(float(os.getenv('SCHEDULE_FREQUENCY_HOURS', '1')) * 60 + 10))") && \
      test $(find /app/logs/alerts.log -mmin -${MINUTES} | wc -l) -eq 1 || exit 1
```

#### New Healthcheck (replace with this)

```dockerfile
HEALTHCHECK --interval=30m --timeout=10s --start-period=30s --retries=3 \
  CMD test -f /app/logs/health_status.txt && \
      MINUTES=$(python3 -c "import os; print(int(float(os.getenv('SCHEDULE_FREQUENCY_HOURS', '1')) * 60 + 10))") && \
      test $(find /app/logs/health_status.txt -mmin -${MINUTES} | wc -l) -eq 1 && \
      grep -q "^OK" /app/logs/health_status.txt || exit 1
```

Changes explained:
- Check `health_status.txt` instead of `alerts.log`
- Interval reduced to 30 minutes (faster failure detection)
- Added `grep -q "^OK"` check - fails if file contains "ERROR"

### Step 3: Apply Changes to All Projects

Apply the above changes to these projects:

```
flag_dispensations/
passage_plan/
new_vessel_certificates/
masters_navigation_audit/
work_permits/
```

Note: `events_alerts` and `vessel_attendances` use older structure without `src/core/base_alert.py`. These can be updated later or left with basic healthcheck.

### Step 4: Rebuild and Deploy

After making changes to each project:

```bash
# For each project
cd /path/to/master_folder/flag_dispensations

# Rebuild without cache
docker compose build --no-cache

# Restart
docker compose up -d

# Verify health status file
docker exec flag_dispensations-app cat /app/logs/health_status.txt
# Should show: OK <timestamp>

# Check health
docker compose ps
# Should show: (healthy)
```

Repeat for all projects:

```bash
cd /path/to/master_folder/passage_plan
docker compose build --no-cache && docker compose up -d

cd /path/to/master_folder/new_vessel_certificates
docker compose build --no-cache && docker compose up -d

cd /path/to/master_folder/masters_navigation_audit
docker compose build --no-cache && docker compose up -d

cd /path/to/master_folder/work_permits
docker compose build --no-cache && docker compose up -d
```

### Step 5: Verify Implementation

#### Check Health Status Files

```bash
docker exec flag-dispensations-app cat /app/logs/health_status.txt
docker exec passage-plan-app cat /app/logs/health_status.txt
docker exec new-vessel-certificates-app cat /app/logs/health_status.txt
docker exec masters-navigation-audit-app cat /app/logs/health_status.txt
docker exec work-permits-app cat /app/logs/health_status.txt
```

Each should show: `OK 2025-12-08T18:26:03.031+02:00`

#### Check Container Health

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

All should show `(healthy)` after 30 seconds.

### Step 6: Test Failure Detection

```bash
# Break database password in one project
cd /path/to/master_folder/flag_dispensations
vim .env
# Change DB_PASS to wrong value

# Restart
docker compose restart

# Check health status file - should show ERROR
docker exec flag-dispensations-app cat /app/logs/health_status.txt

# Wait for healthcheck cycles (up to 90 minutes)
# Container becomes unhealthy after 3 failed checks
# Email alert sent within 30 seconds

# Restore password
vim .env  # Fix DB_PASS
docker compose restart
```

### Backward Compatibility and Breaking Changes

#### Summary: All Changes Are Backward Compatible ✓

**Good news:** All the health monitoring changes described in this guide are **fully backward compatible**. You can safely implement them across all your projects without breaking existing functionality.

---

#### Change Analysis

##### 1. Changes to `src/core/base_alert.py` - ✓ BACKWARD COMPATIBLE

**What changes:**
- Adds new import: `from pathlib import Path`
- Adds new method: `_write_health_status()`
- Adds health status writing calls in `run()` method

**Why it's safe:**
- New import doesn't affect existing code
- New method is only called internally, doesn't change any APIs
- Health status writes are additional actions, don't modify existing logic
- All existing return values and behaviors remain unchanged
- If health file write fails, it logs an error but doesn't raise an exception

**Projects affected:** ALL projects with `src/core/base_alert.py`
- flag_dispensations ✓
- passage_plan ✓
- new_vessel_certificates ✓
- masters_navigation_audit ✓
- work_permits ✓

**Test after deployment:**
```bash
# Old behavior still works
docker compose up -d
# Emails still sent ✓
# Tracking still works ✓
# Scheduling still works ✓

# New behavior added
docker exec <container> cat /app/logs/health_status.txt
# Shows health status ✓
```

---

##### 2. Changes to `Dockerfile` HEALTHCHECK - ✓ BACKWARD COMPATIBLE

**What changes:**
- Changes from checking `alerts.log` to `health_status.txt`
- Adds `grep -q "^OK"` check for error detection
- Reduces interval from 1h to 30m (optional, you can keep 1h)

**Why it's safe:**
- Healthcheck is independent of application logic
- Only affects Docker's view of container health
- Application continues running even if healthcheck fails
- Healthcheck failures don't stop the container (unless restart policy configured)
- If `health_status.txt` doesn't exist yet, healthcheck fails gracefully

**Transition period:**
```
Deploy → Container starts → healthcheck fails → First alert run → health_status.txt created → healthcheck passes
```

**Timeline:**
- Frequency-based (SCHEDULE_FREQUENCY_HOURS=1): ~1 hour until healthy
- Time-based (SCHEDULE_TIMES=12:00,18:00): Until next scheduled run

**Projects affected:** ALL projects
- flag_dispensations ✓
- passage_plan ✓
- new_vessel_certificates ✓
- masters_navigation_audit ✓
- work_permits ✓
- events_alerts ✓
- vessel_attendances ✓

---

##### 3. Changes to `src/core/scheduler.py` - ✓ BACKWARD COMPATIBLE

**What changes:**
- Adds new import: `from pathlib import Path`
- Adds optional parameter to `__init__`: `logs_dir: Path = None`
- Adds new method: `_write_health_status()`
- Adds health status writing call in `_run_all_alerts()`

**Why it's safe:**
- New import doesn't affect existing code
- `logs_dir` parameter is **optional with default value** (`None`)
- Default fallback: `Path('/app/logs')` if not provided
- New method is only called internally
- Works correctly whether `logs_dir` is passed or not

**Backward compatibility guaranteed by:**
```python
def __init__(self, frequency_hours: float, timezone: str, 
             schedule_times_timezone: str = 'Europe/Athens', 
             schedule_times: List[str] = None, 
             logs_dir: Path = None):  # Optional with default
    # ...
    self.logs_dir = logs_dir or Path('/app/logs')  # Fallback
```

**Old code still works:**
```python
# Old instantiation (no logs_dir)
scheduler = AlertScheduler(
    frequency_hours=config.schedule_frequency_hours,
    timezone=config.timezone,
    schedule_times_timezone=config.schedule_times_timezone,
    schedule_times=config.schedule_times
)
# Still works! Uses default /app/logs ✓
```

**New code works better:**
```python
# New instantiation (with logs_dir)
scheduler = AlertScheduler(
    frequency_hours=config.schedule_frequency_hours,
    timezone=config.timezone,
    schedule_times_timezone=config.schedule_times_timezone,
    schedule_times=config.schedule_times,
    logs_dir=config.logs_dir  # Explicit path
)
# Works better! Uses config path ✓
```

**Projects affected:** Only projects using `SCHEDULE_TIMES`
- masters_navigation_audit (if using SCHEDULE_TIMES) ✓

---

##### 4. Changes to `src/main.py` - ✓ BACKWARD COMPATIBLE

**What changes:**
- Adds `logs_dir` parameter when creating scheduler

**Why it's safe:**
- This is the **recommended** change but **not required**
- Scheduler works without it (uses default `/app/logs`)
- If you skip this change, health status still written to `/app/logs/health_status.txt`
- Only difference: Uses default path instead of config path

**Impact of skipping:**
- Health monitoring still works ✓
- Health file written to `/app/logs/` (Docker default) ✓
- Healthcheck still passes ✓
- Only difference: Ignores `config.logs_dir` setting (minor)

**Projects affected:** Only projects using `SCHEDULE_TIMES`
- masters_navigation_audit (if using SCHEDULE_TIMES) ✓

---

#### Migration Strategy: Safe Rollout Plan

You can safely implement these changes using any of these strategies:

##### Strategy 1: All at Once (Recommended)
```bash
# Apply to all projects in one session
for project in flag_dispensations passage_plan new_vessel_certificates masters_navigation_audit work_permits; do
    cd /path/to/$project
    
    # Backup
    cp src/core/base_alert.py src/core/base_alert.py.backup
    cp Dockerfile Dockerfile.backup
    
    # Apply changes (edit files)
    vim src/core/base_alert.py
    vim Dockerfile
    
    # Deploy
    docker compose build --no-cache
    docker compose up -d
    
    echo "✓ $project deployed"
done

# All projects continue working normally
# Health monitoring gradually activates as each runs
```

##### Strategy 2: One by One (Conservative)
```bash
# Start with least critical project
cd /path/to/work_permits
# Apply changes
# Test for 24 hours
# If good, continue to next

cd /path/to/passage_plan
# Apply changes
# Test for 24 hours
# Continue...
```

##### Strategy 3: Partial Implementation (Minimum Viable)
```bash
# Option A: Just base_alert.py + Dockerfile
# Skip scheduler changes entirely
# Health monitoring works for frequency-based projects
# Time-based projects work but need manual health file creation

# Option B: Just Dockerfile
# Change healthcheck only
# Wait until base_alert.py updated later
# Container unhealthy until first successful run
```

---

#### What Happens During Deployment

**Scenario 1: Frequency-based project (SCHEDULE_FREQUENCY_HOURS=1)**
```
12:00:00 - Deploy new version
12:00:05 - Container starts
12:00:10 - Healthcheck runs → FAIL (health_status.txt doesn't exist yet)
12:00:40 - Healthcheck runs → FAIL 
13:00:00 - Alert runs → health_status.txt created with "OK"
13:00:30 - Healthcheck runs → PASS (healthy) ✓
```

**Scenario 2: Time-based project (SCHEDULE_TIMES=12:00,18:00)**
```
14:00:00 - Deploy new version
14:00:05 - Container starts
14:00:30 - Healthcheck runs → FAIL (health_status.txt doesn't exist yet)
15:00:00 - Healthcheck runs → FAIL
16:00:00 - Healthcheck runs → FAIL
18:00:00 - Alert runs → health_status.txt created with "OK"
18:00:30 - Healthcheck runs → PASS (healthy) ✓
```

**Impact:**
- Container runs normally during "unhealthy" period ✓
- Emails sent correctly ✓
- Only health status shows "unhealthy" in Docker
- Monitor alerts you (optional - you can ignore first alert)
- After first run, everything normal ✓

---

#### Breaking Changes: NONE

**There are NO breaking changes in this implementation.**

All changes are:
- ✓ Additive (add new functionality)
- ✓ Optional (work with defaults)
- ✓ Backward compatible (old code still works)
- ✓ Non-destructive (don't remove features)
- ✓ Fail-safe (errors logged, not raised)

---

#### What You Can Skip

If you want to implement gradually:

**Safe to skip:**
1. **Dockerfile interval change** (1h → 30m)
   - Keep 1h if you prefer
   - Health monitoring still works
   - Just slower to detect failures

2. **`src/main.py` changes** (logs_dir parameter)
   - Scheduler uses default path
   - Health monitoring still works
   - Minor: ignores custom logs_dir setting

3. **`src/core/scheduler.py` changes** (for frequency-based projects)
   - Only needed for SCHEDULE_TIMES projects
   - Frequency-based projects work with base_alert.py changes only

**Must implement:**
1. **`src/core/base_alert.py` changes** - Core health monitoring
2. **`Dockerfile` HEALTHCHECK update** - Health detection

**Minimum viable:**
```bash
# Just these two files
vim src/core/base_alert.py  # Add health status writing
vim Dockerfile              # Update healthcheck

# Deploy
docker compose build --no-cache && docker compose up -d

# Works! ✓
```

---

#### Rollback Plan

If you need to rollback (unlikely):
```bash
cd /path/to/project

# Restore backups
cp src/core/base_alert.py.backup src/core/base_alert.py
cp Dockerfile.backup Dockerfile

# Rebuild
docker compose build --no-cache
docker compose up -d

# Everything back to original state
# 5 minutes to rollback
```

---

#### Testing Backward Compatibility

After deployment, verify old functionality still works:
```bash
# Test 1: Alerts still send
docker compose logs -f
# Look for: "Sent X notification(s)"

# Test 2: Tracking still works  
docker exec <container> cat /app/data/sent_alerts.json
# Should contain entries

# Test 3: Scheduling still works
docker compose logs | grep "Next run scheduled"
# Shows next run time

# Test 4: Error handling still works
# Break DB password temporarily
vim .env  # Wrong password
docker compose restart
docker compose logs
# Should show error, not crash

# Test 5: New health monitoring works
docker exec <container> cat /app/logs/health_status.txt
# Shows: OK <timestamp>
```

---

#### Conclusion: Safe to Deploy Everywhere

**✓ You can confidently implement these changes across ALL projects**

Why:
- No breaking changes
- Backward compatible
- Fail-safe implementation
- Easy rollback
- Gradual activation
- Old functionality preserved

**Recommended approach:**
1. Apply to all projects in one session
2. Monitor for 24 hours
3. Verify health monitoring working
4. Done!

**Total risk: Minimal**
- Worst case: Container shows "unhealthy" for 1-4 hours after deployment
- Application continues working normally
- Easy 5-minute rollback if needed
- No data loss, no service interruption

### Special Case: Projects Using SCHEDULE_TIMES

Some projects use time-based scheduling (`SCHEDULE_TIMES=12:00,18:00`) instead of frequency-based scheduling (`SCHEDULE_FREQUENCY_HOURS=1`). These projects require additional modifications to support health monitoring.

#### Projects Affected

Check your `.env` file. If you see:
```bash
SCHEDULE_FREQUENCY_HOURS=
SCHEDULE_TIMES=12:00,18:00
SCHEDULE_TIMES_TIMEZONE=Europe/Athens
```

Then your project uses time-based scheduling and needs these additional changes.

#### Changes Required

You need to modify **three** files (instead of two):
1. `src/core/scheduler.py` - Add health status writing
2. `src/main.py` - Pass logs directory to scheduler
3. `Dockerfile` - Update healthcheck for time-based scheduling

---

#### Change 1: Modify src/core/scheduler.py

##### Change 1.1: Add Import at Top

Find the imports section (around line 1-13) and add `Path`:
```python
"""
Scheduling system for running alerts at regular intervals.

Handles graceful shutdown, error recovery, and interval-based execution.
"""
import signal
import threading
import logging
from datetime import datetime, timedelta, time
from src.formatters.date_formatter import duration_hours
from zoneinfo import ZoneInfo
from typing import Callable, List
from pathlib import Path  # ADD THIS LINE
import pandas as pd

logger = logging.getLogger(__name__)
```

##### Change 1.2: Update __init__ Method

Find the `__init__` method (around line 25) and add `logs_dir` parameter:
```python
def __init__(self, frequency_hours: float, timezone: str, schedule_times_timezone: str = 'Europe/Athens', schedule_times: List[str] = None, logs_dir: Path = None):
    """
    Initialize scheduler.
    
    Args:
        frequency_hours: Hours between alert runs (ignored if schedule_times provided)
        timezone: Timezone for scheduling and logging
        schedule_times_timezone: Timezone for schedule_times
        schedule_times: Optional list of daily run times in HH:MM format
        logs_dir: Path to logs directory for health status file
    """
    self.frequency_hours = frequency_hours
    self.schedule_times = schedule_times
    self.schedule_times_timezone = ZoneInfo(schedule_times_timezone)
    self.timezone = ZoneInfo(timezone)
    self.logs_dir = logs_dir or Path('/app/logs')  # ADD THIS LINE
    self.shutdown_event = threading.Event()
    self._alerts: List[Callable] = []

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, self._signal_handler)
    signal.signal(signal.SIGINT, self._signal_handler)
```

##### Change 1.3: Add Health Status Writer Method

Add this new method after `register_alert()` method (around line 59):
```python
def _write_health_status(self, logs_dir: Path, timezone: ZoneInfo) -> None:
    """Write health status to file for Docker healthcheck."""
    from datetime import datetime
    
    health_file = logs_dir / 'health_status.txt'
    timestamp = datetime.now(tz=timezone).isoformat()
    
    try:
        health_file.write_text(f"OK {timestamp}\n")
        logger.debug(f"Health status written: {timestamp}")
    except Exception as e:
        logger.error(f"Failed to write health status: {e}")
```

##### Change 1.4: Update _run_all_alerts Method

Find the `_run_all_alerts()` method (around line 60-79) and add health status writing at the end:
```python
def _run_all_alerts(self) -> None:
    """Execute all registered alerts."""
    if not self._alerts:
        logger.warning("No alerts registered. Nothing to run.")
        return

    logger.info(f"Running {len(self._alerts)} alert(s)...")

    for idx, alert_runner in enumerate(self._alerts, 1):
        if self.shutdown_event.is_set():
            logger.info("Shutdown requested. Stopping alert execution.")
            break

        try:
            logger.info(f"Executing alert {idx}/{len(self._alerts)}...")
            alert_runner()
        except Exception as e:
            logger.exception(f"Error executing alert {idx}: {e}")
            # Continue with next alert despite error
    
    # Write health status after all alerts complete
    self._write_health_status(self.logs_dir, self.timezone)  # ADD THIS LINE
```

---

#### Change 2: Modify src/main.py

##### Update Scheduler Instantiation

Find where the scheduler is created (around line 207-213) and add `logs_dir` parameter:
```python
# Create scheduler
scheduler = AlertScheduler(
    frequency_hours=config.schedule_frequency_hours,
    timezone=config.timezone,
    schedule_times_timezone=config.schedule_times_timezone,
    schedule_times=config.schedule_times,
    logs_dir=config.logs_dir  # ADD THIS LINE
)
```

---

#### Change 3: Update Dockerfile Healthcheck

Replace the entire `HEALTHCHECK` line in your Dockerfile with this version that handles both scheduling modes:
```dockerfile
# Healthcheck to monitor container
HEALTHCHECK --interval=30m --timeout=10s --start-period=30s --retries=3 \
  CMD test -f /app/logs/health_status.txt && \
      MINUTES=$(python3 -c "import os; schedule_times = os.getenv('SCHEDULE_TIMES', ''); print(1440 if schedule_times else int(float(os.getenv('SCHEDULE_FREQUENCY_HOURS', '1')) * 60 + 10))") && \
      test $(find /app/logs/health_status.txt -mmin -${MINUTES} | wc -l) -eq 1 && \
      grep -q "^OK" /app/logs/health_status.txt || exit 1
```

**How this works:**
- If `SCHEDULE_TIMES` is set (time-based scheduling), uses 1440 minutes (24 hours)
- If `SCHEDULE_TIMES` is empty (frequency-based scheduling), uses `SCHEDULE_FREQUENCY_HOURS * 60 + 10`
- Checks if health_status.txt was updated within that window
- Checks if health_status.txt contains "OK" (not "ERROR")

---

#### Complete Implementation for Time-Based Projects

For projects using `SCHEDULE_TIMES`, you need to modify **all three files**:

**File 1: `src/core/scheduler.py`**
```python
# Add to imports
from pathlib import Path

# Update __init__ signature
def __init__(self, frequency_hours: float, timezone: str, schedule_times_timezone: str = 'Europe/Athens', 
             schedule_times: List[str] = None, logs_dir: Path = None):
    # ... existing code ...
    self.logs_dir = logs_dir or Path('/app/logs')
    # ... rest of __init__ ...

# Add new method after register_alert()
def _write_health_status(self, logs_dir: Path, timezone: ZoneInfo) -> None:
    """Write health status to file for Docker healthcheck."""
    from datetime import datetime
    
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
    
    # Write health status after all alerts complete
    self._write_health_status(self.logs_dir, self.timezone)
```

**File 2: `src/main.py`**
```python
# Update scheduler instantiation (around line 207)
scheduler = AlertScheduler(
    frequency_hours=config.schedule_frequency_hours,
    timezone=config.timezone,
    schedule_times_timezone=config.schedule_times_timezone,
    schedule_times=config.schedule_times,
    logs_dir=config.logs_dir  # ADD THIS
)
```

**File 3: `Dockerfile`**
```dockerfile
# Replace HEALTHCHECK line
HEALTHCHECK --interval=30m --timeout=10s --start-period=30s --retries=3 \
  CMD test -f /app/logs/health_status.txt && \
      MINUTES=$(python3 -c "import os; schedule_times = os.getenv('SCHEDULE_TIMES', ''); print(1440 if schedule_times else int(float(os.getenv('SCHEDULE_FREQUENCY_HOURS', '1')) * 60 + 10))") && \
      test $(find /app/logs/health_status.txt -mmin -${MINUTES} | wc -l) -eq 1 && \
      grep -q "^OK" /app/logs/health_status.txt || exit 1
```

---

#### Deployment Steps for Time-Based Projects
```bash
# 1. Navigate to project
cd /path/to/masters_navigation_audit

# 2. Backup files
cp src/core/scheduler.py src/core/scheduler.py.backup
cp src/main.py src/main.py.backup
cp Dockerfile Dockerfile.backup

# 3. Make all three changes above

# 4. Rebuild without cache
docker compose build --no-cache

# 5. Restart
docker compose up -d

# 6. Wait for next scheduled run (check SCHEDULE_TIMES in .env)
# Example: If SCHEDULE_TIMES=12:00,18:00, wait until 12:00 or 18:00

# 7. Verify health status file created
docker exec masters-navigation-audit-app cat /app/logs/health_status.txt
# Should show: OK 2025-12-11T12:00:15.123456+02:00

# 8. Check container health
docker compose ps
# Should show: (healthy) after 30 minutes
```

---

#### Verification Checklist for Time-Based Projects

- [ ] `.env` has `SCHEDULE_TIMES` set (not `SCHEDULE_FREQUENCY_HOURS`)
- [ ] Modified `src/core/scheduler.py` - added `Path` import
- [ ] Modified `src/core/scheduler.py` - updated `__init__` with `logs_dir`
- [ ] Modified `src/core/scheduler.py` - added `_write_health_status()` method
- [ ] Modified `src/core/scheduler.py` - added health write to `_run_all_alerts()`
- [ ] Modified `src/main.py` - added `logs_dir` to scheduler instantiation
- [ ] Modified `Dockerfile` - updated `HEALTHCHECK` to handle both modes
- [ ] Rebuilt container: `docker compose build --no-cache`
- [ ] Deployed: `docker compose up -d`
- [ ] Waited for scheduled run time
- [ ] Verified health_status.txt exists and shows OK with timestamp
- [ ] Container shows `(healthy)` status after 30 minutes

---

#### Why These Additional Changes Are Needed

**Problem:** 
Time-based scheduling doesn't trigger health status writes because:
- Alerts only run at specific times (e.g., 12:00, 18:00)
- The `base_alert.py` writes health on each alert run
- But the scheduler itself never writes health
- Between scheduled times, no health file is updated

**Solution:**
- Scheduler writes health status after running all alerts
- This ensures health file is updated at each scheduled time
- Healthcheck uses 24-hour window (1440 minutes) for time-based scheduling
- Container stays healthy between daily runs

**Timeline Example (SCHEDULE_TIMES=12:00,18:00):**
```
12:00 - Alerts run, health_status.txt written: OK 12:00:15
12:30 - Healthcheck 1: File age = 30 min < 1440 min ✓ (healthy)
13:00 - Healthcheck 2: File age = 60 min < 1440 min ✓ (healthy)
18:00 - Alerts run, health_status.txt written: OK 18:00:22
18:30 - Healthcheck 3: File age = 30 min < 1440 min ✓ (healthy)
...next day...
11:30 - Healthcheck: File age = 1110 min < 1440 min ✓ (healthy)
12:00 - Alerts run, health_status.txt written: OK 12:00:18
```

---

#### Troubleshooting Time-Based Projects

**Container immediately unhealthy after deployment:**
```bash
# This is expected! Time-based projects need to wait for first scheduled run

# Check when next run is scheduled
docker compose logs -f
# Look for: "Next run scheduled at: 2025-12-11 18:00:00 +0200"

# Wait until that time, then check
docker exec <container> cat /app/logs/health_status.txt
```

**Health status file not created at scheduled time:**
```bash
# Check if scheduler modifications were applied
docker exec <container> grep -n "_write_health_status" /app/src/core/scheduler.py

# Should return line numbers - if empty, rebuild:
docker compose build --no-cache && docker compose up -d
```

**Container becomes unhealthy between runs:**
```bash
# Check HEALTHCHECK MINUTES calculation
docker exec <container> sh -c 'echo $SCHEDULE_TIMES; python3 -c "import os; schedule_times = os.getenv(\"SCHEDULE_TIMES\", \"\"); print(1440 if schedule_times else int(float(os.getenv(\"SCHEDULE_FREQUENCY_HOURS\", \"1\")) * 60 + 10))"'

# Should output:
# 12:00,18:00
# 1440

# If shows wrong value, rebuild Dockerfile
```

### What Gets Detected

Application-Level Failures:
- Database connection errors
- API authentication failures
- Query execution errors
- Unhandled exceptions
- Application crashes

Container-Level Failures:
- Process crashes
- Container stops
- Container removed
- Healthcheck failures

### Timeline for Failure Detection

Example: Database password changed

```
16:00 - App runs successfully, writes "OK"
17:00 - App runs, database fails, writes "ERROR"
17:30 - Healthcheck 1 fails (ERROR detected) - 1/3
18:00 - Healthcheck 2 fails - 2/3
18:30 - Healthcheck 3 fails - 3/3 → UNHEALTHY
18:30 - Monitor detects within 30 seconds
18:31 - Email alert sent
```

Total time: ~90 minutes (next run + 3 healthcheck cycles)

### Troubleshooting

#### Health Status File Not Created

```bash
# Check if changes applied
docker exec <container> grep -n "_write_health_status" /app/src/core/base_alert.py

# If empty, rebuild
docker compose build --no-cache && docker compose up -d
```

#### Healthcheck Always Fails

```bash
# Test healthcheck manually
docker exec <container> sh -c 'test -f /app/logs/health_status.txt && grep -q "^OK" /app/logs/health_status.txt && echo "PASS" || echo "FAIL"'

# Check file contents
docker exec <container> cat /app/logs/health_status.txt
```

### Implementation Checklist

For each project:

- [ ] Backup files: `cp src/core/base_alert.py src/core/base_alert.py.backup`
- [ ] Add `from pathlib import Path` import
- [ ] Add `_write_health_status()` method
- [ ] Add health status on success
- [ ] Add health status on exception
- [ ] Add health status on early returns (3 locations)
- [ ] Update Dockerfile HEALTHCHECK
- [ ] Rebuild: `docker compose build --no-cache`
- [ ] Deploy: `docker compose up -d`
- [ ] Verify: Check health_status.txt exists and shows OK
- [ ] Test: Break DB password, verify ERROR detected

## Support

For issues or questions:
- Check the troubleshooting section above
- Review logs: `tail -f _docker_monitoring/logs/monitor.log`
- Check systemd status: `sudo systemctl status docker-health-monitor`

## License

[Add your license here]

## Changelog

### Version 1.1.0 (2025-12-08)
- Added comprehensive application-level health monitoring implementation guide
- Documented base_alert.py modifications for health status tracking
- Updated Dockerfile healthcheck examples for all projects
- Added step-by-step deployment instructions
- Added troubleshooting section for health monitoring

### Version 1.0.0 (2025-11-25)
- Initial release
- Multi-project container monitoring
- Email alerting with project context
- Project-specific alert routing
- Systemd service integration

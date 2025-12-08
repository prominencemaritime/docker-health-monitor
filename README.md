# Multi-Project Docker Health Monitor

A centralised docker container health monitoring system, with healthchecks across multiple projects. An email alert is sent when containers become unhealthy.

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
│   │   ├── monitor.log              # Application logs
│   │   └── monitor_error.log        # Error logs
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
# or
nano .env
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
sudo nano /etc/systemd/system/docker-health-monitor.service
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
StandardOutput=append:/path/to/master_folder/_docker_monitoring/logs/monitor.log
StandardError=append:/path/to/master_folder/_docker_monitoring/logs/monitor_error.log

# Security settings
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

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

```bash
# View real-time logs
tail -f _docker_monitoring/logs/monitor.log

# View systemd journal logs
sudo journalctl -u docker-health-monitor -f

# View last 100 lines
sudo journalctl -u docker-health-monitor -n 100

# View logs since a specific time
sudo journalctl -u docker-health-monitor --since "1 hour ago"
```

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

2. **Healthcheck Detection**: Only monitors containers that have healthchecks configured in their docker-compose.yml:
   ```yaml
   healthcheck:
     test: ["CMD", "pgrep", "-f", "python"]
     interval: 30s
     timeout: 10s
     retries: 3
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
Subject: 🚨 CRITICAL: [passage-plan] passage-plan-app - Health Status Changed

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

# View recent logs
sudo journalctl -u docker-health-monitor -n 50

# Check for Python errors
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
   tail -f _docker_monitoring/logs/monitor.log
   ```

### Containers Not Being Monitored

The monitor only watches containers with healthchecks. Ensure your docker-compose.yml includes:

```yaml
services:
  your-app:
    # ... other config ...
    healthcheck:
      test: ["CMD", "pgrep", "-f", "python"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
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

Logs are automatically managed by systemd. To configure rotation:

```bash
sudo nano /etc/systemd/journald.conf

# Set:
SystemMaxUse=500M
SystemMaxFileSize=50M
MaxRetentionSec=2week
```

### Backup Configuration

```bash
# Backup configuration
cp _docker_monitoring/.env _docker_monitoring/.env.backup

# Backup with timestamp
cp _docker_monitoring/.env _docker_monitoring/.env.$(date +%Y%m%d)
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

## Support

For issues or questions:
- Check the troubleshooting section above
- Review logs: `tail -f _docker_monitoring/logs/monitor.log`
- Check systemd status: `sudo systemctl status docker-health-monitor`


## Changelog

### Version 1.0.0 (2025-12-08)
- Initial release
- Multi-project container monitoring
- Email alerting with project context
- Project-specific alert routing
- Systemd service integration


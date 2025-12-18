#!/usr/bin/env python3
"""
Multi-Project Docker Health Monitor

Monitors all Docker containers across multiple projects with healthchecks
and sends email alerts with project context when containers become unhealthy.

Features:
- Monitors all containers with healthchecks automatically
- Project-aware alerts (includes project context)
- Project-specific alert routing (optional)
- Tracks container state across all projects
- Includes container logs in alert emails
- Configurable check interval
- Graceful shutdown handling
- Efficient concurrent health checking with two-phase retry pattern

Usage:
    python docker_health_monitor.py
    
Directory Structure:
    /master_folder/
    ├── _docker_monitoring/          # Run the script from here
    │   ├── docker_health_monitor.py
    │   ├── .env
    │   └── logs/
    ├── passage_plan/                # Project 1
    │   └── docker-compose.yml
    ├── vessel_certificates/         # Project 2
    │   └── docker-compose.yml
    └── hot_works_alerts/            # Project 3
        └── docker-compose.yml

Requirements:
    - docker>=7.0.0
    - python-decouple
"""

import docker
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import signal
import sys
from typing import Dict, Optional, List, Tuple
from decouple import config
import logging
from logging.handlers import RotatingFileHandler
import re
import os
from pathlib import Path


# Use script directory for logs (both locally and on remote ubuntu)
# Configure logging with rotation
script_dir = Path(__file__).parent
log_dir = script_dir / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir  / 'monitor.log'
#log_file = '/srv/repos/_docker_monitoring/logs/monitor.log' <- old

file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10_485_760,  # 10MB
    backupCount=5          # Keep 5 old files
)
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger(__name__)


class ContainerHealthCheck:
    """Represents a single container health check result."""
    
    def __init__(
        self, 
        container_name: str, 
        project_name: str, 
        status: Optional[str],
        previous_status: Optional[str] = None
    ):
        self.container_name = container_name
        self.project_name = project_name
        self.status = status
        self.previous_status = previous_status
        self.timestamp = datetime.now()
    
    @property
    def status_changed(self) -> bool:
        """Check if status changed from previous check."""
        return self.status != self.previous_status
    
    @property
    def became_unhealthy(self) -> bool:
        """Check if container transitioned to unhealthy state."""
        return (
            self.status_changed and 
            self.status in ['unhealthy', 'starting'] and
            self.previous_status in ['healthy', 'unknown', None]
        )
    
    @property
    def became_healthy(self) -> bool:
        """Check if container recovered to healthy state."""
        return (
            self.status_changed and 
            self.status == 'healthy' and
            self.previous_status in ['unhealthy', 'starting']
        )


class MultiProjectHealthMonitor:
    """Monitor Docker container health across multiple projects."""
    
    def __init__(self):
        """Initialize the health monitor."""
        self.client = docker.from_env()
        self.container_states: Dict[str, Dict] = {}  # container_name -> {status, project, last_check}
        self.shutdown_requested = False
        
        # Load configuration
        self.smtp_host = config('SMTP_HOST')
        self.smtp_port = int(config('SMTP_PORT', default=465))
        self.smtp_user = config('SMTP_USER')
        self.smtp_pass = config('SMTP_PASS')
        
        # Thread pool for concurrent operations
        self.executor = ThreadPoolExecutor(max_workers=30)

        # Default alert recipients
        self.default_recipients = [
            email.strip() 
            for email in config('HEALTH_CHECK_ALERT_EMAILS', default='').split(',')
            if email.strip()
        ]
        
        # Project-specific routing (optional)
        self.project_routing = self._load_project_routing()
        
        self.check_interval_sec = int(config('HEALTH_CHECK_INTERVAL_SEC', default=30))
        self.wait_and_check_again_min = float(config('WAIT_AND_CHECK_AGAIN_MIN', default=15))
        self.log_tail_lines = int(config('HEALTH_CHECK_LOG_LINES', default=10))
        self.server_name = config('SERVER_NAME', default='Production')
        
        # Validate configuration
        if not self.default_recipients:
            raise ValueError("HEALTH_CHECK_ALERT_EMAILS must be configured in .env")
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info("=" * 70)
        logger.info("Multi-Project Docker Health Monitor initialized")
        logger.info(f"Server: {self.server_name}")
        logger.info(f"Default alert recipients: {', '.join(self.default_recipients)}")
        logger.info(f"Check interval: {self.check_interval_sec} seconds")
        logger.info(f"Retry delay: {self.wait_and_check_again_min} minutes")
        if self.project_routing:
            logger.info(f"Project-specific routing configured for: {', '.join(self.project_routing.keys())}")
        logger.info("=" * 70)
    
    def _load_project_routing(self) -> Dict[str, List[str]]:
        """
        Load project-specific alert routing from environment.
        
        Format in .env:
        CONTAINER_ALERT_ROUTING=passage-plan:email1@ex.com,email2@ex.com;vessel-cert:email3@ex.com
        
        Returns:
            Dict mapping container name patterns to recipient lists
        """
        routing_str = config('CONTAINER_ALERT_ROUTING', default='')
        if not routing_str:
            return {}
        
        routing = {}
        for mapping in routing_str.split(';'):
            if ':' not in mapping:
                continue
            pattern, emails = mapping.split(':', 1)
            recipients = [e.strip() for e in emails.split(',') if e.strip()]
            if recipients:
                routing[pattern.strip()] = recipients
        
        return routing
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}. Shutting down gracefully...")
        self.shutdown_requested = True
    
    def _get_project_name(self, container) -> str:
        """
        Extract project name from container labels or name.
        
        Args:
            container: Docker container object
            
        Returns:
            Project name string
        """
        labels = container.labels
        
        # Check common docker-compose labels
        if 'com.docker.compose.project' in labels:
            return labels['com.docker.compose.project']
        
        # Fallback: extract from container name
        # Docker compose typically names containers: projectname-servicename-1
        container_name = container.name
        match = re.match(r'^([^-]+)-', container_name)
        if match:
            return match.group(1)
        
        return 'unknown'
    
    def _get_recipients_for_container(self, container_name: str, project_name: str) -> List[str]:
        """
        Get recipient list for a specific container.
        
        Checks project-specific routing first, then falls back to default.
        
        Args:
            container_name: Name of the container
            project_name: Project/compose name
            
        Returns:
            List of email addresses to notify
        """
        # Check if there's project-specific routing
        for pattern, recipients in self.project_routing.items():
            if pattern in container_name or pattern in project_name:
                logger.debug(f"Using project-specific routing for {container_name}: {recipients}")
                return recipients
        
        # Fall back to default recipients
        return self.default_recipients
    
    def get_container_health(self, container) -> Optional[str]:
        """
        Get health status of a container.
        
        Args:
            container: Docker container object
            
        Returns:
            Health status string or None if no healthcheck
        """
        try:
            container.reload()  # Refresh container state
            health = container.attrs.get('State', {}).get('Health', {})
            return health.get('Status')
        except docker.errors.NotFound:
            return 'not_found'
        except Exception as e:
            logger.error(f"Error getting health for {container.name}: {e}")
            return None
    
    def get_container_logs(self, container_name: str, tail: int = 50) -> str:
        """
        Get recent logs from a container by name.
        
        Args:
            container_name: Name of the container
            tail: Number of lines to retrieve
            
        Returns:
            Container logs as string
        """
        try:
            container = self.client.containers.get(container_name)
            logs = container.logs(tail=tail).decode('utf-8', errors='replace')
            return logs
        except docker.errors.NotFound:
            return "Container not found - may have been removed"
        except Exception as e:
            return f"Could not retrieve logs: {e}"
    
    def send_alert_email(
        self, 
        container_name: str,
        project_name: str,
        status: str, 
        details: str,
        previous_status: Optional[str] = None,
        recipients: Optional[List[str]] = None
    ):
        """
        Send email alert for health check status change.
        
        Args:
            container_name: Name of the container
            project_name: Project/compose name
            status: Current health status
            details: Additional details (logs, error messages)
            previous_status: Previous health status
            recipients: Override recipient list
        """
        if recipients is None:
            recipients = self._get_recipients_for_container(container_name, project_name)
        
        # Determine alert severity
        if status == 'unhealthy':
            emoji = '!?'
            severity = 'CRITICAL'
        elif status == 'not_found':
            emoji = '!?'
            severity = 'ERROR'
        elif status == 'starting':
            emoji = '!?'
            severity = 'WARNING'
        else:
            emoji = '[OK]'
            severity = 'INFO'
        
        subject = f"{emoji} {severity}: [{project_name}] {container_name} - Health Status Changed"
        
        # Build email body
        status_change = f"{previous_status} → {status}" if previous_status else status
        
        body = f"""
Docker Container Health Alert
==============================

Server:          {self.server_name}
Project:         {project_name}
Container:       {container_name}
Status Change:   {status_change}
Severity:        {severity}
Time:            {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Details:
--------
{details}

Action Required:
----------------
"""
        
        if status == 'unhealthy':
            body += f"""
1. Check container logs:
   docker logs {container_name}

2. Inspect container:
   docker inspect {container_name}

3. Restart container:
   docker restart {container_name}
   
   Or navigate to project and restart:
   cd /path/to/{project_name}
   docker compose restart

4. Check application health endpoint

5. Review recent code changes or deployments
"""
        elif status == 'not_found':
            body += f"""
1. Check if container is running:
   docker ps -a | grep {container_name}

2. Navigate to project directory:
   cd /path/to/{project_name}

3. Check docker-compose status:
   docker compose ps

4. Restart services:
   docker compose up -d

5. Check docker-compose.yml configuration
"""
        else:
            body += """
Monitor the situation and check logs for more information.
"""
        
        body += f"""

Project Context:
----------------
Container name: {container_name}
Project name:   {project_name}
Status:         {status}

---
Automated alert from Multi-Project Docker Health Monitor
Server: {self.server_name}
Monitoring all containers with healthchecks
"""
        
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = self.smtp_user
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        try:
            if self.smtp_port == 587:
                # Use STARTTLS for port 587
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_pass)
                    server.send_message(msg)
            else:
                # Use SSL for port 465
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30) as server:
                    server.login(self.smtp_user, self.smtp_pass)
                    server.send_message(msg)
            logger.info(f"✓ Alert sent for [{project_name}] {container_name} to {', '.join(recipients)}")
        except Exception as e:
            logger.error(f"✗ Failed to send alert email: {e}")

    
    def check_single_container(self, container) -> ContainerHealthCheck:
        """
        Check health of a single container (thread-safe operation).
        
        Args:
            container: Docker container object
            
        Returns:
            ContainerHealthCheck object with results
        """
        container_name = container.name
        project_name = self._get_project_name(container)
        current_status = self.get_container_health(container)
        
        # Get previous state
        previous_state = self.container_states.get(container_name, {})
        previous_status = previous_state.get('status')
        
        return ContainerHealthCheck(
            container_name=container_name,
            project_name=project_name,
            status=current_status,
            previous_status=previous_status
        )
    
    def recheck_single_container(self, container_name: str, project_name: str) -> Tuple[str, Optional[str]]:
        """
        Recheck a single container's health (used in Phase 2).
        
        Args:
            container_name: Name of the container
            project_name: Project name
            
        Returns:
            Tuple of (container_name, current_status)
        """
        try:
            container = self.client.containers.get(container_name)
            status = self.get_container_health(container)
            return (container_name, status)
        except docker.errors.NotFound:
            return (container_name, 'not_found')
        except Exception as e:
            logger.error(f"Error rechecking {container_name}: {e}")
            return (container_name, None)
    
    def phase_one_check_all(self) -> Tuple[List[ContainerHealthCheck], List[ContainerHealthCheck]]:
        """
        Phase 1: Check all containers concurrently.
        
        Returns:
            Tuple of (needs_retry_list, immediate_alert_list)
        """
        logger.info("Phase 1: Checking all containers...")

        try:
            containers = self.client.containers.list()
            
            if not containers:
                logger.debug("No containers running")
                return ([], [])
            
            # Submit all health checks concurrently
            futures = {
                self.executor.submit(self.check_single_container, container): container 
                for container in containers
            }
            
            needs_retry = []
            immediate_alerts = []
            seen_containers = set()
            
            # Collect results as they complete
            for future in as_completed(futures):
                try:
                    health_check = future.result()
                    seen_containers.add(health_check.container_name)
                    
                    # Skip containers without healthchecks
                    if health_check.status is None:
                        continue
                    
                    # Update state
                    self.container_states[health_check.container_name] = {
                        'status': health_check.status,
                        'project': health_check.project_name,
                        'last_check': health_check.timestamp
                    }
                    
                    # Handle status changes
                    if health_check.status_changed:
                        logger.info(
                            f"[{health_check.project_name}] {health_check.container_name}: "
                            f"{health_check.previous_status or 'unknown'} → {health_check.status}"
                        )
                        
                        if health_check.became_unhealthy:
                            # Queue for retry
                            needs_retry.append(health_check)
                        
                        elif health_check.became_healthy:
                            # Immediate alert for recovery
                            immediate_alerts.append(health_check)
                
                except Exception as e:
                    container = futures[future]
                    logger.error(f"Error processing health check for {container.name}: {e}")
            
            # Check for disappeared containers
            for container_name, state in list(self.container_states.items()):
                if container_name not in seen_containers:
                    previous_status = state['status']
                    project_name = state['project']
                    
                    logger.warning(f"[{project_name}] {container_name}: Container no longer running")
                    
                    self.send_alert_email(
                        container_name=container_name,
                        project_name=project_name,
                        status='not_found',
                        details='Container is no longer running or has been removed.',
                        previous_status=previous_status
                    )
                    
                    # Remove from tracking
                    del self.container_states[container_name]
            
            logger.info(f"Phase 1: Complete. Found {len(needs_retry)} unhealthy, {len(immediate_alerts)} recovered")
            return (needs_retry, immediate_alerts)
        
        except Exception as e:
            logger.error(f"Error in Phase 1 health checks: {e}")
            return ([], [])
    
    def phase_two_recheck_unhealthy(self, needs_retry: List[ContainerHealthCheck]):
        """
        Phase 2: Recheck containers that became unhealthy after waiting.
        
        Args:
            needs_retry: List of ContainerHealthCheck objects to recheck
        """
        if not needs_retry:
            return
        
        logger.info(
            f"Phase 2: Rechecking {len(needs_retry)} container(s) after "
            f"{self.wait_and_check_again_min} minute(s)..."
        )
        
        # Interruptible sleep with logging
        sleep_seconds = int(self.wait_and_check_again_min * 60)
        start_time = time.time()
        end_time = start_time + sleep_seconds
        
        logger.info(f"Sleeping for {sleep_seconds} seconds before Phase 2 recheck...")
        
        while time.time() < end_time and not self.shutdown_requested:
            remaining = int(end_time - time.time())
            if remaining > 0:
                # Sleep in 1-second intervals to allow for shutdown
                time.sleep(min(1, remaining))
            else:
                break
        
        if self.shutdown_requested:
            logger.info("Phase 2 sleep interrupted by shutdown request")
            return
        
        logger.info("Sleep complete, starting Phase 2 recheck...")
        
        # Submit all rechecks concurrently
        futures = {
            self.executor.submit(
                self.recheck_single_container, 
                health_check.container_name,
                health_check.project_name
            ): health_check
            for health_check in needs_retry
        }
        
        # Process recheck results
        for future in as_completed(futures):
            original_check = futures[future]
            try:
                container_name, current_status = future.result()
                
                if current_status == 'healthy':
                    logger.info(
                        f"[{original_check.project_name}] {container_name}: "
                        f"Recovered during retry wait; no alert sent"
                    )
                    # Update state
                    self.container_states[container_name]['status'] = 'healthy'
                    continue
                
                # Still unhealthy - send alert with logs
                logs = self.get_container_logs(container_name, tail=self.log_tail_lines)
                
                if current_status == 'not_found':
                    details = 'Container disappeared during retry wait period.'
                else:
                    details = f"Container remained {current_status} after {self.wait_and_check_again_min} minute{'s' if self.wait_and_check_again_min > 1.0 else ''}.\n\nRecent logs:\n\n{logs}"
                
                self.send_alert_email(
                    container_name=container_name,
                    project_name=original_check.project_name,
                    status=current_status or 'unknown',
                    details=details,
                    previous_status=original_check.previous_status
                )
                
                # Update state
                if current_status:
                    self.container_states[container_name]['status'] = current_status
                
            except Exception as e:
                logger.error(
                    f"Error rechecking {original_check.container_name}: {e}"
                )
    
    def handle_immediate_alerts(self, immediate_alerts: List[ContainerHealthCheck]):
        """
        Send immediate alerts for containers that recovered.
        
        Args:
            immediate_alerts: List of ContainerHealthCheck objects
        """
        for health_check in immediate_alerts:
            details = f"Container recovered to healthy status."
            
            self.send_alert_email(
                container_name=health_check.container_name,
                project_name=health_check.project_name,
                status=health_check.status,
                details=details,
                previous_status=health_check.previous_status
            )
    
    def check_all_containers(self):
        """
        Main health check orchestration using two-phase pattern.
        
        Phase 1: Check all containers, identify those needing retry
        Phase 2: Wait and recheck unhealthy containers before alerting
        """
        # Phase 1: Initial concurrent health checks
        needs_retry, immediate_alerts = self.phase_one_check_all()
        
        # Handle immediate alerts (recoveries)
        if immediate_alerts:
            self.handle_immediate_alerts(immediate_alerts)
        
        # Phase 2: Wait and recheck unhealthy containers
        if needs_retry and not self.shutdown_requested:
            self.phase_two_recheck_unhealthy(needs_retry)
    
    def run(self):
        """Run the health monitoring loop."""
        logger.info("=" * 70)
        logger.info("▶ MULTI-PROJECT DOCKER HEALTH MONITOR STARTED")
        logger.info("=" * 70)
        
        try:
            # Initial check
            self.check_all_containers()
            
            # Main monitoring loop
            while not self.shutdown_requested:
                time.sleep(self.check_interval_sec)
                
                if self.shutdown_requested:
                    break
                
                self.check_all_containers()
        
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        
        except Exception as e:
            logger.exception(f"Fatal error in monitoring loop: {e}")
        
        finally:
            # Shutdown executor gracefully
            logger.info("Shutting down thread pool...")
            self.executor.shutdown(wait=True, cancel_futures=True)
            
            logger.info("=" * 70)
            logger.info("◼ MULTI-PROJECT DOCKER HEALTH MONITOR STOPPED")
            logger.info("=" * 70)


def main():
    """Main entry point."""
    try:
        monitor = MultiProjectHealthMonitor()
        monitor.run()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Failed to start health monitor: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

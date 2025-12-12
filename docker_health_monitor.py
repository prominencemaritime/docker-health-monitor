#!/usr/bin/env python3
"""
Multi-Project Docker Health Monitor (polished)

- Non-blocking delayed retry: when a container is unhealthy, a background
  retry task waits the configured interval and re-checks. Only if still
  unhealthy an alert is sent.
- Uses ThreadPoolExecutor (no external queue needed).
- Thread-safe state and retry scheduling (locks).
- Prevents duplicate parallel retries for the same container.
- Optional exponential backoff + jitter.
- Graceful shutdown handling.
- Configurable via .env (uses python-decouple).

Drop into your monitoring folder and run with the same .env keys you had.
"""

from __future__ import annotations
import docker
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
import time
import signal
import sys
from typing import Dict, Optional, List, Callable
from decouple import config
import logging
from logging.handlers import RotatingFileHandler
import re
import threading
import random

# ---------- Logging setup ----------
LOG_FILE = config('MONITOR_LOG_FILE', default='/srv/repos/_docker_monitoring/logs/monitor.log')

file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=int(config('MONITOR_LOG_MAX_BYTES', default=10_485_760)),  # 10MB
    backupCount=int(config('MONITOR_LOG_BACKUP_COUNT', default=5))
)
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
logger = logging.getLogger(__name__)


# ---------- Monitor class ----------
class MultiProjectHealthMonitor:
    def __init__(self):
        # Docker client
        self.client = docker.from_env()

        # Shared state
        self.container_states: Dict[str, Dict] = {}  # name -> {status, project, last_check, retry_scheduled_until?}
        self.container_states_lock = threading.RLock()

        # Track scheduled retry futures to avoid duplicates
        self.retry_futures: Dict[str, Future] = {}
        self.retry_futures_lock = threading.RLock()

        # Shutdown flag
        self.shutdown_requested = threading.Event()

        # Load configuration (from .env via decouple)
        self.smtp_host = config('SMTP_HOST')
        self.smtp_port = int(config('SMTP_PORT', default=465))
        self.smtp_user = config('SMTP_USER')
        self.smtp_pass = config('SMTP_PASS')

        self.default_recipients = [
            e.strip() for e in config('HEALTH_CHECK_ALERT_EMAILS', default='').split(',') if e.strip()
        ]
        if not self.default_recipients:
            raise ValueError("HEALTH_CHECK_ALERT_EMAILS must be configured in .env")

        # Project-specific routing
        self.project_routing = self._load_project_routing()

        # Timing & executor
        self.check_interval_sec = int(config('HEALTH_CHECK_INTERVAL_SEC', default=30))
        # wait in minutes before re-check; can be float
        self.wait_and_check_again_min = float(config('WAIT_AND_CHECK_AGAIN_MIN', default=5))
        self.max_workers = int(config('MONITOR_MAX_WORKERS', default=30))
        self.log_tail_lines = int(config('HEALTH_CHECK_LOG_LINES', default=50))
        self.server_name = config('SERVER_NAME', default='Production')

        # Backoff config (optional)
        self.use_backoff = config('HEALTH_USE_BACKOFF', default='false').lower() in ('1', 'true', 'yes')
        self.backoff_multiplier = float(config('HEALTH_BACKOFF_MULTIPLIER', default=2.0))
        self.backoff_max_min = float(config('HEALTH_BACKOFF_MAX_MIN', default=60.0))
        self.retry_jitter_seconds = float(config('HEALTH_RETRY_JITTER_SEC', default=5.0))

        # Executor for background tasks
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

        # Register signals
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Log startup info
        logger.info("=" * 70)
        logger.info("Multi-Project Docker Health Monitor initialized")
        logger.info(f"Server: {self.server_name}")
        logger.info(f"Default alert recipients: {', '.join(self.default_recipients)}")
        logger.info(f"Check interval: {self.check_interval_sec} seconds")
        logger.info(f"Retry wait (base): {self.wait_and_check_again_min} minutes")
        if self.project_routing:
            logger.info(f"Project-specific routing configured for: {', '.join(self.project_routing.keys())}")
        logger.info(f"Executor workers: {self.max_workers}")
        logger.info("=" * 70)

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}. Requesting graceful shutdown...")
        self.shutdown_requested.set()

    def _load_project_routing(self) -> Dict[str, List[str]]:
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

    # ---------------- Email ----------------
    def _get_recipients_for_container(self, container_name: str, project_name: str) -> List[str]:
        for pattern, recipients in self.project_routing.items():
            if pattern in container_name or pattern in project_name:
                logger.debug(f"Using project-specific routing for {container_name}: {recipients}")
                return recipients
        return self.default_recipients

    def send_alert_email(
        self,
        container_name: str,
        project_name: str,
        status: str,
        details: str,
        previous_status: Optional[str] = None,
        recipients: Optional[List[str]] = None
    ):
        if recipients is None:
            recipients = self._get_recipients_for_container(container_name, project_name)

        if status == 'unhealthy':
            severity = 'CRITICAL'
            emoji = '🔥'
        elif status == 'not_found':
            severity = 'ERROR'
            emoji = '⚠️'
        elif status == 'starting':
            severity = 'WARNING'
            emoji = '🔁'
        else:
            severity = 'INFO'
            emoji = 'ℹ️'

        subject = f"{emoji} {severity}: [{project_name}] {container_name} - {status}"

        status_change = f"{previous_status} → {status}" if previous_status else status
        body = (
            f"Docker Container Health Alert\n"
            f"=============================\n\n"
            f"Server:          {self.server_name}\n"
            f"Project:         {project_name}\n"
            f"Container:       {container_name}\n"
            f"Status Change:   {status_change}\n"
            f"Severity:        {severity}\n"
            f"Time:            {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Details:\n{details}\n\n"
        )

        if status == 'unhealthy':
            body += (
                "Action Required:\n"
                "1. Check container logs:\n"
                f"   docker logs {container_name}\n\n"
                "2. Inspect container:\n"
                f"   docker inspect {container_name}\n\n"
                "3. Restart container:\n"
                f"   docker restart {container_name}\n\n"
            )

        body += f"\nProject Context:\nContainer name: {container_name}\nProject name:   {project_name}\nStatus:         {status}\n\n---\nAutomated alert from Multi-Project Docker Health Monitor\n"

        msg = MIMEMultipart()
        msg['From'] = self.smtp_user
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        try:
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=20) as server:
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
            logger.info(f"Alert sent for [{project_name}] {container_name} -> {', '.join(recipients)}")
        except Exception as exc:
            logger.exception(f"Failed to send alert email for {container_name}: {exc}")

    # ---------------- Docker helpers ----------------
    def _get_project_name(self, container) -> str:
        labels = getattr(container, 'labels', {}) or container.attrs.get('Config', {}).get('Labels', {}) or {}
        if 'com.docker.compose.project' in labels:
            return labels['com.docker.compose.project']
        # fallback to name parsing like project-service-1
        match = re.match(r'^([^-]+)-', container.name)
        if match:
            return match.group(1)
        return 'unknown'

    def get_container_health(self, container) -> Optional[str]:
        try:
            container.reload()
            health = container.attrs.get('State', {}).get('Health', {})
            return health.get('Status')
        except Exception as e:
            logger.debug(f"Error reading health for {getattr(container, 'name', '<unknown>')}: {e}")
            return None

    def get_container_logs(self, container, tail: int = 50) -> str:
        try:
            raw = container.logs(tail=tail)
            if isinstance(raw, bytes):
                return raw.decode('utf-8', errors='replace')
            return str(raw)
        except Exception as e:
            return f"Could not retrieve logs: {e}"

    # ---------------- Retry logic (background task) ----------------
    def _compute_backoff_seconds(self, attempt: int) -> float:
        """
        attempt: 1-based attempt count. For first retry attempt=1 uses base wait.
        Returns seconds to sleep including jitter.
        """
        base_sec = self.wait_and_check_again_min * 60.0
        if not self.use_backoff or attempt <= 1:
            wait = base_sec
        else:
            wait_min = min(self.wait_and_check_again_min * (self.backoff_multiplier ** (attempt - 1)), self.backoff_max_min)
            wait = wait_min * 60.0
        jitter = random.uniform(0, self.retry_jitter_seconds)
        return wait + jitter

    def schedule_retry(self, container_name: str, project_name: str, previous_status: Optional[str], attempt: int = 1):
        """
        Schedule an asynchronous retry for a given container.
        Will skip scheduling if there's already a pending retry for that container.
        """
        with self.retry_futures_lock:
            if container_name in self.retry_futures:
                logger.debug(f"Retry already scheduled for {container_name}; skipping duplicate scheduling.")
                return

            future = self.executor.submit(self._retry_task, container_name, project_name, previous_status, attempt)
            self.retry_futures[container_name] = future

            # attach a done callback to clean up entry
            def _on_done(fut: Future, name=container_name):
                with self.retry_futures_lock:
                    self.retry_futures.pop(name, None)
            future.add_done_callback(_on_done)

    def _retry_task(self, container_name: str, project_name: str, previous_status: Optional[str], attempt: int):
        """
        Background task:
          1) Sleep for backoff seconds
          2) Re-check container health
          3) Send alert only if still unhealthy/not found
        """
        wait_seconds = self._compute_backoff_seconds(attempt)
        logger.info(f"[{project_name}] {container_name}: scheduling retry (attempt {attempt}) in {wait_seconds:.1f}s")
        # Sleep but wake early if shutdown requested
        deadline = time.time() + wait_seconds
        while not self.shutdown_requested.is_set() and time.time() < deadline:
            time.sleep(min(1.0, deadline - time.time()))

        if self.shutdown_requested.is_set():
            logger.info(f"[{project_name}] {container_name}: retry cancelled due to shutdown.")
            return

        # After wait, attempt to get container and check health
        try:
            container = self.client.containers.get(container_name)
        except docker.errors.NotFound:
            logger.warning(f"[{project_name}] {container_name}: container not found during retry; sending not_found alert")
            self.send_alert_email(
                container_name=container_name,
                project_name=project_name,
                status='not_found',
                details='Container disappeared during retry wait period.',
                previous_status=previous_status
            )
            return
        except Exception as e:
            logger.exception(f"Error retrieving container {container_name} during retry: {e}")
            # Optionally schedule another retry with incremented attempt if desired
            return

        status = self.get_container_health(container)
        if status is None:
            # No healthcheck defined; do nothing
            logger.debug(f"[{project_name}] {container_name}: no healthcheck available on retry.")
            return

        if status == 'healthy':
            logger.info(f"[{project_name}] {container_name}: recovered during retry; no alert sent.")
            # Update state
            with self.container_states_lock:
                self.container_states[container_name] = {
                    'status': status,
                    'project': project_name,
                    'last_check': datetime.now()
                }
            return

        # Still unhealthy - gather logs and send alert
        logs = self.get_container_logs(container, tail=self.log_tail_lines)
        details = f"Recent logs (last {self.log_tail_lines} lines):\n\n{logs}"
        logger.info(f"[{project_name}] {container_name}: still {status} after retry -> sending alert")
        self.send_alert_email(
            container_name=container_name,
            project_name=project_name,
            status=status,
            details=details,
            previous_status=previous_status
        )

        # Optionally: if you want additional retries (exponential), schedule again:
        if self.use_backoff and (attempt < int(config('HEALTH_MAX_ATTEMPTS', default=3))):
            # schedule another retry attempt with attempt+1
            self.schedule_retry(container_name, project_name, previous_status, attempt + 1)

    # ---------------- Per-container check (submitted to executor) ----------------
    def _check_container_task(self, container):
        """
        Perform a single container health check. Designed to run inside executor.
        """
        container_name = container.name
        project_name = self._get_project_name(container)
        try:
            current_status = self.get_container_health(container)
        except Exception as e:
            logger.exception(f"Error checking container {container_name}: {e}")
            return

        if current_status is None:
            # no healthcheck configured; ignore
            logger.debug(f"[{project_name}] {container_name}: no healthcheck; skipping")
            return

        with self.container_states_lock:
            previous_state = self.container_states.get(container_name, {})
            previous_status = previous_state.get('status')

        if current_status != previous_status:
            logger.info(f"[{project_name}] {container_name}: {previous_status or 'unknown'} → {current_status}")

            # Update tracked state immediately with last_check; do not mark retry scheduled here
            with self.container_states_lock:
                self.container_states[container_name] = {
                    'status': current_status,
                    'project': project_name,
                    'last_check': datetime.now()
                }

            if current_status != 'healthy':
                # Schedule an async retry if none pending
                self.schedule_retry(container_name, project_name, previous_status, attempt=1)
        else:
            # status unchanged - just update last_check
            with self.container_states_lock:
                self.container_states[container_name] = {
                    'status': current_status,
                    'project': project_name,
                    'last_check': datetime.now()
                }

    # ---------------- Main scanning loop ----------------
    def check_all_containers_once(self):
        """
        Snap a list of containers and submit per-container checks to the executor.
        """
        try:
            containers = self.client.containers.list()
        except Exception as e:
            logger.exception(f"Error listing containers: {e}")
            return

        seen = set()
        projects = {}

        futures = []
        for container in containers:
            seen.add(container.name)
            project = self._get_project_name(container)
            projects.setdefault(project, []).append(container.name)
            # submit a task per container; executor will constrain concurrency
            futures.append(self.executor.submit(self._check_container_task, container))

        # Optional: wait briefly for futures to start (not required). We won't block for their completion here.
        logger.debug(f"Submitted {len(futures)} container checks across {len(projects)} projects.")

        # Detect disappeared containers (those previously tracked but not in current list)
        with self.container_states_lock:
            for tracked_name, state in list(self.container_states.items()):
                if tracked_name not in seen:
                    prev_status = state.get('status')
                    project_name = state.get('project', 'unknown')
                    logger.warning(f"[{project_name}] {tracked_name}: Container no longer running")
                    # send not_found alert (do synchronously so we don't lose notification during shutdown)
                    self.send_alert_email(
                        container_name=tracked_name,
                        project_name=project_name,
                        status='not_found',
                        details='Container is no longer running or has been removed.',
                        previous_status=prev_status
                    )
                    # remove from tracked
                    self.container_states.pop(tracked_name, None)

    def run(self):
        logger.info("=" * 70)
        logger.info("▶ MULTI-PROJECT DOCKER HEALTH MONITOR STARTED")
        logger.info("=" * 70)
        try:
            # Initial pass
            self.check_all_containers_once()

            # Main loop
            while not self.shutdown_requested.is_set():
                # Sleep but wake early on shutdown
                deadline = time.time() + self.check_interval_sec
                while not self.shutdown_requested.is_set() and time.time() < deadline:
                    time.sleep(min(1.0, deadline - time.time()))
                if self.shutdown_requested.is_set():
                    break

                self.check_all_containers_once()

        except Exception as e:
            logger.exception(f"Fatal error in monitoring loop: {e}")

        finally:
            logger.info("Shutdown requested; waiting for background tasks to finish (graceful)...")
            # Prevent new tasks and wait for currently running tasks to complete
            self.executor.shutdown(wait=True)
            logger.info("=" * 70)
            logger.info("◼ MULTI-PROJECT DOCKER HEALTH MONITOR STOPPED")
            logger.info("=" * 70)


# ---------- CLI entry ----------
def main():
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


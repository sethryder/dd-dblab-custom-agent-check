"""
Datadog Agent Check for DBLab (Database Lab Engine)

Monitors:
  - Instance health (dblab.instance.health service check)
  - Data refresh status (dblab.refresh.health service check)
  - Synchronization status (dblab.sync.health service check)
  - Pool filesystem metrics (free, used, size, compression ratio)
  - Clone count
"""

import datetime

from datadog_checks.base import AgentCheck, ConfigurationError

STATUS_CODE_MAP = {
    "ok": AgentCheck.OK,
    "warning": AgentCheck.WARNING,
    "warn": AgentCheck.WARNING,
    "error": AgentCheck.CRITICAL,
    "err": AgentCheck.CRITICAL,
    "failed": AgentCheck.CRITICAL,
    "pending": AgentCheck.WARNING,
    "refreshing": AgentCheck.OK,
}


def _map_status(code):
    """Map a DBLab status code string to a Datadog service check status."""
    if code is None:
        return AgentCheck.UNKNOWN
    return STATUS_CODE_MAP.get(code.lower(), AgentCheck.UNKNOWN)


class DblabCheck(AgentCheck):
    __NAMESPACE__ = "dblab"

    def check(self, instance):
        url = instance.get("url", "").rstrip("/")
        token = instance.get("verification_token", "")
        tags = instance.get("tags", [])

        if not url:
            raise ConfigurationError("'url' is required in the DBLab check configuration")
        if not token:
            raise ConfigurationError("'verification_token' is required in the DBLab check configuration")

        tags = tags + self._probe_version(url)

        status_url = f"{url}/status"

        try:
            response = self.http.get(
                status_url,
                headers={"Verification-Token": token},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            self.service_check("instance.health", AgentCheck.CRITICAL, tags=tags, message=str(e))
            self.service_check("refresh.health", AgentCheck.UNKNOWN, tags=tags, message="Could not reach DBLab API")
            self.service_check("sync.health", AgentCheck.UNKNOWN, tags=tags, message="Could not reach DBLab API")
            raise

        self._check_instance_health(data, tags)
        self._check_refresh_status(data, tags)
        self._check_sync_status(data, tags)
        self._collect_pool_metrics(data, tags)
        self._collect_clone_metrics(data, tags)

    _VERSION_CACHE_TTL = datetime.timedelta(hours=24)

    def _probe_version(self, url):
        """Try /healthz (4.0+ only). Returns version/edition tags, or [] on 3.5.0.
        Result is cached for 24 hours so the endpoint is not hit every collection interval."""
        now = datetime.datetime.now(datetime.timezone.utc)
        if hasattr(self, "_version_tags_expiry") and now < self._version_tags_expiry:
            return self._version_tags
        try:
            response = self.http.get(f"{url}/healthz")
            response.raise_for_status()
            data = response.json()
            version_tags = []
            if data.get("version"):
                version_tags.append(f"dblab_version:{data['version']}")
            if data.get("edition"):
                version_tags.append(f"dblab_edition:{data['edition']}")
            self._version_tags = version_tags
        except Exception:
            self._version_tags = []
        self._version_tags_expiry = now + self._VERSION_CACHE_TTL
        return self._version_tags

    def _check_instance_health(self, data, tags):
        status = data.get("status", {})
        code = status.get("code")
        message = status.get("message", "")
        dd_status = _map_status(code)
        self.service_check("instance.health", dd_status, tags=tags, message=message)

    def _check_refresh_status(self, data, tags):
        retrieving = data.get("retrieving")
        if retrieving is None:
            self.service_check("refresh.health", AgentCheck.UNKNOWN, tags=tags, message="No retrieving data in response")
            return

        status_code = retrieving.get("status")
        dd_status = _map_status(status_code)
        message_parts = [f"status={status_code}"]

        last_refresh = retrieving.get("lastRefresh")
        if last_refresh:
            message_parts.append(f"lastRefresh={last_refresh}")
            try:
                last_refresh_dt = datetime.datetime.fromisoformat(last_refresh.replace("Z", "+00:00"))
                now = datetime.datetime.now(datetime.timezone.utc)
                age_seconds = (now - last_refresh_dt).total_seconds()
                self.gauge("refresh.age_seconds", age_seconds, tags=tags)
            except ValueError:
                pass

        next_refresh = retrieving.get("nextRefresh")
        if next_refresh:
            message_parts.append(f"nextRefresh={next_refresh}")

        self.service_check("refresh.health", dd_status, tags=tags, message=", ".join(message_parts))

        if dd_status == AgentCheck.CRITICAL:
            self.event(
                {
                    "event_type": "dblab.refresh.failed",
                    "msg_title": "DBLab data refresh failed",
                    "msg_text": ", ".join(message_parts),
                    "alert_type": "error",
                    "tags": tags,
                }
            )

    def _check_sync_status(self, data, tags):
        sync = data.get("synchronization")
        if sync is None:
            return

        status = sync.get("status", {})
        code = status.get("code") if isinstance(status, dict) else None
        message = status.get("message", "") if isinstance(status, dict) else ""

        dd_status = _map_status(code)
        self.service_check("sync.health", dd_status, tags=tags, message=message)

        replication_lag = sync.get("replicationLag")
        if replication_lag is not None:
            try:
                self.gauge("sync.replication_lag_seconds", float(replication_lag), tags=tags)
            except (TypeError, ValueError):
                pass

    def _collect_pool_metrics(self, data, tags):
        pools = data.get("pools", [])
        for pool in pools:
            pool_name = pool.get("name", "unknown")
            pool_tags = tags + [f"pool:{pool_name}", f"pool_mode:{pool.get('mode', 'unknown')}"]

            fs = pool.get("fileSystem", {})
            if fs:
                for field, metric in [
                    ("free", "pool.fs.free_bytes"),
                    ("size", "pool.fs.size_bytes"),
                    ("used", "pool.fs.used_bytes"),
                    ("dataSize", "pool.fs.data_size_bytes"),
                    ("usedBySnapshots", "pool.fs.used_by_snapshots_bytes"),
                    ("usedByClones", "pool.fs.used_by_clones_bytes"),
                ]:
                    val = fs.get(field)
                    if val is not None:
                        self.gauge(metric, val, tags=pool_tags)

                compress_ratio = fs.get("compressRatio")
                if compress_ratio is not None:
                    self.gauge("pool.fs.compress_ratio", compress_ratio, tags=pool_tags)

            clone_list = pool.get("cloneList", [])
            self.gauge("pool.clone_count", len(clone_list), tags=pool_tags)

            pool_status = pool.get("status")
            if pool_status:
                pool_dd_status = _map_status(pool_status)
                self.service_check("pool.health", pool_dd_status, tags=pool_tags)

    def _collect_clone_metrics(self, data, tags):
        cloning = data.get("cloning", {})
        if not cloning:
            return

        num_clones = cloning.get("numClones")
        if num_clones is not None:
            self.gauge("cloning.num_clones", num_clones, tags=tags)

        expected_time = cloning.get("expectedCloningTime")
        if expected_time is not None:
            self.gauge("cloning.expected_time_seconds", expected_time, tags=tags)

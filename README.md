# Datadog Agent Check for DBLab

A custom [Datadog Agent check](https://docs.datadoghq.com/extend/custom_checks/write_agent_check/) that monitors [DBLab Engine](https://postgres.ai/products/dblab_engine) (Database Lab Engine) instances.

Compatible with **DBLab 3.5.0** and **4.0+**.

## What it monitors

| What | Datadog name | Type |
|---|---|---|
| Overall instance health | `dblab.instance.health` | Service check |
| Data refresh health | `dblab.refresh.health` | Service check |
| Replication sync health | `dblab.sync.health` | Service check |
| Per-pool health | `dblab.pool.health` | Service check |
| Time since last data refresh | `dblab.refresh.age_seconds` | Gauge |
| Replication lag | `dblab.sync.replication_lag_seconds` | Gauge |
| Pool filesystem free space | `dblab.pool.fs.free_bytes` | Gauge |
| Pool filesystem total size | `dblab.pool.fs.size_bytes` | Gauge |
| Pool filesystem used space | `dblab.pool.fs.used_bytes` | Gauge |
| Pool data size | `dblab.pool.fs.data_size_bytes` | Gauge |
| Pool space used by snapshots | `dblab.pool.fs.used_by_snapshots_bytes` | Gauge |
| Pool space used by clones | `dblab.pool.fs.used_by_clones_bytes` | Gauge |
| Pool compression ratio | `dblab.pool.fs.compress_ratio` | Gauge |
| Clones per pool | `dblab.pool.clone_count` | Gauge |
| Total active clones | `dblab.cloning.num_clones` | Gauge |
| Expected clone creation time | `dblab.cloning.expected_time_seconds` | Gauge |

### Events

A `dblab.refresh.failed` event is emitted when the data refresh status is critical.

### Version tags (DBLab 4.0+ only)

On DBLab 4.0+, all metrics and service checks are automatically tagged with `dblab_version` and `dblab_edition` (e.g. `dblab_version:v4.0.0`, `dblab_edition:standard`). These are resolved via the unauthenticated `/healthz` endpoint and cached for 24 hours.

## Requirements

- Datadog Agent 7+
- DBLab Engine 3.5.0 or 4.0+
- Network access from the Agent host to the DBLab API

## Installation

1. Copy `checks.d/dblab.py` to your Agent's `checks.d` directory:

   | OS | Path |
   |---|---|
   | Linux | `/etc/datadog-agent/checks.d/` |
   | macOS | `~/.datadog-agent/checks.d/` |
   | Windows | `C:\ProgramData\Datadog\checks.d\` |

2. Copy `conf.d/dblab.d/conf.yaml` to your Agent's `conf.d` directory:

   | OS | Path |
   |---|---|
   | Linux | `/etc/datadog-agent/conf.d/dblab.d/` |
   | macOS | `~/.datadog-agent/conf.d/dblab.d/` |
   | Windows | `C:\ProgramData\Datadog\conf.d\dblab.d\` |

3. Edit `conf.yaml` with your DBLab instance details (see [Configuration](#configuration)).

4. Restart the Datadog Agent.

## Configuration

```yaml
init_config:

instances:
  - url: "https://<DBLAB_HOST>/api"
    verification_token: "<VERIFICATION_TOKEN>"
    tags:
      - "env:prod"
      - "dblab_instance:<INSTANCE_NAME>"
    # min_collection_interval: 60
```

| Option | Required | Description |
|---|---|---|
| `url` | Yes | Base URL of the DBLab Engine API. No trailing slash. |
| `verification_token` | Yes | DBLab verification token (`server.verificationToken` in DBLab config). |
| `tags` | No | List of tags to attach to all metrics and service checks. |
| `min_collection_interval` | No | Collection interval in seconds. Default: 15. Recommended: 60. |

Multiple DBLab instances can be monitored by adding additional entries under `instances`.

## Verifying the check

Run the check manually with:

```sh
sudo datadog-agent check dblab
```

## Service check status mapping

DBLab status codes are mapped to Datadog service check statuses as follows:

| DBLab status | Datadog status |
|---|---|
| `ok`, `refreshing` | OK |
| `warning`, `warn`, `pending` | WARNING |
| `error`, `err`, `failed` | CRITICAL |
| unknown / missing | UNKNOWN |

# ALM Platform — Architecture & Governance Document

**Version:** 1.0  
**Date:** June 2026  
**Classification:** Internal — For Distribution to Audit, Compliance, and Technology Stakeholders  

---

## 1. Executive Summary

The ALM Platform is a purpose-built financial model execution environment that enforces end-to-end governance over how analytical models are defined, deployed, launched, and reported on. Every model run that produces output used in official reporting is initiated through a single controlled web interface, passes through a mandatory change control gate before reaching production, and generates an immutable audit trail retained for seven years. Auditors have dedicated, always-on read access to the complete audit log.

This document describes the platform architecture with emphasis on four governance pillars:

- **Controlled Execution** — All models run inside a single, uniform environment
- **Change Control** — Models and the platform itself must pass a formal promotion process before use in production
- **Comprehensive Logging** — Every user action, model launch, and configuration change is recorded and retained for seven years
- **Audit Access** — Audit logs are continuously accessible to authorized audit users

---

## 2. System Overview

### 2.1 Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React 18 + TypeScript, served via Nginx | Single user interface |
| Backend API | Python 3.11, FastAPI | Business logic, authentication, audit |
| Task Queue | Celery + Redis | Controlled, sequential model execution |
| Database | PostgreSQL 15+ | Persistent state, audit log, run records |
| Container Runtime | Docker (host socket) | Isolated, reproducible model containers |
| Authentication | LDAP / Active Directory + JWT | Identity tied to all audit records |
| Infrastructure | Red Hat Enterprise Linux 8, Systemd | On-premise, institutional-grade hosting |

### 2.2 High-Level Architecture

```
User (browser)
     │
     ▼
  Nginx (HTTPS reverse proxy)
     │
     ├──► React SPA (single web interface)
     │
     └──► FastAPI (backend API + WebSocket)
               │
               ├──► PostgreSQL (runs, audit logs, users, models)
               │
               ├──► Redis (task queue, real-time log streaming)
               │
               └──► Celery Worker
                         │
                         └──► Docker Container Pipeline
                                   │
                                   └──► Model Outputs → Filesystem
```

---

## 3. Governance Pillar 1 — Single Controlled Execution Environment

### 3.1 Principle

No model may be executed outside the ALM Platform. All model runs — whether triggered manually by a user, on a schedule, or by an administrator — flow through the same queue, the same worker, and the same Docker orchestration layer. This eliminates shadow execution, ad-hoc spreadsheet runs, or direct server-side script executions that would be invisible to governance controls.

### 3.2 How It Is Enforced

**Single Web Interface**  
All users — regardless of role — access models exclusively through the ALM Platform web interface. There is no command-line bypass, no direct database write path for creating runs, and no batch submission outside the API. The Nginx reverse proxy exposes only the web application and API endpoints; no other services are publicly reachable.

**Role-Based Access Control**  
Access is gated by four roles assigned per user:

| Role | Capabilities |
|---|---|
| `admin` | Full access including user management, audit log, model admin |
| `developer` | Run models, view queue, view monitoring; access model admin in dev environment |
| `runner` | Submit and monitor model runs and queue |
| `reader` | View-only access to run history, outputs |

Every API endpoint enforces role requirements server-side. A `reader` cannot submit a run; a `runner` cannot modify a model definition.

**Authenticated Identity on Every Action**  
All users authenticate against the institutional LDAP/Active Directory. JWT tokens are issued on login and automatically expire. Every API request — including WebSocket connections for live log streaming — carries a validated JWT. The authenticated `username` is recorded on every run record and every audit log entry.

**Uniform Docker Container Execution**  
Models are not executed as scripts or processes on the host. Every model is defined as an ordered pipeline of Docker container images. The Celery worker pulls these definitions from the database and launches containers via the Docker daemon using a tightly controlled orchestration layer (`docker_runner/runner.py`). The following is uniform across all runs:

- Volume mounts: shared read-only input data at `/data/input`; run-specific output at `/data/output`; run-specific logs at `/data/logs`
- Environment variable injection: `RUN_ID`, `MODEL_SLUG`, `OUTPUT_DIR`, `LOG_DIR` plus config and input variables
- Sequential pipeline execution: containers within a model run in defined order; failure of any container halts the pipeline
- Resource limits: CPU and memory limits enforced per container via Docker's resource constraints

**Queue Discipline**  
Runs are not executed immediately on submission. They enter a queue with an assigned `queue_position`. A single Celery worker dequeues and executes runs one at a time (prefetch multiplier = 1). The queue is visible to authorized users in real time. This ensures ordered, observable execution — not ad-hoc parallel execution.

**Immutable Config Snapshot**  
When a run is submitted, the complete model configuration in effect at that moment is captured as a `config_snapshot` on the run record. Changes to a model's configuration after submission do not affect the run already in the queue. The output of every run is therefore reproducible and traceable to the exact configuration used.

---

## 4. Governance Pillar 2 — Change Control Before Production

### 4.1 Principle

The production server runs only approved versions of the platform software and approved, tested model definitions. No model or platform update may be applied to the production environment without passing through a controlled promotion path. Only results produced by models running on the production-approved platform version are eligible for use in official reporting.

### 4.2 Two-Environment Architecture

The platform operates in two distinct modes controlled by the `APP_MODE` environment variable:

| Mode | Purpose | Restrictions |
|---|---|---|
| `develop` | Model authoring, testing, iteration | Model Admin UI enabled; API docs exposed; dev users available; Docker image simulation on if image missing |
| `production` | Official reporting runs | Model Admin UI disabled (403); API docs hidden; all users from LDAP; no simulation fallbacks |

Model definitions created or modified in the develop environment are not automatically available in production. They must be explicitly exported (as YAML) and imported into the production environment by an authorized administrator — providing a manual, audited gate.

### 4.3 Model Change Control

**Model Definition as Versioned Artifacts**  
Each model definition is a database record containing:
- Ordered pipeline of Docker container images (with explicit image tags, e.g., `alm/ir-analyze:v2.1.3`)
- Default configuration (`default_config` JSONB)
- Input schema (`input_schema`)

Model records carry `created_at` and `updated_at` timestamps. Every create and update operation on a model generates an audit log entry (see Pillar 3).

**YAML Export / Import as the Change Gate**  
Model definitions can be exported from the develop environment as YAML files. These YAML files serve as the change artifact — they can be reviewed, approved, and version-controlled in a code repository (e.g., Git) before being imported into production. This makes the model promotion process explicit and traceable.

**Container Image Versioning**  
The platform does not automatically pull or update Docker images. All container images used by models must be explicitly built, tagged with a version identifier (not `latest` for production use), and loaded onto the production server before being referenced in a model definition. The image tag is part of the model record and is captured in the `config_snapshot` of every run, ensuring that which container version produced which output is always known.

**Database Schema Change Control**  
All database schema changes are managed through Alembic migrations with a linear versioning scheme (`001 → 002 → 003 → ...`). Migrations are applied explicitly during deployment (`alembic upgrade head`) and the current schema version is tracked in the `alembic_version` table. No ad-hoc schema modifications are made.

**Platform Software Deployment**  
Platform updates (backend API, frontend, worker code) are applied through Systemd service restarts or Docker Compose redeployments. These are deliberate, administrator-initiated operations. The separation of `APP_MODE=develop` and `APP_MODE=production` ensures development-in-progress work cannot accidentally surface in the reporting environment.

### 4.4 Report Eligibility

Only runs executed via the production platform — authenticated through LDAP, logged in the production database, and executed by the production Celery worker against the production-approved model definitions — produce outputs eligible for official reports. Outputs are stored at paths structured as:

```
{RUNS_BASE_PATH}/{run_id}/outputs/
```

And upon archival:

```
{ARCHIVE_BASE_PATH}/{username}/{model_slug}/{YYYY-MM-DD}/{run_id}/
```

The `run_id` links every output file back to its complete provenance record in the database: who ran it, when, with which model version, with which inputs, and with which configuration snapshot.

---

## 5. Governance Pillar 3 — Comprehensive Logging and Seven-Year Retention

### 5.1 Principle

Every significant action performed on the platform — model launches, configuration changes, user management actions, scheduling changes, archival operations — generates an immutable log record. These records are retained for a minimum of seven years and are available for review at any time.

### 5.2 Audit Log Structure

The `audit_logs` table in PostgreSQL is the central immutable record of all platform activity:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Unique record identifier |
| `timestamp` | Timestamp (UTC) | Exact time of the action |
| `user_id` | UUID | Foreign key to authenticated user |
| `username` | String | LDAP username at time of action (denormalized for durability) |
| `action` | String | Action performed (e.g., `run_created`, `model_updated`) |
| `resource_type` | String | What was acted on (e.g., `run`, `model`, `user`, `schedule`) |
| `resource_id` | String | Identifier of the specific resource |
| `details` | JSONB | Structured detail payload (inputs, config, before/after values) |
| `ip_address` | String | Client IP address of the request |

### 5.3 Events That Generate Audit Log Entries

| Category | Events Logged |
|---|---|
| **Model Runs** | Run created (with full inputs and config snapshot), run cancelled, run archived |
| **Model Definitions** | Model created, model updated (configuration, container images, input schema), model deleted |
| **Queue** | Queue reordered (drag-and-drop position changes) |
| **Schedules** | Schedule created, schedule activated/deactivated |
| **User Management** | User created, user role changed, user deactivated |
| **Authentication** | Login events (captured at JWT issuance via LDAP identity) |
| **System Events** | Resource threshold alerts (CPU/memory), cleanup operations |

### 5.4 Run Execution Logs

In addition to audit logs, every model run produces granular execution logs:

- **Container logs**: The stdout/stderr of every Docker container in the pipeline is written to `{run_id}/logs/{container_name}.log` on the filesystem
- **Real-time streaming**: Logs are published line-by-line to a Redis pub/sub channel (`run:{run_id}:logs`) and streamed live to users via WebSocket
- **Run record**: The `runs` table records `status`, `started_at`, `completed_at`, `exit_code` per container, `retry_count`, and peak resource usage (CPU%, memory MB)

### 5.5 Seven-Year Retention

**Active Run Data (First 30 Days)**  
Run records and outputs are retained in the active filesystem path for 30 days. A Celery Beat scheduled task runs daily at 2:00 AM UTC to remove runs older than 30 days that have not been explicitly archived.

**Archive (Long-Term Retention)**  
Any run can be archived before the 30-day expiry. Archival copies the entire run directory (outputs, logs) to the long-term archive path, organized as `{username}/{model_slug}/{YYYY-MM-DD}/{run_id}/`. The run record in the database is marked `is_archived=true` and includes the `archive_path`. Archived runs are not subject to the 30-day cleanup.

**Database Records (Seven-Year Retention)**  
The `audit_logs` table, `runs` table, and `run_containers` table in PostgreSQL must be retained for a minimum of seven years. This requires:

1. **No deletion policy on audit_logs**: The cleanup task does not touch the `audit_logs` table. Audit records are never deleted by the platform.
2. **Database backup policy**: The PostgreSQL database must be backed up on a schedule consistent with a seven-year retention requirement (e.g., daily backups retained for 7 years).
3. **Archive filesystem retention**: The `ARCHIVE_BASE_PATH` filesystem must be covered by the institutional storage retention policy for seven years.

The platform enforces the database-side constraint; the seven-year backup retention of the underlying PostgreSQL instance is implemented at the infrastructure/DBA level and must be documented in the institution's data retention policy.

### 5.6 Resource and System Monitoring Logs

A Celery Beat task runs every 60 seconds to check CPU and memory utilization. When a threshold is breached and the cooldown period has elapsed, a `ResourceAlert` record is written to the database and email notifications are sent to all administrators. This creates a continuous health record of the server environment.

---

## 6. Governance Pillar 4 — Continuous Audit Access

### 6.1 Principle

Auditors have access to the complete audit trail at all times — not on request, not after a ticket is raised, but through a dedicated interface available whenever they need it. The audit log is read-only and cannot be modified or deleted by any user of the platform.

### 6.2 Audit Log Interface

The platform includes a dedicated **Audit Log page** accessible to users with the `admin` role. The interface provides:

- **Full-history view**: All audit log entries from the beginning of the system, newest first
- **Search and filter**: Filter by user, action type, resource type, date range, or free-text search on the details field
- **CSV export**: Any filtered view can be exported as a CSV file for offline analysis, submission to external audit systems, or long-term offline archival

### 6.3 Audit Role Provisioning

Users granted the `admin` role have access to both the Audit Log page and the User Management page. For pure audit use cases, an auditor account can be provisioned with the `admin` role by a system administrator. The provisioning of this account is itself recorded as an audit log entry.

The system administrator should create dedicated read-focused auditor accounts rather than sharing admin credentials. All access to the audit log interface is authenticated via LDAP and recorded — meaning that auditor log reviews are themselves logged.

### 6.4 Immutability of the Audit Log

The audit log is append-only by design:

- **No API endpoint exists to delete or update audit log records.** The `audit_logs` table has no `DELETE` or `UPDATE` path exposed through the application layer.
- **Database-level protection**: The PostgreSQL role used by the application should be granted `INSERT` and `SELECT` on `audit_logs` only — not `UPDATE` or `DELETE`. This is enforced at the database permission level, separate from the application code.
- **Username denormalization**: The `username` field is stored directly on each audit record (not just as a foreign key to the `users` table). This ensures that even if a user account is deactivated or renamed, historical audit records remain accurate and readable.

### 6.5 API Access for External Audit Systems

The `/api/audit` endpoint provides programmatic access to audit records for integration with institutional SIEM systems, external audit platforms, or automated compliance reporting tools. Access requires a valid JWT from an `admin`-role account. Responses are paginated JSON with the same fields available in the UI.

---

## 7. Data Flow: From Run Submission to Auditable Record

The following describes the complete lifecycle of a model run from the governance perspective:

```
1. User logs in via LDAP → JWT issued
         │
         ▼
2. User selects model and submits inputs via web interface
   → API validates role (must be runner or above)
   → Run record created in DB: status=queued, config_snapshot captured
   → Audit log entry: action=run_created, user, inputs, config_snapshot, timestamp, IP
         │
         ▼
3. Run enters queue with queue_position assigned
   → Queue visible to all authenticated users in real time
         │
         ▼
4. Celery worker dequeues run
   → Resource check (memory/CPU budget)
   → Docker containers launched in pipeline order
   → Logs written to filesystem + streamed via Redis pub/sub → WebSocket → UI
   → RunContainer records updated with container_id, exit_code, peak resources
         │
         ▼
5. Run completes (or fails/is cancelled)
   → Run record updated: status, completed_at, output_path
   → Outputs available at run_id-scoped filesystem path
         │
         ▼
6. Administrator/user archives the run (before 30-day expiry)
   → Outputs copied to long-term archive path
   → Run record marked is_archived=true, archive_path set
   → Audit log entry: action=run_archived
         │
         ▼
7. Audit user reviews the record at any time
   → Audit Log page: full details of who ran what, when, with what config
   → Run Detail page: container-level logs, inputs, outputs, config snapshot
   → CSV export available for offline audit submission
```

---

## 8. Summary of Governance Controls

| Requirement | Implementation |
|---|---|
| Single execution interface | All models run via the platform web UI and API; no out-of-band execution path |
| Controlled environment | Docker containers with defined images, volume mounts, and resource limits; uniform across all runs |
| Change control for models | YAML export/import between environments; explicit image versioning; admin-only model management |
| Change control for platform | `APP_MODE=develop` vs `production` separation; Alembic-managed schema migrations; deliberate Systemd/Docker deployments |
| Only platform-produced results in reports | `run_id` links every output to a full provenance record in the production database |
| All actions logged | Immutable `audit_logs` table with user, action, resource, details, IP, and timestamp |
| Model launches logged | `run_created` audit entry captures full inputs, config snapshot, user identity |
| Model changes logged | `model_created` / `model_updated` audit entries on every definition change |
| Seven-year retention | Audit log is append-only; archive filesystem holds run outputs; DB backup policy covers 7 years |
| Audit access at all times | Dedicated Audit Log UI for `admin`-role users; CSV export; `/api/audit` endpoint for external systems |
| Audit log immutability | No DELETE/UPDATE API exists; database permissions enforce INSERT/SELECT only on `audit_logs` |

---

## 9. Recommended Operational Procedures

The following operational procedures complement the platform's technical controls to complete the governance framework:

1. **Image Version Policy**: Tag all production Docker model images with explicit semantic versions (e.g., `v2.1.3`). Never use `latest` in production model definitions. Update the model definition via the YAML change-control process when a new image version is approved.

2. **Database Backup and Retention**: Configure daily PostgreSQL backups with a retention policy of at least 7 years. Backups must cover the `audit_logs`, `runs`, and `run_containers` tables. Test restore procedures quarterly.

3. **Archive Before Expiry**: Establish a workflow to archive all reporting-relevant runs before the 30-day automatic cleanup. Consider scheduling automated archival of all completed runs via the API or by extending the cleanup threshold for specific model categories.

4. **Auditor Account Provisioning**: Create dedicated LDAP accounts for auditors with the `admin` role. Do not share credentials. Document auditor accounts in the system's user register.

5. **Model Promotion Process**: Formalize the YAML export → review → Git commit → import to production workflow as a documented change request process with approval sign-off by the model owner and technology owner.

6. **Access Review**: Conduct a quarterly review of user accounts and role assignments. Deactivate any accounts for departed staff immediately.

---

*This document describes the ALM Platform as built and deployed. It should be reviewed and updated whenever significant architectural changes are made to the platform.*

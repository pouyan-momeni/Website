# ALMPlatform — Financial Model Execution Platform

A production-grade web application for executing long-running financial models via Docker containers on on-premise Red Hat 8 servers. Built with FastAPI, React, Celery, and PostgreSQL.

## Features

- **Model Execution** — Run financial models as Docker container pipelines with sequential steps
- **Queue Management** — Drag-and-drop queue reordering for waiting runs
- **Real-Time Logs** — WebSocket-based live log streaming during model execution
- **Resource Monitoring** — CPU, memory, and disk tracking with threshold alerts
- **Scheduling** — Cron-based automatic model runs via Celery Beat
- **Archival** — Long-term storage with structured archive paths
- **LDAP Authentication** — Enterprise SSO with role-based access control (admin/developer/runner/reader)
- **Marimo Notebooks** — Interactive data exploration for developers (develop mode only)
- **Two Modes** — `develop` (full features) and `production` (locked-down)

## System Requirements

- **OS**: Red Hat Enterprise Linux 8 (or compatible)
- **Python**: 3.11+
- **Node.js**: 18+ (for frontend build)
- **PostgreSQL**: 15+
- **Redis**: 7+
- **Docker Engine**: 24+ (no Swarm/Kubernetes)
- **Nginx**: 1.20+

## Quick Setup (Red Hat 8)

### 1. Install System Dependencies

```bash
# Enable EPEL and required repos
sudo dnf install -y epel-release
sudo dnf module enable -y postgresql:15 redis:7 nginx:1.22 nodejs:18

# Install packages
sudo dnf install -y \
  python3.11 python3.11-pip python3.11-devel \
  postgresql-server postgresql-devel \
  redis nginx nodejs npm \
  gcc openldap-devel docker-ce

# Initialize PostgreSQL
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql

# Start Redis & Docker
sudo systemctl enable --now redis docker
```

### 2. Configure PostgreSQL

```bash
sudo -u postgres psql <<EOF
CREATE USER almplatform WITH PASSWORD 'your_secure_password';
CREATE DATABASE almplatform OWNER almplatform;
GRANT ALL PRIVILEGES ON DATABASE almplatform TO almplatform;
EOF

# Enable password auth — edit pg_hba.conf
sudo vi /var/lib/pgsql/data/pg_hba.conf
# Change "ident" to "md5" for local connections
sudo systemctl restart postgresql
```

### 3. Set Up Application

```bash
# Clone to /app
sudo mkdir -p /app && cd /app

# Create Python virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r backend/requirements.txt

# Configure environment
cp .env.example .env
vi .env  # Fill in all values

# Create data directories
sudo mkdir -p /data/almplatform/{runs,archive,marimo}
sudo chown -R almplatform:almplatform /data/almplatform

# Run database migrations
alembic upgrade head

# Seed example data
python scripts/seed_models.py
```

### 4. Build Frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

### 5. Configure Nginx

```bash
sudo cp nginx/nginx.conf /etc/nginx/nginx.conf
sudo nginx -t
sudo systemctl enable --now nginx
```

### 6. Install & Start Services

```bash
sudo bash scripts/install-services.sh
```

### 7. Verify

```bash
# Check all services
systemctl status almapp-api almapp-worker almapp-beat almapp-redis nginx

# Test API
curl http://localhost/api/health

# View logs
journalctl -u almapp-api -f
```

## Running with Docker Compose (No Systemd)

If you prefer to run the entire stack (Frontend, API, Worker, Beat, Postgres, Redis) via Docker Compose without installing systemd services:

### 1. Configure Environment
```bash
cp .env.example .env
vi .env  # Fill in all necessary values
```

### 2. Build and Start Services
```bash
# Start all services in the background
docker compose up -d

# Check logs
docker compose logs -f
```

### 3. Initialize Database
```bash
# Run Alembic migrations
docker compose run --rm api alembic upgrade head

# Seed initial data
docker compose run --rm api python scripts/seed_models.py
```

The application will be available at `http://localhost`.

## Running in Development

```bash
# Terminal 1: API
source venv/bin/activate
uvicorn backend.main:app --reload --port 8000

# Terminal 2: Celery Worker
celery -A backend.workers.celery_app worker --loglevel=info --concurrency=2

# Terminal 3: Celery Beat
celery -A backend.workers.celery_app beat --loglevel=info

# Terminal 4: Frontend dev server
cd frontend && npm run dev
```

## Deployment Modes

| Feature | `develop` | `production` |
|---|---|---|
| Model Admin (create/edit) | ✅ | ❌ (403) |
| Input Schema editing | ✅ | ❌ (403) |
| Marimo Notebooks | ✅ | ❌ (403) |
| API docs (/api/docs) | ✅ | ❌ |
| All other features | ✅ | ✅ |

Set `APP_MODE=develop` or `APP_MODE=production` in `.env`.

## Architecture

```
┌─────────┐     ┌─────────┐     ┌──────────┐
│  Nginx  │────►│ FastAPI │────►│PostgreSQL│
│  (SPA)  │     │  (API)  │     └──────────┘
└─────────┘     └────┬────┘
                     │
                ┌────▼────┐     ┌──────────┐
                │  Redis  │◄───►│  Celery  │
                │ (broker)│     │ (worker) │
                └─────────┘     └────┬─────┘
                                     │
                                ┌────▼─────┐
                                │  Docker  │
                                │(containers)│
                                └──────────┘
```

## Role Hierarchy

| Role | Capabilities |
|---|---|
| `admin` | Everything + user management + model admin (develop mode) |
| `developer` | Run models + queue + monitoring + Marimo (develop mode) |
| `runner` | Run models + queue + monitoring + archive |
| `reader` | View runs and history only |

## Key Paths

| Path | Purpose |
|---|---|
| `RUNS_BASE_PATH/{run_id}/outputs/` | Run output files |
| `RUNS_BASE_PATH/{run_id}/logs/` | Container log files |
| `ARCHIVE_BASE_PATH/{user}/{slug}/{date}/{run_id}/` | Archived runs |
| `SHARED_NAS_PATH` | Shared NAS mount (read-only in containers) |
| `MARIMO_BASE_PATH/{user}/` | Marimo notebooks per user |

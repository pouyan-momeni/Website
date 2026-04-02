"""Pydantic schemas for all API request/response models."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Auth ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    pass  # refresh token comes from httpOnly cookie


# ─── User ────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    ldap_username: str
    email: Optional[str] = None
    role: str = Field(default="reader", pattern="^(admin|developer|runner|reader)$")


class UserUpdate(BaseModel):
    role: str = Field(pattern="^(admin|developer|runner|reader)$")


class UserResponse(BaseModel):
    id: UUID
    ldap_username: str
    email: Optional[str]
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Model ───────────────────────────────────────────────────────────────────

class DockerImageSpec(BaseModel):
    name: str
    image: str
    order: int
    extra_args: str = Field(default="", description="Raw docker run arguments, e.g. --rm -v /host:/container -e KEY=val")


class ConfigField(BaseModel):
    value: Any
    type: str
    description: str = ""


class InputField(BaseModel):
    name: str
    type: str
    required: bool = True
    source: Optional[str] = Field(default=None, pattern="^(upload|server)$")


class ModelCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    category: Optional[str] = None
    docker_images: list[DockerImageSpec] = Field(default_factory=list)
    default_config: dict[str, ConfigField] = Field(default_factory=dict)
    input_schema: list[InputField] = Field(default_factory=list)


class ResourceStats(BaseModel):
    avg_cpu_percent: float
    avg_memory_mb: float
    avg_disk_mb: float
    avg_duration_seconds: float
    sample_count: int


class ModelResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str]
    category: Optional[str] = None
    docker_images: list[dict[str, Any]]
    default_config: dict[str, Any]
    input_schema: list[dict[str, Any]]
    avg_resources: Optional[ResourceStats] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConfigUpdate(BaseModel):
    default_config: dict[str, Any]


class InputSchemaUpdate(BaseModel):
    input_schema: list[dict[str, Any]]


class ContainersUpdate(BaseModel):
    docker_images: list[DockerImageSpec]


# ─── Run ─────────────────────────────────────────────────────────────────────

class RunCreate(BaseModel):
    model_id: UUID
    inputs: dict[str, Any] = Field(default_factory=dict)
    config_override: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    id: UUID
    model_id: UUID
    triggered_by: UUID
    status: str
    inputs: Optional[dict[str, Any]]
    config_snapshot: Optional[dict[str, Any]]
    celery_task_id: Optional[str]
    current_container_index: int
    queue_position: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    is_archived: bool
    archived_at: Optional[datetime]
    archive_path: Optional[str]
    output_path: Optional[str]
    log_path: Optional[str]

    model_config = {"from_attributes": True}


class RunListResponse(BaseModel):
    id: UUID
    model_id: UUID
    triggered_by: UUID
    status: str
    queue_position: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    is_archived: bool
    model_name: Optional[str] = None
    username: Optional[str] = None

    model_config = {"from_attributes": True}


# ─── Run Container ──────────────────────────────────────────────────────────

class RunContainerResponse(BaseModel):
    id: UUID
    run_id: UUID
    container_name: str
    docker_container_id: Optional[str]
    status: str
    retry_count: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    exit_code: Optional[int]
    log_file: Optional[str]

    model_config = {"from_attributes": True}


# ─── Queue ───────────────────────────────────────────────────────────────────

class QueueReorderRequest(BaseModel):
    run_ids: list[UUID]


# ─── Schedule ────────────────────────────────────────────────────────────────

class ScheduleCreate(BaseModel):
    model_id: UUID
    cron_expression: str
    inputs: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None


class ScheduleUpdate(BaseModel):
    cron_expression: Optional[str] = None
    inputs: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class ScheduleResponse(BaseModel):
    id: UUID
    model_id: UUID
    created_by: UUID
    cron_expression: str
    inputs: Optional[dict[str, Any]]
    config: Optional[dict[str, Any]]
    is_active: bool
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─── Monitoring ──────────────────────────────────────────────────────────────

class ResourceSnapshot(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_total_gb: float
    memory_used_gb: float
    disk_percent: float
    disk_total_gb: float
    disk_used_gb: float


class ContainerInfo(BaseModel):
    docker_id: str
    name: str
    image: str
    status: str
    run_id: Optional[str]
    started_at: Optional[str]
    memory_usage_mb: Optional[float]
    cpu_percent: Optional[float] = None


class NotebookMonitorInfo(BaseModel):
    id: str
    name: str
    owner_username: str
    status: str
    url: Optional[str]
    port: Optional[int]
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None
    started_at: Optional[str] = None


# ─── Marimo ──────────────────────────────────────────────────────────────────

class MarimoLaunchResponse(BaseModel):
    port: int
    url: str


class MarimoStatusResponse(BaseModel):
    running: bool
    port: Optional[int] = None
    url: Optional[str] = None

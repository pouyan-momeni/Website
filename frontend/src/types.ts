export interface User {
    id: string;
    ldap_username: string;
    email: string | null;
    role: 'admin' | 'developer' | 'runner' | 'reader';
    is_active: boolean;
    created_at: string;
}

export interface DockerImageSpec {
    name: string;
    image: string;
    order: number;
    extra_args: string;
}

export interface ConfigField {
    value: unknown;
    type: string;
    description: string;
}

export interface InputField {
    name: string;
    type: string;
    required: boolean;
    source?: 'upload' | 'server';
}

export interface Model {
    id: string;
    name: string;
    slug: string;
    description: string | null;
    docker_images: DockerImageSpec[];
    default_config: Record<string, ConfigField>;
    input_schema: InputField[];
    created_at: string;
    updated_at: string;
}

export interface Run {
    id: string;
    model_id: string;
    triggered_by: string;
    status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
    inputs: Record<string, unknown> | null;
    config_snapshot: Record<string, unknown> | null;
    celery_task_id: string | null;
    current_container_index: number;
    queue_position: number | null;
    started_at: string | null;
    completed_at: string | null;
    created_at: string;
    is_archived: boolean;
    archived_at: string | null;
    archive_path: string | null;
    output_path: string | null;
    log_path: string | null;
}

export interface RunListItem {
    id: string;
    model_id: string;
    triggered_by: string;
    status: string;
    queue_position: number | null;
    started_at: string | null;
    completed_at: string | null;
    created_at: string;
    is_archived: boolean;
    model_name: string | null;
    username: string | null;
}

export interface RunContainer {
    id: string;
    run_id: string;
    container_name: string;
    docker_container_id: string | null;
    status: string;
    retry_count: number;
    started_at: string | null;
    completed_at: string | null;
    exit_code: number | null;
    log_file: string | null;
}

export interface Schedule {
    id: string;
    model_id: string;
    model_name: string;
    created_by: string;
    created_by_username: string;
    scheduled_at: string;
    repeat_type: 'none' | 'daily' | 'weekly' | 'monthly' | 'custom';
    cron_expression: string | null;
    repeat_count: number | null;
    executions_done: number;
    inputs: Record<string, unknown> | null;
    config: Record<string, unknown> | null;
    is_active: boolean;
    next_run_at: string | null;
    last_run_at: string | null;
    created_at: string;
}

export interface ResourceSnapshot {
    cpu_percent: number;
    memory_percent: number;
    memory_total_gb: number;
    memory_used_gb: number;
    disk_percent: number;
    disk_total_gb: number;
    disk_used_gb: number;
}

export interface ContainerInfo {
    docker_id: string;
    name: string;
    image: string;
    status: string;
    run_id: string | null;
    started_at: string | null;
    memory_usage_mb: number | null;
    cpu_percent: number | null;
}

export interface NotebookMonitorInfo {
    id: string;
    name: string;
    owner_username: string;
    status: string;
    url: string | null;
    port: number | null;
    cpu_percent: number | null;
    memory_mb: number | null;
    started_at: string | null;
}

export interface TokenResponse {
    access_token: string;
    token_type: string;
}

export interface Notebook {
    id: string;
    name: string;
    description?: string;
    owner_id: string;
    owner_username: string;
    folder: 'personal' | 'shared';
    shared_from?: string | null;
    status: 'stopped' | 'running' | 'paused';
    created_at: string;
    updated_at?: string;
    port: number | null;
    url: string | null;
}

import { useAuthStore } from '../stores/auth';
import type {
    Model, Run, RunListItem, Schedule, ResourceSnapshot,
    ContainerInfo, User, TokenResponse, Notebook,
} from '../types';

const BASE_URL = '/api';

class ApiClient {
    private getHeaders(): Record<string, string> {
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };
        const token = useAuthStore.getState().accessToken;
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        return headers;
    }

    private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
        const url = `${BASE_URL}${path}`;
        const response = await fetch(url, {
            ...options,
            headers: { ...this.getHeaders(), ...options.headers as Record<string, string> },
            credentials: 'include',
        });

        if (response.status === 401) {
            const refreshed = await this.tryRefresh();
            if (refreshed) {
                const retryResponse = await fetch(url, {
                    ...options,
                    headers: { ...this.getHeaders(), ...options.headers as Record<string, string> },
                    credentials: 'include',
                });
                if (!retryResponse.ok) {
                    throw new Error(`API error: ${retryResponse.status}`);
                }
                return retryResponse.json();
            }
            useAuthStore.getState().clearAuth();
            window.location.href = '/login';
            throw new Error('Session expired');
        }

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(error.detail || `API error: ${response.status}`);
        }

        if (response.status === 204) return undefined as T;
        return response.json();
    }

    private async tryRefresh(): Promise<boolean> {
        try {
            const response = await fetch(`${BASE_URL}/auth/refresh`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            });
            if (response.ok) {
                const data: TokenResponse = await response.json();
                const { user } = useAuthStore.getState();
                if (user) {
                    useAuthStore.getState().setAuth(data.access_token, user);
                }
                return true;
            }
            return false;
        } catch {
            return false;
        }
    }

    // Auth
    async login(username: string, password: string): Promise<TokenResponse> {
        return this.request('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
    }

    async logout(): Promise<void> {
        await this.request('/auth/logout', { method: 'POST' });
    }

    async getMode(): Promise<{ mode: string }> {
        const response = await fetch(`${BASE_URL}/config/mode`);
        return response.json();
    }

    // Models
    async getModels(): Promise<Model[]> {
        return this.request('/models');
    }

    async getModel(id: string): Promise<Model> {
        return this.request(`/models/${id}`);
    }

    async createModel(data: Partial<Model>): Promise<Model> {
        return this.request('/models', { method: 'POST', body: JSON.stringify(data) });
    }

    async updateConfig(modelId: string, config: Record<string, unknown>): Promise<Model> {
        return this.request(`/models/${modelId}/config`, {
            method: 'PUT',
            body: JSON.stringify({ default_config: config }),
        });
    }

    async updateInputSchema(modelId: string, schema: unknown[]): Promise<Model> {
        return this.request(`/models/${modelId}/input-schema`, {
            method: 'PUT',
            body: JSON.stringify({ input_schema: schema }),
        });
    }

    async updateContainers(modelId: string, images: unknown[]): Promise<Model> {
        return this.request(`/models/${modelId}/containers`, {
            method: 'PUT',
            body: JSON.stringify({ docker_images: images }),
        });
    }

    // Runs
    async createRun(data: { model_id: string; inputs: Record<string, unknown>; config_override: Record<string, unknown> }): Promise<Run> {
        return this.request('/runs', { method: 'POST', body: JSON.stringify(data) });
    }

    async getRuns(params?: Record<string, string>): Promise<RunListItem[]> {
        const query = params ? '?' + new URLSearchParams(params).toString() : '';
        return this.request(`/runs${query}`);
    }

    async getRun(id: string): Promise<Run> {
        return this.request(`/runs/${id}`);
    }

    async cancelRun(id: string): Promise<void> {
        await this.request(`/runs/${id}`, { method: 'DELETE' });
    }

    async archiveRun(id: string): Promise<Run> {
        return this.request(`/runs/${id}/archive`, { method: 'POST' });
    }

    async deleteRun(id: string): Promise<void> {
        await this.request(`/runs/${id}/delete`, { method: 'DELETE' });
    }

    async getRunLogs(id: string): Promise<{ logs: string[] }> {
        return this.request(`/runs/${id}/logs`);
    }

    async unarchiveRun(id: string): Promise<Run> {
        return this.request(`/runs/${id}/unarchive`, { method: 'POST' });
    }

    async getRunOutputs(id: string): Promise<{ files: Array<{ name: string; size: number; type: string; extension: string }> }> {
        return this.request(`/runs/${id}/outputs`);
    }

    getRunOutputUrl(id: string, filename: string): string {
        return `/api/runs/${id}/outputs/${encodeURIComponent(filename)}`;
    }

    // Queue
    async getQueue(): Promise<RunListItem[]> {
        return this.request('/queue');
    }

    async reorderQueue(runIds: string[]): Promise<void> {
        await this.request('/queue/reorder', {
            method: 'PUT',
            body: JSON.stringify({ run_ids: runIds }),
        });
    }

    // Schedules
    async getSchedules(): Promise<Schedule[]> {
        return this.request('/schedules');
    }

    async createSchedule(data: {
        model_id: string; model_name?: string; scheduled_at: string;
        repeat_type: string; cron_expression?: string; repeat_count?: number;
        inputs?: Record<string, unknown>; config?: Record<string, unknown>;
    }): Promise<Schedule> {
        return this.request('/schedules', { method: 'POST', body: JSON.stringify(data) });
    }

    async toggleSchedule(id: string): Promise<Schedule> {
        return this.request(`/schedules/${id}/toggle`, { method: 'POST' });
    }

    async deleteSchedule(id: string): Promise<void> {
        await this.request(`/schedules/${id}`, { method: 'DELETE' });
    }

    // Monitoring
    async getResources(): Promise<ResourceSnapshot> {
        return this.request('/monitoring/resources');
    }

    async getContainers(): Promise<ContainerInfo[]> {
        return this.request('/monitoring/containers');
    }

    async killContainer(dockerId: string): Promise<void> {
        await this.request(`/monitoring/containers/${dockerId}`, { method: 'DELETE' });
    }

    // Users
    async getUsers(): Promise<User[]> {
        return this.request('/users');
    }

    async createUser(data: { ldap_username: string; email?: string; role: string }): Promise<User> {
        return this.request('/users', { method: 'POST', body: JSON.stringify(data) });
    }

    async updateUserRole(userId: string, role: string): Promise<User> {
        return this.request(`/users/${userId}/role`, { method: 'PUT', body: JSON.stringify({ role }) });
    }

    async deactivateUser(userId: string): Promise<void> {
        await this.request(`/users/${userId}`, { method: 'DELETE' });
    }

    // Notebooks
    async getNotebooks(): Promise<Notebook[]> {
        return this.request('/notebooks');
    }

    async createNotebook(name: string): Promise<Notebook> {
        return this.request('/notebooks', { method: 'POST', body: JSON.stringify({ name }) });
    }

    async startNotebook(id: string): Promise<Notebook> {
        return this.request(`/notebooks/${id}/start`, { method: 'POST' });
    }

    async stopNotebook(id: string): Promise<Notebook> {
        return this.request(`/notebooks/${id}/stop`, { method: 'POST' });
    }

    async pauseNotebook(id: string): Promise<Notebook> {
        return this.request(`/notebooks/${id}/pause`, { method: 'POST' });
    }

    async deleteNotebook(id: string): Promise<void> {
        await this.request(`/notebooks/${id}`, { method: 'DELETE' });
    }

    // Audit
    async getAuditLog(params: string): Promise<{ entries: unknown[]; total: number; page: number; page_size: number }> {
        return this.request(`/audit?${params}`);
    }
}

export const api = new ApiClient();

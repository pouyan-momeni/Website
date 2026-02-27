import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

export function formatDuration(startedAt: string | null, completedAt: string | null): string {
    if (!startedAt) return '—';
    const start = new Date(startedAt).getTime();
    const end = completedAt ? new Date(completedAt).getTime() : Date.now();
    const delta = Math.floor((end - start) / 1000);
    const hours = Math.floor(delta / 3600);
    const minutes = Math.floor((delta % 3600) / 60);
    const seconds = delta % 60;
    if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
    if (minutes > 0) return `${minutes}m ${seconds}s`;
    return `${seconds}s`;
}

export function formatDate(dateStr: string | null): string {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleString();
}

export function statusColor(status: string): string {
    switch (status) {
        case 'completed': return 'text-emerald-400';
        case 'running': return 'text-blue-400';
        case 'queued': return 'text-amber-400';
        case 'failed': return 'text-red-400';
        case 'cancelled': return 'text-gray-400';
        default: return 'text-muted-foreground';
    }
}

export function statusBg(status: string): string {
    switch (status) {
        case 'completed': return 'bg-emerald-500/10 border-emerald-500/20';
        case 'running': return 'bg-blue-500/10 border-blue-500/20';
        case 'queued': return 'bg-amber-500/10 border-amber-500/20';
        case 'failed': return 'bg-red-500/10 border-red-500/20';
        case 'cancelled': return 'bg-gray-500/10 border-gray-500/20';
        default: return 'bg-muted';
    }
}

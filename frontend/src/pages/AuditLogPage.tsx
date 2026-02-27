import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { Loader2, FileText, Filter, User, Clock, ChevronDown, X } from 'lucide-react';

interface AuditEntry {
    id: string;
    timestamp: string;
    user_id: string;
    username: string;
    action: string;
    resource_type: string;
    resource_id: string | null;
    details: Record<string, unknown>;
    ip_address: string | null;
}

interface AuditResponse {
    entries: AuditEntry[];
    total: number;
    page: number;
    page_size: number;
}

const actionColors: Record<string, string> = {
    login: 'bg-emerald-500/10 text-emerald-400',
    logout: 'bg-slate-500/10 text-slate-400',
    create_run: 'bg-blue-500/10 text-blue-400',
    create_schedule: 'bg-purple-500/10 text-purple-400',
    start_notebook: 'bg-amber-500/10 text-amber-400',
    stop_notebook: 'bg-red-500/10 text-red-400',
    schedule_trigger: 'bg-cyan-500/10 text-cyan-400',
};

const actionLabels: Record<string, string> = {
    login: 'Login',
    logout: 'Logout',
    create_run: 'Created Run',
    create_schedule: 'Created Schedule',
    start_notebook: 'Started Notebook',
    stop_notebook: 'Stopped Notebook',
    schedule_trigger: 'Schedule Triggered',
};

function formatTime(iso: string) {
    try {
        const d = new Date(iso);
        return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'medium' });
    } catch {
        return iso;
    }
}

export default function AuditLogPage() {
    const [page, setPage] = useState(1);
    const [filterUser, setFilterUser] = useState('');
    const [filterAction, setFilterAction] = useState('');
    const [filterResource, setFilterResource] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('page_size', '30');
    if (filterUser) params.set('username', filterUser);
    if (filterAction) params.set('action', filterAction);
    if (filterResource) params.set('resource_type', filterResource);

    const { data, isLoading } = useQuery<AuditResponse>({
        queryKey: ['audit', page, filterUser, filterAction, filterResource],
        queryFn: () => api.getAuditLog(params.toString()) as Promise<AuditResponse>,
        refetchInterval: 10000,
    });

    const totalPages = data ? Math.ceil(data.total / data.page_size) : 1;
    const hasFilters = filterUser || filterAction || filterResource;

    return (
        <div className="max-w-5xl mx-auto animate-fade-in">
            <div className="flex items-center justify-between mb-6">
                <h1 className="text-2xl font-bold flex items-center gap-2">
                    <FileText className="w-6 h-6 text-primary" />
                    Audit Log
                </h1>
                <button
                    onClick={() => setShowFilters(!showFilters)}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors ${showFilters || hasFilters
                        ? 'border-primary/50 bg-primary/10 text-primary'
                        : 'border-border text-muted-foreground hover:text-foreground hover:bg-accent'
                        }`}
                >
                    <Filter className="w-4 h-4" />
                    Filters
                    {hasFilters && (
                        <span className="w-2 h-2 rounded-full bg-primary" />
                    )}
                    <ChevronDown className={`w-3 h-3 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
                </button>
            </div>

            {/* Filters */}
            {showFilters && (
                <div className="bg-card border border-border rounded-xl p-4 mb-6 grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                        <label className="block text-xs text-muted-foreground mb-1">Username</label>
                        <input
                            value={filterUser}
                            onChange={e => { setFilterUser(e.target.value); setPage(1); }}
                            placeholder="Filter by user..."
                            className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                        />
                    </div>
                    <div>
                        <label className="block text-xs text-muted-foreground mb-1">Action</label>
                        <select
                            value={filterAction}
                            onChange={e => { setFilterAction(e.target.value); setPage(1); }}
                            className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                        >
                            <option value="">All actions</option>
                            <option value="login">Login</option>
                            <option value="create_run">Create Run</option>
                            <option value="create_schedule">Create Schedule</option>
                            <option value="start_notebook">Start Notebook</option>
                            <option value="schedule_trigger">Schedule Trigger</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs text-muted-foreground mb-1">Resource</label>
                        <select
                            value={filterResource}
                            onChange={e => { setFilterResource(e.target.value); setPage(1); }}
                            className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                        >
                            <option value="">All resources</option>
                            <option value="auth">Auth</option>
                            <option value="run">Run</option>
                            <option value="schedule">Schedule</option>
                            <option value="notebook">Notebook</option>
                        </select>
                    </div>
                    {hasFilters && (
                        <button
                            onClick={() => { setFilterUser(''); setFilterAction(''); setFilterResource(''); setPage(1); }}
                            className="col-span-full text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                        >
                            <X className="w-3 h-3" /> Clear filters
                        </button>
                    )}
                </div>
            )}

            {/* Table */}
            <div className="bg-card border border-border rounded-xl overflow-hidden">
                {isLoading ? (
                    <div className="flex justify-center py-12">
                        <Loader2 className="w-6 h-6 animate-spin text-primary" />
                    </div>
                ) : !data || data.entries.length === 0 ? (
                    <div className="text-center text-muted-foreground py-12 text-sm">
                        No audit log entries{hasFilters ? ' matching filters' : ' yet'}.
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-border text-muted-foreground text-left">
                                    <th className="px-4 py-3 font-medium">
                                        <div className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" /> Time</div>
                                    </th>
                                    <th className="px-4 py-3 font-medium">
                                        <div className="flex items-center gap-1"><User className="w-3.5 h-3.5" /> User</div>
                                    </th>
                                    <th className="px-4 py-3 font-medium">Action</th>
                                    <th className="px-4 py-3 font-medium">Resource</th>
                                    <th className="px-4 py-3 font-medium">Details</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.entries.map(entry => (
                                    <tr key={entry.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                                        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">
                                            {formatTime(entry.timestamp)}
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className="font-medium text-sm">{entry.username}</span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={`text-xs px-2 py-1 rounded-full font-medium ${actionColors[entry.action] || 'bg-muted text-muted-foreground'
                                                }`}>
                                                {actionLabels[entry.action] || entry.action}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className="text-xs text-muted-foreground">{entry.resource_type}</span>
                                            {entry.resource_id && (
                                                <span className="ml-1 text-xs font-mono text-muted-foreground/60">
                                                    {entry.resource_id.slice(0, 8)}
                                                </span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-xs text-muted-foreground max-w-[200px] truncate">
                                            {entry.details && Object.keys(entry.details).length > 0
                                                ? Object.entries(entry.details).map(([k, v]) => `${k}: ${v}`).join(', ')
                                                : '—'
                                            }
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Pagination */}
                {data && data.total > data.page_size && (
                    <div className="flex items-center justify-between px-4 py-3 border-t border-border">
                        <span className="text-xs text-muted-foreground">
                            {data.total} entries · Page {page} of {totalPages}
                        </span>
                        <div className="flex gap-2">
                            <button
                                onClick={() => setPage(p => Math.max(1, p - 1))}
                                disabled={page <= 1}
                                className="px-3 py-1 text-xs border border-border rounded-lg disabled:opacity-40 hover:bg-accent transition-colors"
                            >
                                Previous
                            </button>
                            <button
                                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                                disabled={page >= totalPages}
                                className="px-3 py-1 text-xs border border-border rounded-lg disabled:opacity-40 hover:bg-accent transition-colors"
                            >
                                Next
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

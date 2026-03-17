import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { formatDate, formatDuration, statusColor, statusBg } from '../lib/utils';
import { Loader2, Search, Archive, ArchiveRestore, Eye, ChevronLeft, ChevronRight, Trash2, CheckCircle } from 'lucide-react';

export default function RunHistoryPage() {
    const queryClient = useQueryClient();
    const [filters, setFilters] = useState<Record<string, string>>({});
    const [page, setPage] = useState(0);
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
    const pageSize = 20;

    const { data: models } = useQuery({
        queryKey: ['models'],
        queryFn: () => api.getModels(),
    });

    const params: Record<string, string> = {
        limit: String(pageSize),
        offset: String(page * pageSize),
        ...filters,
    };
    Object.keys(params).forEach(k => { if (!params[k]) delete params[k]; });

    const { data: runs, isLoading } = useQuery({
        queryKey: ['runs', params],
        queryFn: () => api.getRuns(params),
        refetchInterval: 5000,
    });

    const archiveMutation = useMutation({
        mutationFn: (id: string) => api.archiveRun(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runs'] }),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: string) => api.deleteRun(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['runs'] });
            setDeleteConfirmId(null);
        },
    });

    const unarchiveMutation = useMutation({
        mutationFn: (id: string) => api.unarchiveRun(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runs'] }),
    });

    return (
        <div className="animate-fade-in">
            <h1 className="text-2xl font-bold mb-6">Run History</h1>

            {/* Filters */}
            <div className="flex flex-wrap gap-3 mb-6 bg-card border border-border rounded-xl p-4">
                <div className="relative flex-1 min-w-[200px]">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <select
                        value={filters.model_id || ''}
                        onChange={(e) => { setFilters(f => ({ ...f, model_id: e.target.value })); setPage(0); }}
                        className="w-full pl-10 pr-3 py-2 bg-background border border-border rounded-lg text-sm focus:ring-2 focus:ring-primary/50"
                    >
                        <option value="">All Models</option>
                        {models?.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                    </select>
                </div>
                <select
                    value={filters.status || ''}
                    onChange={(e) => { setFilters(f => ({ ...f, status: e.target.value })); setPage(0); }}
                    className="px-3 py-2 bg-background border border-border rounded-lg text-sm focus:ring-2 focus:ring-primary/50"
                >
                    <option value="">All Statuses</option>
                    <option value="queued">Queued</option>
                    <option value="running">Running</option>
                    <option value="completed">Completed</option>
                    <option value="failed">Failed</option>
                    <option value="cancelled">Cancelled</option>
                </select>
                <input
                    type="date"
                    value={filters.date_from || ''}
                    onChange={(e) => { setFilters(f => ({ ...f, date_from: e.target.value })); setPage(0); }}
                    className="px-3 py-2 bg-background border border-border rounded-lg text-sm focus:ring-2 focus:ring-primary/50"
                />
                <input
                    type="date"
                    value={filters.date_to || ''}
                    onChange={(e) => { setFilters(f => ({ ...f, date_to: e.target.value })); setPage(0); }}
                    className="px-3 py-2 bg-background border border-border rounded-lg text-sm focus:ring-2 focus:ring-primary/50"
                />
            </div>

            {/* Delete Confirmation Modal */}
            {deleteConfirmId && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 animate-fade-in">
                    <div className="bg-card border border-border rounded-xl p-6 max-w-md mx-4 shadow-2xl">
                        <h3 className="font-semibold text-lg mb-2">Delete Run</h3>
                        <p className="text-sm text-muted-foreground mb-6">
                            Are you sure you want to permanently delete this run? This action cannot be undone.
                        </p>
                        <div className="flex gap-3 justify-end">
                            <button onClick={() => setDeleteConfirmId(null)} className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent">Cancel</button>
                            <button
                                onClick={() => deleteMutation.mutate(deleteConfirmId)}
                                disabled={deleteMutation.isPending}
                                className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-500 disabled:opacity-50"
                            >
                                {deleteMutation.isPending ? 'Deleting...' : 'Delete Run'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Table */}
            {isLoading ? (
                <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>
            ) : (
                <div className="bg-card border border-border rounded-xl overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-border text-muted-foreground text-left">
                                    <th className="px-4 py-3 font-medium">Model</th>
                                    <th className="px-4 py-3 font-medium">Status</th>
                                    <th className="px-4 py-3 font-medium">Triggered By</th>
                                    <th className="px-4 py-3 font-medium">Started</th>
                                    <th className="px-4 py-3 font-medium">Duration</th>
                                    <th className="px-4 py-3 font-medium">Archived</th>
                                    <th className="px-4 py-3 font-medium">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {runs?.map(run => (
                                    <tr key={run.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                                        <td className="px-4 py-3 font-medium">{run.model_name || '—'}</td>
                                        <td className="px-4 py-3">
                                            <span className={`text-xs font-medium px-2 py-1 rounded-full border ${statusBg(run.status)} ${statusColor(run.status)}`}>
                                                {run.status === 'running' && <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400 mr-1 animate-pulse" />}
                                                {run.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-muted-foreground">{run.username || '—'}</td>
                                        <td className="px-4 py-3 text-muted-foreground">{formatDate(run.started_at)}</td>
                                        <td className="px-4 py-3 text-muted-foreground">{formatDuration(run.started_at, run.completed_at)}</td>
                                        <td className="px-4 py-3">
                                            {run.is_archived ? (
                                                <span className="text-emerald-400 flex items-center gap-1">
                                                    <CheckCircle className="w-3.5 h-3.5" /> Yes
                                                </span>
                                            ) : (
                                                <span className="text-muted-foreground text-xs">No</span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-1">
                                                <Link
                                                    to={`/runs/${run.id}`}
                                                    className="p-1.5 rounded-md text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                                                    title="View Details"
                                                >
                                                    <Eye className="w-4 h-4" />
                                                </Link>
                                                {!run.is_archived && ['completed', 'failed', 'cancelled'].includes(run.status) && (
                                                    <>
                                                        <button
                                                            onClick={() => archiveMutation.mutate(run.id)}
                                                            disabled={archiveMutation.isPending}
                                                            className="p-1.5 rounded-md text-muted-foreground hover:text-amber-400 hover:bg-amber-500/10 transition-colors"
                                                            title="Archive (preserve permanently)"
                                                        >
                                                            <Archive className="w-4 h-4" />
                                                        </button>
                                                        <button
                                                            onClick={() => setDeleteConfirmId(run.id)}
                                                            disabled={deleteMutation.isPending}
                                                            className="p-1.5 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                                                            title="Delete permanently"
                                                        >
                                                            <Trash2 className="w-4 h-4" />
                                                        </button>
                                                    </>
                                                )}
                                                {run.is_archived && (
                                                    <button
                                                        onClick={() => unarchiveMutation.mutate(run.id)}
                                                        disabled={unarchiveMutation.isPending}
                                                        className="p-1.5 rounded-md text-muted-foreground hover:text-amber-400 hover:bg-amber-500/10 transition-colors"
                                                        title="Unarchive"
                                                    >
                                                        <ArchiveRestore className="w-4 h-4" />
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                                {(!runs || runs.length === 0) && (
                                    <tr>
                                        <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                                            No runs found.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>

                    {/* Pagination */}
                    <div className="flex items-center justify-between px-4 py-3 border-t border-border">
                        <span className="text-sm text-muted-foreground">
                            Showing {page * pageSize + 1}–{page * pageSize + (runs?.length || 0)}
                        </span>
                        <div className="flex gap-2">
                            <button
                                onClick={() => setPage(p => Math.max(0, p - 1))}
                                disabled={page === 0}
                                className="p-1.5 rounded-md border border-border hover:bg-accent disabled:opacity-30 transition-colors"
                            >
                                <ChevronLeft className="w-4 h-4" />
                            </button>
                            <button
                                onClick={() => setPage(p => p + 1)}
                                disabled={!runs || runs.length < pageSize}
                                className="p-1.5 rounded-md border border-border hover:bg-accent disabled:opacity-30 transition-colors"
                            >
                                <ChevronRight className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

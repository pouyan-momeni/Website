import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useAuthStore } from '../stores/auth';
import { formatDate, formatDuration, statusColor, statusBg } from '../lib/utils';
import {
    Loader2, Archive, ArchiveRestore, Terminal, FileText, Settings, Download,
    Trash2, ArrowLeft, Ban, FileSpreadsheet, BarChart3, FileJson, Eye, X, Cpu,
} from 'lucide-react';

/** Fetches an image via the authenticated API and renders it using a blob URL */
function AuthImage({ src, alt, className, onClick }: { src: string; alt: string; className?: string; onClick?: () => void }) {
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const { accessToken } = useAuthStore();

    useEffect(() => {
        let cancelled = false;
        const fetchImage = async () => {
            try {
                const resp = await fetch(src, {
                    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
                });
                if (!resp.ok) return;
                const blob = await resp.blob();
                if (!cancelled) setBlobUrl(URL.createObjectURL(blob));
            } catch (_e) { /* ignore */ }
        };
        fetchImage();
        return () => { cancelled = true; };
    }, [src, accessToken]);

    if (!blobUrl) return <div className={`flex items-center justify-center bg-muted/30 rounded ${className || ''}`} style={{ minHeight: 120 }}><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>;
    return <img src={blobUrl} alt={alt} className={className} onClick={onClick} />;
}

export default function RunDetailPage() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { user, accessToken } = useAuthStore();
    const [logs, setLogs] = useState<string[]>([]);
    const [activeTab, setActiveTab] = useState<'logs' | 'inputs' | 'config' | 'outputs' | 'resources'>('logs');
    const [viewingChart, setViewingChart] = useState<string | null>(null);
    const logRef = useRef<HTMLDivElement>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const [logTotal, setLogTotal] = useState(0);
    const [logOffset, setLogOffset] = useState(0);
    const [hasMoreLogs, setHasMoreLogs] = useState(false);
    const [loadingMoreLogs, setLoadingMoreLogs] = useState(false);
    const LOG_PAGE_SIZE = 200;

    const { data: run, isLoading } = useQuery({
        queryKey: ['run', id],
        queryFn: () => api.getRun(id!),
        enabled: !!id,
        refetchInterval: (data) => {
            const r = data as any;
            return r?.status === 'running' || r?.status === 'queued' ? 2000 : false;
        },
    });

    const { data: outputData } = useQuery({
        queryKey: ['run-outputs', id],
        queryFn: () => api.getRunOutputs(id!),
        enabled: !!id && activeTab === 'outputs',
    });

    const archiveMutation = useMutation({
        mutationFn: () => api.archiveRun(id!),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['run', id] });
            queryClient.invalidateQueries({ queryKey: ['runs'] });
        },
    });

    const unarchiveMutation = useMutation({
        mutationFn: () => api.unarchiveRun(id!),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['run', id] });
            queryClient.invalidateQueries({ queryKey: ['runs'] });
        },
    });

    const deleteMutation = useMutation({
        mutationFn: () => api.deleteRun(id!),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['runs'] });
            navigate('/history');
        },
    });

    const cancelMutation = useMutation({
        mutationFn: () => api.cancelRun(id!),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['run', id] }),
    });

    // Initial log fetch — loads the first page
    useEffect(() => {
        if (!id) return;
        api.getRunLogs(id, 0, LOG_PAGE_SIZE).then(data => {
            if (data.logs?.length > 0) setLogs(data.logs);
            setLogTotal(data.total ?? data.logs?.length ?? 0);
            setLogOffset(data.logs?.length ?? 0);
            setHasMoreLogs(data.has_more ?? false);
            // Auto-scroll to bottom on first load
            setTimeout(() => {
                if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
            }, 100);
        }).catch(() => { });
    }, [id, run?.status]);

    // Load earlier logs on demand
    const loadMoreLogs = async () => {
        if (!id || loadingMoreLogs || !hasMoreLogs) return;
        setLoadingMoreLogs(true);
        try {
            const data = await api.getRunLogs(id, logOffset, LOG_PAGE_SIZE);
            if (data.logs?.length > 0) {
                const prevScrollHeight = logRef.current?.scrollHeight ?? 0;
                setLogs(prev => [...prev, ...data.logs]);
                setLogOffset(prev => prev + data.logs.length);
                setHasMoreLogs(data.has_more ?? false);
                setLogTotal(data.total ?? 0);
                // Maintain scroll position after prepending
                setTimeout(() => {
                    if (logRef.current) {
                        const newScrollHeight = logRef.current.scrollHeight;
                        logRef.current.scrollTop += newScrollHeight - prevScrollHeight;
                    }
                }, 50);
            } else {
                setHasMoreLogs(false);
            }
        } catch (_e) { /* ignore */ }
        setLoadingMoreLogs(false);
    };

    // WebSocket for live logs (running/queued runs only)
    useEffect(() => {
        if (!id || !run || (run.status !== 'running' && run.status !== 'queued')) return;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${protocol}//${window.location.host}/ws/runs/${id}/logs`);
        wsRef.current = ws;
        ws.onmessage = (event) => {
            setLogs(prev => {
                if (prev.length > 0 && prev[prev.length - 1] === event.data) return prev;
                return [...prev, event.data];
            });
            setTimeout(() => {
                if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
            }, 50);
        };
        ws.onerror = () => { };
        ws.onclose = () => { };
        return () => { ws.close(); wsRef.current = null; };
    }, [id, run?.status]);

    if (isLoading) return <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
    if (!run) return <div className="text-center py-20 text-muted-foreground">Run not found</div>;

    const canArchive = user && ['admin', 'developer', 'runner'].includes(user.role) &&
        !run.is_archived && ['completed', 'failed', 'cancelled'].includes(run.status);
    const canUnarchive = user && ['admin', 'developer', 'runner'].includes(user.role) && run.is_archived;
    const canDelete = user && ['admin', 'developer', 'runner'].includes(user.role) &&
        ['completed', 'failed', 'cancelled'].includes(run.status);
    const canCancel = user && ['admin', 'developer', 'runner'].includes(user.role) &&
        ['running', 'queued'].includes(run.status);

    const fileIcon = (type: string, ext: string) => {
        if (type === 'chart') return <BarChart3 className="w-4 h-4 text-purple-400" />;
        if (ext === '.json') return <FileJson className="w-4 h-4 text-amber-400" />;
        return <FileSpreadsheet className="w-4 h-4 text-emerald-400" />;
    };

    const formatSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const authDownload = async (url: string, filename: string) => {
        try {
            const resp = await fetch(url, {
                headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
            });
            if (!resp.ok) return;
            const blob = await resp.blob();
            const blobUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(blobUrl);
        } catch (_e) { /* ignore */ }
    };

    return (
        <div className="max-w-4xl mx-auto animate-fade-in">
            {/* Chart viewer modal */}
            {viewingChart && (
                <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-8" onClick={() => setViewingChart(null)}>
                    <div className="bg-card border border-border rounded-xl max-w-4xl w-full max-h-[85vh] overflow-auto p-4" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between mb-3">
                            <span className="font-medium text-sm">{viewingChart}</span>
                            <button onClick={() => setViewingChart(null)} className="p-1 hover:bg-accent rounded-md"><X className="w-4 h-4" /></button>
                        </div>
                        <AuthImage
                            src={api.getRunOutputUrl(id!, viewingChart)}
                            alt={viewingChart}
                            className="w-full rounded-lg"
                        />
                    </div>
                </div>
            )}

            <button onClick={() => navigate('/history')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors">
                <ArrowLeft className="w-4 h-4" /> Back to History
            </button>

            {/* Header */}
            <div className="flex items-start justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-bold mb-1">Run Details</h1>
                    <p className="text-sm text-muted-foreground font-mono">{run.id}</p>
                </div>
                <div className="flex items-center gap-2 flex-wrap justify-end">
                    <span className={`text-sm font-medium px-3 py-1.5 rounded-full border ${statusBg(run.status)} ${statusColor(run.status)}`}>
                        {run.status === 'running' && <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400 mr-1.5 animate-pulse" />}
                        {run.status}
                    </span>
                    {canCancel && (
                        <button onClick={() => cancelMutation.mutate()} disabled={cancelMutation.isPending}
                            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-red-500/20 text-sm text-red-400 hover:bg-red-500/10 transition-colors">
                            <Ban className="w-4 h-4" /> Cancel
                        </button>
                    )}
                    {canArchive && (
                        <button onClick={() => archiveMutation.mutate()} disabled={archiveMutation.isPending}
                            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border text-sm hover:bg-accent transition-colors">
                            <Archive className="w-4 h-4" /> Archive
                        </button>
                    )}
                    {canUnarchive && (
                        <button onClick={() => unarchiveMutation.mutate()} disabled={unarchiveMutation.isPending}
                            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-amber-500/20 text-sm text-amber-400 hover:bg-amber-500/10 transition-colors">
                            <ArchiveRestore className="w-4 h-4" /> Unarchive
                        </button>
                    )}
                    {canDelete && !run.is_archived && (
                        <button onClick={() => { if (confirm('Delete permanently?')) deleteMutation.mutate(); }}
                            disabled={deleteMutation.isPending}
                            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-red-500/20 text-sm text-red-400 hover:bg-red-500/10 transition-colors">
                            <Trash2 className="w-4 h-4" /> Delete
                        </button>
                    )}
                </div>
            </div>

            {/* Summary cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                {[
                    { label: 'Started', value: formatDate(run.started_at) },
                    { label: 'Duration', value: formatDuration(run.started_at, run.completed_at) },
                    { label: 'Step', value: `${(run.current_container_index ?? 0) + 1}/3` },
                    { label: 'Archived', value: run.is_archived ? '✓ Yes' : '✗ No' },
                ].map(({ label, value }) => (
                    <div key={label} className="bg-card border border-border rounded-lg p-3">
                        <p className="text-xs text-muted-foreground">{label}</p>
                        <p className="text-sm font-medium mt-0.5">{value}</p>
                    </div>
                ))}
            </div>

            {/* Archive/warning banners */}
            {run.is_archived && (
                <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-3 mb-6 text-sm flex items-center justify-between">
                    <div>
                        <span className="text-emerald-400 font-medium">✓ Archived</span>
                        <span className="text-muted-foreground ml-2">
                            {run.archived_at && `at ${formatDate(run.archived_at)}`}
                        </span>
                    </div>
                    {canUnarchive && (
                        <button onClick={() => unarchiveMutation.mutate()} className="text-xs text-amber-400 hover:text-amber-300 underline">
                            Unarchive
                        </button>
                    )}
                </div>
            )}
            {!run.is_archived && ['completed', 'failed', 'cancelled'].includes(run.status) && (
                <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 mb-6 text-sm">
                    <span className="text-amber-400 font-medium">⚠ Not archived</span>
                    <span className="text-muted-foreground ml-2">This run will be automatically deleted after 7 days. Archive it to preserve it permanently.</span>
                </div>
            )}

            {/* Tabs */}
            <div className="flex gap-1 mb-4 bg-card border border-border rounded-lg p-1">
                {[
                    { key: 'logs', label: 'Logs', icon: Terminal },
                    { key: 'inputs', label: 'Inputs', icon: FileText },
                    { key: 'config', label: 'Config', icon: Settings },
                    { key: 'outputs', label: 'Outputs', icon: Download },
                    { key: 'resources', label: 'Resources', icon: Cpu },
                ].map(({ key, label, icon: Icon }) => (
                    <button key={key} onClick={() => setActiveTab(key as any)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm transition-all ${activeTab === key ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground'}`}>
                        <Icon className="w-4 h-4" />{label}
                        {key === 'outputs' && outputData?.files && outputData.files.length > 0 && (
                            <span className="text-[10px] bg-primary/20 text-primary px-1.5 py-0.5 rounded-full">{outputData.files.length}</span>
                        )}
                    </button>
                ))}
            </div>

            {/* Tab content */}
            <div className="bg-card border border-border rounded-xl overflow-hidden">
                {activeTab === 'logs' && (
                    <div>
                        {logTotal > 0 && (
                            <div className="flex items-center justify-between px-4 pt-3 pb-1">
                                <span className="text-xs text-muted-foreground">
                                    Showing {logs.length} of {logTotal} log lines
                                </span>
                                {hasMoreLogs && (
                                    <button
                                        onClick={loadMoreLogs}
                                        disabled={loadingMoreLogs}
                                        className="text-xs text-primary hover:text-primary/80 font-medium px-2 py-1 rounded-md border border-primary/20 hover:bg-primary/10 transition-colors disabled:opacity-50"
                                    >
                                        {loadingMoreLogs ? 'Loading...' : `Load more (+${Math.min(LOG_PAGE_SIZE, logTotal - logs.length)})`}
                                    </button>
                                )}
                            </div>
                        )}
                        <div ref={logRef} className="log-viewer p-4 max-h-[500px] overflow-y-auto">
                            {logs.length > 0 ? logs.map((line, i) => (
                                <div key={i} className={`py-0.5 font-mono text-xs ${line.includes('[system]') ? 'text-blue-400' :
                                    line.toLowerCase().includes('error') ? 'text-red-400' :
                                        line.includes('Progress:') ? 'text-emerald-400' : 'text-muted-foreground'}`}>
                                    {line}
                                </div>
                            )) : (
                                <p className="text-muted-foreground text-sm">
                                    {run.status === 'running' || run.status === 'queued' ? 'Waiting for logs...' : 'No logs available.'}
                                </p>
                            )}
                        </div>
                    </div>
                )}

                {activeTab === 'inputs' && (
                    <div className="p-4">
                        {run.inputs && Object.keys(run.inputs).length > 0 ? (
                            <div className="space-y-2">
                                {Object.entries(run.inputs).map(([key, val]) => (
                                    <div key={key} className="flex gap-4 py-2 border-b border-border/50">
                                        <span className="text-sm font-medium min-w-[150px] text-primary">{key}</span>
                                        <span className="text-sm text-muted-foreground">{String(val)}</span>
                                    </div>
                                ))}
                            </div>
                        ) : <p className="text-sm text-muted-foreground">No inputs recorded.</p>}
                    </div>
                )}

                {activeTab === 'config' && (
                    <div className="p-4">
                        {run.config_snapshot && Object.keys(run.config_snapshot).length > 0 ? (
                            <div className="space-y-2">
                                {Object.entries(run.config_snapshot).map(([key, val]) => (
                                    <div key={key} className="flex gap-4 py-2 border-b border-border/50">
                                        <span className="text-sm font-medium min-w-[150px] text-primary">{key}</span>
                                        <span className="text-sm text-muted-foreground font-mono">
                                            {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        ) : <p className="text-sm text-muted-foreground">No configuration snapshot.</p>}
                    </div>
                )}

                {activeTab === 'outputs' && (
                    <div className="p-4">
                        {run.output_path && (
                            <p className="text-xs text-muted-foreground mb-4">
                                Output directory: <code className="text-primary/70 bg-primary/5 px-1.5 py-0.5 rounded">{run.output_path}</code>
                            </p>
                        )}

                        {/* Charts section */}
                        {outputData?.files?.filter(f => f.type === 'chart').length ? (
                            <div className="mb-6">
                                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                                    <BarChart3 className="w-4 h-4 text-purple-400" /> Charts & Visualizations
                                </h3>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                    {outputData.files.filter(f => f.type === 'chart').map(file => (
                                        <div key={file.name} className="border border-border rounded-lg overflow-hidden bg-background">
                                            <AuthImage
                                                src={api.getRunOutputUrl(id!, file.name)}
                                                alt={file.name}
                                                className="w-full cursor-pointer hover:opacity-90 transition-opacity"
                                                onClick={() => setViewingChart(file.name)}
                                            />
                                            <div className="flex items-center justify-between px-3 py-2 border-t border-border">
                                                <span className="text-xs text-muted-foreground">{file.name}</span>
                                                <div className="flex gap-1">
                                                    <button onClick={() => setViewingChart(file.name)}
                                                        className="p-1 rounded text-muted-foreground hover:text-primary hover:bg-primary/10" title="View full size">
                                                        <Eye className="w-3.5 h-3.5" />
                                                    </button>
                                                    <button onClick={() => authDownload(api.getRunOutputUrl(id!, file.name), file.name)}
                                                        className="p-1 rounded text-muted-foreground hover:text-primary hover:bg-primary/10" title="Download">
                                                        <Download className="w-3.5 h-3.5" />
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ) : null}

                        {/* Data files section */}
                        {outputData?.files?.filter(f => f.type !== 'chart').length ? (
                            <div>
                                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                                    <FileSpreadsheet className="w-4 h-4 text-emerald-400" /> Data Files
                                </h3>
                                <div className="space-y-1">
                                    {outputData.files.filter(f => f.type !== 'chart').map(file => (
                                        <div key={file.name} className="flex items-center justify-between px-3 py-2.5 rounded-lg border border-border/50 hover:bg-accent/30 transition-colors">
                                            <div className="flex items-center gap-3">
                                                {fileIcon(file.type, file.extension)}
                                                <div>
                                                    <span className="text-sm font-medium">{file.name}</span>
                                                    <span className="text-xs text-muted-foreground ml-2">{formatSize(file.size)}</span>
                                                </div>
                                            </div>
                                            <button onClick={() => authDownload(api.getRunOutputUrl(id!, file.name), file.name)}
                                                className="flex items-center gap-1.5 px-3 py-1 rounded-md text-xs text-primary hover:bg-primary/10 transition-colors">
                                                <Download className="w-3.5 h-3.5" /> Download
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ) : null}

                        {(!outputData?.files || outputData.files.length === 0) && (
                            <p className="text-sm text-muted-foreground py-4 text-center">
                                {run.status === 'completed' ? 'No output files found.' : 'Output files will appear here after the run completes.'}
                            </p>
                        )}
                    </div>
                )}

                {activeTab === 'resources' && (
                    <div className="p-4">
                        <h3 className="text-sm font-medium mb-3">Container Resource Usage</h3>
                        {run.container_stats && Object.keys(run.container_stats).length > 0 ? (
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b border-border text-muted-foreground text-left">
                                            <th className="pb-2 pr-4 font-medium">Container</th>
                                            <th className="pb-2 pr-4 font-medium">Image</th>
                                            <th className="pb-2 pr-4 font-medium text-right">Peak CPU%</th>
                                            <th className="pb-2 pr-4 font-medium text-right">Peak Memory</th>
                                            <th className="pb-2 pr-4 font-medium text-right">Disk</th>
                                            <th className="pb-2 font-medium text-right">Duration</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {Object.entries(run.container_stats as Record<string, any>).map(([name, stats]) => (
                                            <tr key={name} className="border-b border-border/50">
                                                <td className="py-2 pr-4 font-medium">{name}</td>
                                                <td className="py-2 pr-4 text-muted-foreground text-xs font-mono">{stats.image || '—'}</td>
                                                <td className="py-2 pr-4 text-right">
                                                    <span className="inline-flex items-center gap-1">
                                                        <Cpu className="w-3 h-3 text-primary/60" />
                                                        {stats.max_cpu_percent?.toFixed(1) ?? '—'}%
                                                    </span>
                                                </td>
                                                <td className="py-2 pr-4 text-right">
                                                    {stats.max_memory_mb != null
                                                        ? stats.max_memory_mb >= 1024
                                                            ? `${(stats.max_memory_mb / 1024).toFixed(1)} GB`
                                                            : `${stats.max_memory_mb.toFixed(0)} MB`
                                                        : '—'}
                                                </td>
                                                <td className="py-2 pr-4 text-right">
                                                    {stats.max_disk_mb != null
                                                        ? stats.max_disk_mb >= 1024
                                                            ? `${(stats.max_disk_mb / 1024).toFixed(1)} GB`
                                                            : `${stats.max_disk_mb.toFixed(0)} MB`
                                                        : '—'}
                                                </td>
                                                <td className="py-2 text-right">
                                                    {stats.duration_seconds != null
                                                        ? stats.duration_seconds >= 60
                                                            ? `${(stats.duration_seconds / 60).toFixed(1)} min`
                                                            : `${stats.duration_seconds.toFixed(1)} s`
                                                        : '—'}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <p className="text-sm text-muted-foreground py-4 text-center">
                                {run.status === 'completed' || run.status === 'failed'
                                    ? 'No resource usage data available for this run.'
                                    : 'Resource stats will appear here after the run completes.'}
                            </p>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

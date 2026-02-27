import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import {
    Loader2, Plus, Play, Pause, Square, Trash2, Code, Search,
    ArrowLeft, ExternalLink, User, Calendar, X,
} from 'lucide-react';
import type { Notebook } from '../types';

export default function NotebooksPage() {
    const queryClient = useQueryClient();
    const [search, setSearch] = useState('');
    const [showCreate, setShowCreate] = useState(false);
    const [newName, setNewName] = useState('');
    const [newDesc, setNewDesc] = useState('');
    const [openNotebook, setOpenNotebook] = useState<Notebook | null>(null);
    const iframeRef = useRef<HTMLIFrameElement>(null);

    const { data: notebooks, isLoading } = useQuery({
        queryKey: ['notebooks'],
        queryFn: () => api.getNotebooks(),
        refetchInterval: 5000,
    });

    const createMutation = useMutation({
        mutationFn: () => api.createNotebook(newName.trim()),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['notebooks'] });
            setNewName('');
            setNewDesc('');
            setShowCreate(false);
        },
    });

    const startMutation = useMutation({
        mutationFn: (id: string) => api.startNotebook(id),
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['notebooks'] });
            // Auto-open notebook when started
            setOpenNotebook(data as Notebook);
        },
    });

    const stopMutation = useMutation({
        mutationFn: (id: string) => api.stopNotebook(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['notebooks'] });
            if (openNotebook) setOpenNotebook(null);
        },
    });

    const pauseMutation = useMutation({
        mutationFn: (id: string) => api.pauseNotebook(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notebooks'] }),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: string) => api.deleteNotebook(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notebooks'] }),
    });

    // Keep open notebook in sync with API state
    useEffect(() => {
        if (openNotebook && notebooks) {
            const updated = notebooks.find(nb => nb.id === openNotebook.id);
            if (updated) setOpenNotebook(updated);
        }
    }, [notebooks]);

    const filtered = (notebooks || []).filter(nb =>
        nb.name.toLowerCase().includes(search.toLowerCase()) ||
        (nb.description || '').toLowerCase().includes(search.toLowerCase()) ||
        nb.owner_username.toLowerCase().includes(search.toLowerCase())
    );

    const statusColor = (status: string) => {
        switch (status) {
            case 'running': return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
            case 'paused': return 'text-amber-400 bg-amber-500/10 border-amber-500/20';
            default: return 'text-muted-foreground bg-muted border-border';
        }
    };

    const formatDate = (d: string) => new Date(d).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
    });

    // ───── Open Notebook View (full iframe) ─────
    if (openNotebook) {
        return (
            <div className="animate-fade-in flex flex-col h-[calc(100vh-48px)]">
                {/* Header bar */}
                <div className="flex items-center justify-between bg-card border-b border-border px-4 py-2 flex-shrink-0">
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => setOpenNotebook(null)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                        >
                            <ArrowLeft className="w-4 h-4" /> Back
                        </button>
                        <div className="h-5 w-px bg-border" />
                        <Code className="w-4 h-4 text-primary" />
                        <span className="font-semibold text-sm">{openNotebook.name}</span>
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${statusColor(openNotebook.status)}`}>
                            {openNotebook.status === 'running' && <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1 animate-pulse" />}
                            {openNotebook.status}
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        {openNotebook.status === 'stopped' && (
                            <button
                                onClick={() => startMutation.mutate(openNotebook.id)}
                                disabled={startMutation.isPending}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                            >
                                <Play className="w-3.5 h-3.5" /> Start
                            </button>
                        )}
                        {openNotebook.status === 'running' && (
                            <>
                                <button
                                    onClick={() => pauseMutation.mutate(openNotebook.id)}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-amber-400 hover:bg-amber-500/10 transition-colors"
                                >
                                    <Pause className="w-3.5 h-3.5" /> Pause
                                </button>
                                <button
                                    onClick={() => stopMutation.mutate(openNotebook.id)}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-red-400 hover:bg-red-500/10 transition-colors"
                                >
                                    <Square className="w-3.5 h-3.5" /> Stop
                                </button>
                                {openNotebook.url && (
                                    <a
                                        href={openNotebook.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                                    >
                                        <ExternalLink className="w-3.5 h-3.5" /> Open External
                                    </a>
                                )}
                            </>
                        )}
                        {openNotebook.status === 'paused' && (
                            <>
                                <button
                                    onClick={() => startMutation.mutate(openNotebook.id)}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                                >
                                    <Play className="w-3.5 h-3.5" /> Resume
                                </button>
                                <button
                                    onClick={() => stopMutation.mutate(openNotebook.id)}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-red-400 hover:bg-red-500/10 transition-colors"
                                >
                                    <Square className="w-3.5 h-3.5" /> Stop
                                </button>
                            </>
                        )}
                    </div>
                </div>

                {/* Iframe for the Marimo editor */}
                <div className="flex-1 bg-background">
                    {openNotebook.status === 'running' && openNotebook.url ? (
                        <iframe
                            ref={iframeRef}
                            src={openNotebook.url}
                            className="w-full h-full border-0"
                            title={`Marimo - ${openNotebook.name}`}
                        />
                    ) : openNotebook.status === 'running' ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="text-center">
                                <Loader2 className="w-10 h-10 animate-spin text-primary mx-auto mb-4" />
                                <p className="text-lg font-medium">Starting notebook...</p>
                                <p className="text-sm text-muted-foreground mt-1">The Marimo editor will load shortly</p>
                            </div>
                        </div>
                    ) : (
                        <div className="flex items-center justify-center h-full">
                            <div className="text-center max-w-md">
                                <Code className="w-16 h-16 text-muted-foreground mx-auto mb-4 opacity-50" />
                                <h2 className="text-xl font-semibold mb-2">Notebook is {openNotebook.status}</h2>
                                <p className="text-sm text-muted-foreground mb-6">
                                    {openNotebook.status === 'stopped'
                                        ? 'Start the notebook to launch the Marimo editor where you can write and run Python code interactively.'
                                        : 'Resume the notebook to continue working in the Marimo editor.'}
                                </p>
                                <button
                                    onClick={() => startMutation.mutate(openNotebook.id)}
                                    disabled={startMutation.isPending}
                                    className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-all"
                                >
                                    {startMutation.isPending ? (
                                        <><Loader2 className="w-4 h-4 animate-spin" /> Starting...</>
                                    ) : (
                                        <><Play className="w-4 h-4" /> {openNotebook.status === 'paused' ? 'Resume Notebook' : 'Start Notebook'}</>
                                    )}
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        );
    }

    // ───── Gallery View ─────
    if (isLoading) {
        return <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
    }

    return (
        <div className="animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-bold">Notebooks</h1>
                    <p className="text-sm text-muted-foreground mt-1">Interactive data exploration environments</p>
                </div>
                <button
                    onClick={() => setShowCreate(!showCreate)}
                    className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
                >
                    <Plus className="w-4 h-4" /> New Notebook
                </button>
            </div>

            {/* Search bar */}
            <div className="relative mb-6">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search notebooks by name, description, or owner..."
                    className="w-full pl-10 pr-10 py-2.5 bg-card border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                />
                {search && (
                    <button
                        onClick={() => setSearch('')}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                        <X className="w-4 h-4" />
                    </button>
                )}
            </div>

            {/* Create form */}
            {showCreate && (
                <div className="bg-card border border-border rounded-xl p-5 mb-6 animate-fade-in">
                    <h3 className="text-sm font-semibold mb-3">Create New Notebook</h3>
                    <div className="space-y-3">
                        <input
                            type="text"
                            value={newName}
                            onChange={(e) => setNewName(e.target.value)}
                            placeholder="Notebook name (e.g. Portfolio Analysis)"
                            className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                            autoFocus
                        />
                        <input
                            type="text"
                            value={newDesc}
                            onChange={(e) => setNewDesc(e.target.value)}
                            placeholder="Description (optional)"
                            className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && newName.trim()) createMutation.mutate();
                            }}
                        />
                        <div className="flex gap-2">
                            <button
                                onClick={() => newName.trim() && createMutation.mutate()}
                                disabled={!newName.trim() || createMutation.isPending}
                                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
                            >
                                {createMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Create'}
                            </button>
                            <button
                                onClick={() => { setShowCreate(false); setNewName(''); setNewDesc(''); }}
                                className="px-3 py-2 text-muted-foreground hover:text-foreground rounded-lg text-sm border border-border hover:bg-accent"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Gallery grid */}
            {filtered.length === 0 ? (
                <div className="bg-card border border-border rounded-xl p-12 text-center">
                    <Code className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                    <h2 className="text-lg font-semibold mb-2">
                        {search ? 'No notebooks match your search' : 'No Notebooks Yet'}
                    </h2>
                    <p className="text-sm text-muted-foreground">
                        {search ? 'Try a different search term.' : 'Create a notebook to start exploring data interactively.'}
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {filtered.map((nb: Notebook) => (
                        <div
                            key={nb.id}
                            onClick={() => setOpenNotebook(nb)}
                            className="bg-card border border-border rounded-xl p-5 cursor-pointer hover:border-primary/40 hover:shadow-lg hover:shadow-primary/5 transition-all group"
                        >
                            {/* Card header */}
                            <div className="flex items-start justify-between mb-3">
                                <div className="flex items-center gap-2.5 min-w-0">
                                    <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 group-hover:bg-primary/20 transition-colors">
                                        <Code className="w-4 h-4 text-primary" />
                                    </div>
                                    <div className="min-w-0">
                                        <h3 className="font-semibold text-sm truncate group-hover:text-primary transition-colors">
                                            {nb.name}
                                        </h3>
                                    </div>
                                </div>
                                <span className={`text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded-full border flex-shrink-0 ${statusColor(nb.status)}`}>
                                    {nb.status === 'running' && <span className="inline-block w-1 h-1 rounded-full bg-emerald-400 mr-1 animate-pulse" />}
                                    {nb.status}
                                </span>
                            </div>

                            {/* Description */}
                            {nb.description && (
                                <p className="text-xs text-muted-foreground mb-3 line-clamp-2">
                                    {nb.description}
                                </p>
                            )}

                            {/* Footer */}
                            <div className="flex items-center gap-3 text-xs text-muted-foreground pt-2 border-t border-border/50">
                                <span className="flex items-center gap-1">
                                    <User className="w-3 h-3" /> {nb.owner_username}
                                </span>
                                <span className="flex items-center gap-1">
                                    <Calendar className="w-3 h-3" /> {formatDate(nb.updated_at || nb.created_at)}
                                </span>
                            </div>

                            {/* Actions (stop propagation so card click doesn't fire) */}
                            <div className="flex items-center gap-1 mt-3 pt-2 border-t border-border/50" onClick={(e) => e.stopPropagation()}>
                                {nb.status === 'stopped' && (
                                    <button
                                        onClick={() => startMutation.mutate(nb.id)}
                                        disabled={startMutation.isPending}
                                        className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-emerald-400 hover:bg-emerald-500/10 transition-colors"
                                    >
                                        <Play className="w-3 h-3" /> Start
                                    </button>
                                )}
                                {nb.status === 'running' && (
                                    <>
                                        <button
                                            onClick={() => pauseMutation.mutate(nb.id)}
                                            className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-amber-400 hover:bg-amber-500/10 transition-colors"
                                        >
                                            <Pause className="w-3 h-3" /> Pause
                                        </button>
                                        <button
                                            onClick={() => stopMutation.mutate(nb.id)}
                                            className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-red-400 hover:bg-red-500/10 transition-colors"
                                        >
                                            <Square className="w-3 h-3" /> Stop
                                        </button>
                                    </>
                                )}
                                {nb.status === 'paused' && (
                                    <>
                                        <button
                                            onClick={() => startMutation.mutate(nb.id)}
                                            className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-emerald-400 hover:bg-emerald-500/10 transition-colors"
                                        >
                                            <Play className="w-3 h-3" /> Resume
                                        </button>
                                        <button
                                            onClick={() => stopMutation.mutate(nb.id)}
                                            className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-red-400 hover:bg-red-500/10 transition-colors"
                                        >
                                            <Square className="w-3 h-3" /> Stop
                                        </button>
                                    </>
                                )}
                                <div className="flex-1" />
                                {nb.status !== 'running' && (
                                    <button
                                        onClick={() => {
                                            if (confirm(`Delete "${nb.name}"?`)) deleteMutation.mutate(nb.id);
                                        }}
                                        className="p-1 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                                        title="Delete"
                                    >
                                        <Trash2 className="w-3 h-3" />
                                    </button>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

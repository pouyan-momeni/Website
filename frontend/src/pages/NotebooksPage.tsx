import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import {
    Loader2, Plus, Play, Pause, Square, Trash2, Code, Search,
    ArrowLeft, ExternalLink, User, Calendar, X, Copy, FolderOpen, Globe, Share2, XCircle,
} from 'lucide-react';
import type { Notebook } from '../types';
import { useAuthStore } from '../stores/auth';

export default function NotebooksPage() {
    const queryClient = useQueryClient();
    const [search, setSearch] = useState('');
    const [showCreate, setShowCreate] = useState(false);
    const [newName, setNewName] = useState('');
    const [newDesc, setNewDesc] = useState('');
    const [openNotebook, setOpenNotebook] = useState<Notebook | null>(null);
    const [activeTab, setActiveTab] = useState<'personal' | 'shared'>('personal');
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
    const iframeRef = useRef<HTMLIFrameElement>(null);
    const { user } = useAuthStore();
    const isAdmin = user?.role === 'admin';

    const { data: notebooks, isLoading } = useQuery({
        queryKey: ['notebooks'],
        queryFn: () => api.getNotebooks(),
        refetchInterval: 5000,
    });

    const { data: sharedNotebooks, isLoading: sharedLoading } = useQuery({
        queryKey: ['notebooks-shared'],
        queryFn: () => api.getSharedNotebooks(),
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

    const copyMutation = useMutation({
        mutationFn: (id: string) => api.copySharedNotebook(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['notebooks'] });
            setActiveTab('personal');
        },
    });

    const shareMutation = useMutation({
        mutationFn: (id: string) => api.shareNotebook(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['notebooks'] });
            queryClient.invalidateQueries({ queryKey: ['notebooks-shared'] });
        },
    });

    const unshareMutation = useMutation({
        mutationFn: (id: string) => api.unshareNotebook(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['notebooks'] });
            queryClient.invalidateQueries({ queryKey: ['notebooks-shared'] });
        },
    });

    const startMutation = useMutation({
        mutationFn: (id: string) => api.startNotebook(id),
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['notebooks'] });
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
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['notebooks'] });
            queryClient.invalidateQueries({ queryKey: ['notebooks-shared'] });
            setDeleteConfirmId(null);
        },
    });

    // Keep open notebook in sync with API state
    useEffect(() => {
        if (openNotebook && notebooks) {
            const updated = notebooks.find(nb => nb.id === openNotebook.id);
            if (updated) setOpenNotebook(updated);
        }
    }, [notebooks]);

    const currentList = activeTab === 'personal' ? (notebooks || []) : (sharedNotebooks || []);
    const filtered = currentList.filter(nb =>
        nb.name.toLowerCase().includes(search.toLowerCase()) ||
        (nb.description || '').toLowerCase().includes(search.toLowerCase()) ||
        nb.owner_username.toLowerCase().includes(search.toLowerCase())
    );

    // Build map: personalNotebookId → sharedNotebookId (for toggle logic)
    const sharedMap = new Map<string, string>();
    (sharedNotebooks || []).forEach(nb => {
        if (nb.shared_from) sharedMap.set(nb.shared_from, nb.id);
    });

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
                {activeTab === 'personal' && (
                    <button
                        onClick={() => setShowCreate(!showCreate)}
                        className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
                    >
                        <Plus className="w-4 h-4" /> New Notebook
                    </button>
                )}
            </div>

            {/* Tabs: My Notebooks / Shared Library */}
            <div className="flex gap-1 mb-6 bg-card border border-border rounded-xl p-1">
                <button
                    onClick={() => setActiveTab('personal')}
                    className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${activeTab === 'personal'
                        ? 'bg-primary text-primary-foreground shadow-sm'
                        : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                        }`}
                >
                    <FolderOpen className="w-4 h-4" />
                    My Notebooks
                    {notebooks && <span className="text-xs opacity-75">({notebooks.length})</span>}
                </button>
                <button
                    onClick={() => setActiveTab('shared')}
                    className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${activeTab === 'shared'
                        ? 'bg-primary text-primary-foreground shadow-sm'
                        : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                        }`}
                >
                    <Globe className="w-4 h-4" />
                    Shared Library
                    {sharedNotebooks && <span className="text-xs opacity-75">({sharedNotebooks.length})</span>}
                </button>
            </div>

            {/* Search bar */}
            <div className="relative mb-6">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={activeTab === 'personal' ? 'Search your notebooks...' : 'Search shared notebooks...'}
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

            {/* Create form (only on personal tab) */}
            {showCreate && activeTab === 'personal' && (
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

            {/* Delete Confirmation Modal */}
            {deleteConfirmId && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 animate-fade-in">
                    <div className="bg-card border border-border rounded-xl p-6 max-w-md mx-4 shadow-2xl">
                        <h3 className="font-semibold text-lg mb-2">Delete Notebook</h3>
                        <p className="text-sm text-muted-foreground mb-6">
                            Are you sure you want to delete this notebook? This action cannot be undone.
                        </p>
                        <div className="flex gap-3 justify-end">
                            <button onClick={() => setDeleteConfirmId(null)} className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent">Cancel</button>
                            <button
                                onClick={() => deleteMutation.mutate(deleteConfirmId)}
                                disabled={deleteMutation.isPending}
                                className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-500 disabled:opacity-50"
                            >
                                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Shared tab info banner */}
            {activeTab === 'shared' && (
                <div className="flex items-center gap-3 bg-blue-500/5 border border-blue-500/20 text-blue-300 rounded-xl px-4 py-3 mb-6 text-sm">
                    <Globe className="w-5 h-5 flex-shrink-0" />
                    <span>Shared notebooks are <strong>read-only</strong>. Click <strong>Copy to My Notebooks</strong> to create your own editable copy.</span>
                </div>
            )}

            {/* Gallery grid */}
            {(activeTab === 'shared' ? sharedLoading : false) ? (
                <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>
            ) : filtered.length === 0 ? (
                <div className="bg-card border border-border rounded-xl p-12 text-center">
                    <Code className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                    <h2 className="text-lg font-semibold mb-2">
                        {search ? 'No notebooks match your search' : activeTab === 'personal' ? 'No Notebooks Yet' : 'No Shared Notebooks'}
                    </h2>
                    <p className="text-sm text-muted-foreground">
                        {search ? 'Try a different search term.' : activeTab === 'personal' ? 'Create a notebook to start exploring data interactively.' : 'No shared notebooks are available yet.'}
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {filtered.map((nb: Notebook) => (
                        <div
                            key={nb.id}
                            onClick={() => activeTab === 'personal' ? setOpenNotebook(nb) : undefined}
                            className={`bg-card border border-border rounded-xl p-5 transition-all group ${activeTab === 'personal' ? 'cursor-pointer hover:border-primary/40 hover:shadow-lg hover:shadow-primary/5' : ''}`}
                        >
                            {/* Card header */}
                            <div className="flex items-start justify-between mb-3">
                                <div className="flex items-center gap-2.5 min-w-0">
                                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${activeTab === 'shared' ? 'bg-blue-500/10 group-hover:bg-blue-500/20' : 'bg-primary/10 group-hover:bg-primary/20'}`}>
                                        {activeTab === 'shared' ? <Globe className="w-4 h-4 text-blue-400" /> : <Code className="w-4 h-4 text-primary" />}
                                    </div>
                                    <div className="min-w-0">
                                        <h3 className={`font-semibold text-sm truncate transition-colors ${activeTab === 'personal' ? 'group-hover:text-primary' : ''}`}>
                                            {nb.name}
                                        </h3>
                                    </div>
                                </div>
                                {activeTab === 'personal' && (
                                    <span className={`text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded-full border flex-shrink-0 ${statusColor(nb.status)}`}>
                                        {nb.status === 'running' && <span className="inline-block w-1 h-1 rounded-full bg-emerald-400 mr-1 animate-pulse" />}
                                        {nb.status}
                                    </span>
                                )}
                                {activeTab === 'shared' && (
                                    <span className="text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded-full border text-blue-400 bg-blue-500/10 border-blue-500/20 flex-shrink-0">
                                        shared
                                    </span>
                                )}
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

                            {/* Actions */}
                            <div className="flex items-center gap-1 mt-3 pt-2 border-t border-border/50" onClick={(e) => e.stopPropagation()}>
                                {activeTab === 'personal' && (
                                    <>
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
                                            <>
                                                {sharedMap.has(nb.id) ? (
                                                    <button
                                                        onClick={() => unshareMutation.mutate(sharedMap.get(nb.id)!)}
                                                        disabled={unshareMutation.isPending}
                                                        className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-amber-400 hover:bg-amber-500/10 transition-colors disabled:opacity-50"
                                                        title="Remove from Shared Library"
                                                    >
                                                        <XCircle className="w-3 h-3" />
                                                        Unshare
                                                    </button>
                                                ) : (
                                                    <button
                                                        onClick={() => shareMutation.mutate(nb.id)}
                                                        disabled={shareMutation.isPending}
                                                        className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-blue-400 hover:bg-blue-500/10 transition-colors disabled:opacity-50"
                                                        title="Share to Shared Library"
                                                    >
                                                        <Share2 className="w-3 h-3" />
                                                        Share
                                                    </button>
                                                )}
                                                <button
                                                    onClick={() => setDeleteConfirmId(nb.id)}
                                                    className="p-1 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                                                    title="Delete"
                                                >
                                                    <Trash2 className="w-3 h-3" />
                                                </button>
                                            </>
                                        )}
                                    </>
                                )}
                                {activeTab === 'shared' && (
                                    <>
                                        <button
                                            onClick={() => copyMutation.mutate(nb.id)}
                                            disabled={copyMutation.isPending}
                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-primary bg-primary/10 hover:bg-primary/20 transition-colors disabled:opacity-50"
                                        >
                                            {copyMutation.isPending ? (
                                                <Loader2 className="w-3 h-3 animate-spin" />
                                            ) : (
                                                <Copy className="w-3 h-3" />
                                            )}
                                            Copy to My Notebooks
                                        </button>
                                        {nb.owner_id === user?.id && (
                                            <button
                                                onClick={() => unshareMutation.mutate(nb.id)}
                                                disabled={unshareMutation.isPending}
                                                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs text-amber-400 hover:bg-amber-500/10 transition-colors disabled:opacity-50"
                                                title="Remove from Shared Library"
                                            >
                                                <XCircle className="w-3 h-3" />
                                                Unshare
                                            </button>
                                        )}
                                        <div className="flex-1" />
                                        {isAdmin && (
                                            <button
                                                onClick={() => setDeleteConfirmId(nb.id)}
                                                className="p-1 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                                                title="Delete from Shared Library (Admin)"
                                            >
                                                <Trash2 className="w-3 h-3" />
                                            </button>
                                        )}
                                    </>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

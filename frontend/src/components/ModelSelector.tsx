import { useState, useRef, useEffect } from 'react';
import { Search, ChevronDown, FolderOpen, Cpu, HardDrive, Clock, Database } from 'lucide-react';
import type { Model } from '../types';

interface ModelSelectorProps {
    models: Model[];
    selectedId: string;
    onChange: (id: string) => void;
    label?: string;
}

function ResourceBadges({ model }: { model: Model }) {
    const r = model.avg_resources;
    if (!r || r.sample_count === 0) return null;
    return (
        <span className="flex items-center gap-2 mt-0.5">
            <span className="inline-flex items-center gap-0.5 text-[9px] text-muted-foreground/70">
                <Cpu className="w-2.5 h-2.5" />{r.avg_cpu_percent.toFixed(0)}%
            </span>
            <span className="inline-flex items-center gap-0.5 text-[9px] text-muted-foreground/70">
                <HardDrive className="w-2.5 h-2.5" />{r.avg_memory_mb >= 1024 ? `${(r.avg_memory_mb / 1024).toFixed(1)}GB` : `${r.avg_memory_mb.toFixed(0)}MB`}
            </span>
            {r.avg_disk_mb > 0 && (
                <span className="inline-flex items-center gap-0.5 text-[9px] text-muted-foreground/70">
                    <Database className="w-2.5 h-2.5" />{r.avg_disk_mb >= 1024 ? `${(r.avg_disk_mb / 1024).toFixed(1)}GB` : `${r.avg_disk_mb.toFixed(0)}MB`}
                </span>
            )}
            <span className="inline-flex items-center gap-0.5 text-[9px] text-muted-foreground/70">
                <Clock className="w-2.5 h-2.5" />{r.avg_duration_seconds >= 60 ? `${(r.avg_duration_seconds / 60).toFixed(1)}m` : `${r.avg_duration_seconds.toFixed(0)}s`}
            </span>
        </span>
    );
}

export default function ModelSelector({ models, selectedId, onChange, label = 'Select Model' }: ModelSelectorProps) {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
    const containerRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    const selectedModel = models.find(m => m.id === selectedId);

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false);
                setSearch('');
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    useEffect(() => {
        if (open && inputRef.current) inputRef.current.focus();
    }, [open]);

    const filtered = search.trim()
        ? models.filter(m => m.name.toLowerCase().includes(search.toLowerCase()))
        : models;

    const categories = new Map<string, Model[]>();
    const uncategorized: Model[] = [];
    for (const m of filtered) {
        if (m.category) {
            if (!categories.has(m.category)) categories.set(m.category, []);
            categories.get(m.category)!.push(m);
        } else {
            uncategorized.push(m);
        }
    }
    const sortedCategories = Array.from(categories.entries()).sort((a, b) => a[0].localeCompare(b[0]));

    const handleSelect = (id: string) => {
        onChange(id);
        setOpen(false);
        setSearch('');
    };

    const renderModelItem = (m: Model, indent: boolean) => (
        <button
            key={m.id}
            onClick={() => handleSelect(m.id)}
            className={`w-full text-left px-3 py-2 ${indent ? 'pl-7' : 'pl-3'} text-sm transition-colors ${m.id === selectedId
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'hover:bg-accent text-foreground'
                }`}
        >
            <div className="flex items-center justify-between">
                <span>{m.name}</span>
            </div>
            <ResourceBadges model={m} />
        </button>
    );

    return (
        <div ref={containerRef} className="relative">
            <label className="block text-sm font-medium mb-1.5">{label}</label>
            <button
                onClick={() => setOpen(!open)}
                className="w-full flex items-center justify-between px-3 py-2.5 bg-card border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-colors hover:border-primary/30"
            >
                <span className={selectedModel ? 'text-foreground' : 'text-muted-foreground'}>
                    {selectedModel ? (
                        <span className="flex items-center gap-2">
                            {selectedModel.name}
                            {selectedModel.category && (
                                <span className="text-[10px] bg-primary/15 text-primary/70 px-1.5 py-0.5 rounded-full">{selectedModel.category}</span>
                            )}
                        </span>
                    ) : 'Select a model...'}
                </span>
                <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>

            {open && (
                <div className="absolute z-50 mt-1 w-full bg-card border border-border rounded-lg shadow-xl overflow-hidden animate-fade-in">
                    <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
                        <Search className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                        <input
                            ref={inputRef}
                            type="text"
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            placeholder="Search models..."
                            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
                        />
                    </div>

                    <div className="max-h-[300px] overflow-y-auto">
                        {filtered.length === 0 ? (
                            <div className="px-3 py-4 text-sm text-muted-foreground text-center">No models found</div>
                        ) : (
                            <>
                                {sortedCategories.map(([category, catModels]) => (
                                    <div key={category}>
                                        <div className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold bg-muted/30 sticky top-0">
                                            <FolderOpen className="w-3 h-3" />
                                            {category}
                                        </div>
                                        {catModels.map(m => renderModelItem(m, true))}
                                    </div>
                                ))}
                                {uncategorized.length > 0 && sortedCategories.length > 0 && (
                                    <div className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold bg-muted/30 sticky top-0">
                                        <FolderOpen className="w-3 h-3" />
                                        Uncategorized
                                    </div>
                                )}
                                {uncategorized.map(m => renderModelItem(m, sortedCategories.length > 0))}
                            </>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { Loader2, Code, ExternalLink } from 'lucide-react';

export default function MarimoPage() {
    const [launched, setLaunched] = useState(false);

    const { data: status } = useQuery({
        queryKey: ['marimo-status'],
        queryFn: () => api.getMarimoStatus(),
        refetchInterval: launched ? 5000 : false,
    });

    const launchMutation = useMutation({
        mutationFn: () => api.launchMarimo(),
        onSuccess: () => setLaunched(true),
    });

    const marimoUrl = status?.url;
    const isRunning = status?.running;

    return (
        <div className="max-w-3xl mx-auto animate-fade-in">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-bold">Marimo Notebook</h1>
                    <p className="text-sm text-muted-foreground mt-1">Interactive data exploration environment</p>
                </div>
                {!isRunning && (
                    <button
                        onClick={() => launchMutation.mutate()}
                        disabled={launchMutation.isPending}
                        className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
                    >
                        {launchMutation.isPending ? (
                            <><Loader2 className="w-4 h-4 animate-spin" /> Launching...</>
                        ) : (
                            <><Code className="w-4 h-4" /> Launch Notebook</>
                        )}
                    </button>
                )}
            </div>

            {launchMutation.isError && (
                <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-sm text-red-400 mb-6">
                    {(launchMutation.error as Error).message}
                </div>
            )}

            {isRunning && marimoUrl ? (
                <div className="bg-card border border-border rounded-xl overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-muted/50">
                        <span className="text-sm text-muted-foreground">Marimo — Port {status.port}</span>
                        <div className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                            <span className="text-xs text-emerald-400">Running</span>
                            <a
                                href={marimoUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="p-1 rounded text-muted-foreground hover:text-foreground"
                            >
                                <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                        </div>
                    </div>
                    <iframe
                        src={marimoUrl}
                        className="w-full border-0"
                        style={{ height: 'calc(100vh - 220px)' }}
                        title="Marimo Notebook"
                    />
                </div>
            ) : !isRunning && !launchMutation.isPending ? (
                <div className="bg-card border border-border rounded-xl p-12 text-center">
                    <Code className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                    <h2 className="text-lg font-semibold mb-2">No Notebook Running</h2>
                    <p className="text-sm text-muted-foreground">
                        Launch a Marimo notebook to explore financial data interactively.
                        Each developer gets their own isolated instance.
                    </p>
                </div>
            ) : null}
        </div>
    );
}

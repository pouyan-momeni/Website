import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../api/client';
import { Loader2, Cpu, HardDrive, MemoryStick, Skull } from 'lucide-react';
import { useState, useEffect } from 'react';
import type { ResourceSnapshot } from '../types';

function GaugeCard({ label, value, total, unit, color, icon: Icon }: {
    label: string; value: number; total: number; unit: string; color: string;
    icon: React.ElementType;
}) {
    const pct = Math.min(value, 100);
    return (
        <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center gap-2 mb-3">
                <Icon className={`w-5 h-5 ${color}`} />
                <h3 className="text-sm font-medium text-muted-foreground">{label}</h3>
            </div>
            <div className="text-3xl font-bold mb-2">{pct.toFixed(1)}<span className="text-lg text-muted-foreground">%</span></div>
            <div className="w-full h-2 bg-muted rounded-full overflow-hidden mb-2">
                <div
                    className={`h-full rounded-full transition-all duration-500 ${pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-amber-500' : 'bg-emerald-500'
                        }`}
                    style={{ width: `${pct}%` }}
                />
            </div>
            <p className="text-xs text-muted-foreground">{total.toFixed(1)} {unit} total</p>
        </div>
    );
}

export default function MonitoringPage() {
    const queryClient = useQueryClient();
    const [history, setHistory] = useState<{ time: string; cpu: number; memory: number; disk: number }[]>([]);

    const { data: resources } = useQuery({
        queryKey: ['resources'],
        queryFn: () => api.getResources(),
        refetchInterval: 30000,
    });

    const { data: containers, isLoading: containersLoading } = useQuery({
        queryKey: ['containers'],
        queryFn: () => api.getContainers(),
        refetchInterval: 30000,
    });

    const killMutation = useMutation({
        mutationFn: (dockerId: string) => api.killContainer(dockerId),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['containers'] }),
    });

    // Track resource history for charts
    useEffect(() => {
        if (resources) {
            setHistory(prev => {
                const newPoint = {
                    time: new Date().toLocaleTimeString(),
                    cpu: resources.cpu_percent,
                    memory: resources.memory_percent,
                    disk: resources.disk_percent,
                };
                const updated = [...prev, newPoint].slice(-20);
                return updated;
            });
        }
    }, [resources]);

    return (
        <div className="animate-fade-in">
            <h1 className="text-2xl font-bold mb-6">System Monitoring</h1>

            {/* Gauges */}
            {resources && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                    <GaugeCard
                        label="CPU Usage"
                        value={resources.cpu_percent}
                        total={100}
                        unit="% capacity"
                        color="text-blue-400"
                        icon={Cpu}
                    />
                    <GaugeCard
                        label="Memory Usage"
                        value={resources.memory_percent}
                        total={resources.memory_total_gb}
                        unit="GB"
                        color="text-emerald-400"
                        icon={MemoryStick}
                    />
                    <GaugeCard
                        label="Disk Usage"
                        value={resources.disk_percent}
                        total={resources.disk_total_gb}
                        unit="GB"
                        color="text-amber-400"
                        icon={HardDrive}
                    />
                </div>
            )}

            {/* Chart */}
            {history.length > 1 && (
                <div className="bg-card border border-border rounded-xl p-5 mb-8">
                    <h2 className="text-sm font-medium text-muted-foreground mb-4">Resource History (last 10 minutes)</h2>
                    <ResponsiveContainer width="100%" height={200}>
                        <AreaChart data={history}>
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(217 33% 18%)" />
                            <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="hsl(215 20% 55%)" />
                            <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} stroke="hsl(215 20% 55%)" />
                            <Tooltip
                                contentStyle={{ backgroundColor: 'hsl(222 47% 8%)', border: '1px solid hsl(217 33% 18%)', borderRadius: '8px' }}
                                labelStyle={{ color: 'hsl(210 40% 96%)' }}
                            />
                            <Area type="monotone" dataKey="cpu" stroke="#60a5fa" fill="#60a5fa20" name="CPU %" />
                            <Area type="monotone" dataKey="memory" stroke="#34d399" fill="#34d39920" name="Memory %" />
                            <Area type="monotone" dataKey="disk" stroke="#fbbf24" fill="#fbbf2420" name="Disk %" />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            )}

            {/* Running containers */}
            <div className="bg-card border border-border rounded-xl overflow-hidden">
                <div className="p-4 border-b border-border">
                    <h2 className="text-lg font-semibold">Running Containers</h2>
                </div>
                {containersLoading ? (
                    <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div>
                ) : !containers || containers.length === 0 ? (
                    <div className="p-8 text-center text-muted-foreground text-sm">No containers currently running.</div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-border text-muted-foreground text-left">
                                    <th className="px-4 py-3 font-medium">Name</th>
                                    <th className="px-4 py-3 font-medium">Image</th>
                                    <th className="px-4 py-3 font-medium">Run ID</th>
                                    <th className="px-4 py-3 font-medium">Started</th>
                                    <th className="px-4 py-3 font-medium">Memory</th>
                                    <th className="px-4 py-3 font-medium">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {containers.map(container => (
                                    <tr key={container.docker_id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                                        <td className="px-4 py-3 font-medium">{container.name}</td>
                                        <td className="px-4 py-3 text-muted-foreground font-mono text-xs">{container.image}</td>
                                        <td className="px-4 py-3 text-muted-foreground font-mono text-xs">{container.run_id?.slice(0, 8) || '—'}</td>
                                        <td className="px-4 py-3 text-muted-foreground">{container.started_at ? new Date(container.started_at).toLocaleString() : '—'}</td>
                                        <td className="px-4 py-3 text-muted-foreground">{container.memory_usage_mb ? `${container.memory_usage_mb} MB` : '—'}</td>
                                        <td className="px-4 py-3">
                                            <button
                                                onClick={() => killMutation.mutate(container.docker_id)}
                                                className="p-1.5 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                                                title="Kill container"
                                            >
                                                <Skull className="w-4 h-4" />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}

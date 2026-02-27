import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors,
    type DragEndEvent,
} from '@dnd-kit/core';
import {
    arrayMove, SortableContext, sortableKeyboardCoordinates,
    useSortable, verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { api } from '../api/client';
import { formatDate, statusColor, statusBg } from '../lib/utils';
import { Loader2, GripVertical, X, Play, Clock, Calendar, ToggleLeft, ToggleRight, Trash2 } from 'lucide-react';
import type { RunListItem, Schedule } from '../types';

function SortableRunItem({ run, onCancel }: { run: RunListItem; onCancel: (id: string) => void }) {
    const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: run.id });
    const style = { transform: CSS.Transform.toString(transform), transition };

    return (
        <div
            ref={setNodeRef}
            style={style}
            className={`flex items-center gap-3 p-3 rounded-lg border ${statusBg(run.status)} transition-all`}
        >
            {run.status === 'queued' && (
                <button {...attributes} {...listeners} className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground">
                    <GripVertical className="w-4 h-4" />
                </button>
            )}
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="font-medium text-sm truncate">{run.model_name || 'Unknown Model'}</span>
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${statusBg(run.status)} ${statusColor(run.status)}`}>
                        {run.status}
                    </span>
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                    by {run.username || 'Unknown'} · {formatDate(run.created_at)}
                    {run.queue_position && ` · Position: #${run.queue_position}`}
                </div>
            </div>
            {(run.status === 'queued' || run.status === 'running') && (
                <button
                    onClick={() => onCancel(run.id)}
                    className="p-1.5 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                    title="Cancel"
                >
                    <X className="w-4 h-4" />
                </button>
            )}
        </div>
    );
}

const repeatLabels: Record<string, string> = {
    none: 'One-time',
    daily: 'Daily',
    weekly: 'Weekly',
    monthly: 'Monthly',
    custom: 'Custom (cron)',
};

function formatScheduleDate(iso: string | null) {
    if (!iso) return '—';
    try {
        return new Date(iso).toLocaleString(undefined, {
            dateStyle: 'medium', timeStyle: 'short',
        });
    } catch (_e) {
        return iso;
    }
}

export default function RunQueuePage() {
    const queryClient = useQueryClient();

    const { data: queue, isLoading } = useQuery({
        queryKey: ['queue'],
        queryFn: () => api.getQueue(),
        refetchInterval: 5000,
    });

    const { data: schedules, isLoading: schedulesLoading } = useQuery({
        queryKey: ['schedules'],
        queryFn: () => api.getSchedules(),
        refetchInterval: 10000,
    });

    const reorderMutation = useMutation({
        mutationFn: (ids: string[]) => api.reorderQueue(ids),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queue'] }),
    });

    const cancelMutation = useMutation({
        mutationFn: (id: string) => api.cancelRun(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queue'] }),
    });

    const toggleMutation = useMutation({
        mutationFn: (id: string) => api.toggleSchedule(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['schedules'] }),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: string) => api.deleteSchedule(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['schedules'] }),
    });

    const sensors = useSensors(
        useSensor(PointerSensor),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
    );

    const running = (queue || []).filter(r => r.status === 'running');
    const waiting = (queue || []).filter(r => r.status === 'queued');

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (!over || active.id === over.id) return;

        const oldIndex = waiting.findIndex(r => r.id === active.id);
        const newIndex = waiting.findIndex(r => r.id === over.id);
        const reordered = arrayMove(waiting, oldIndex, newIndex);
        reorderMutation.mutate(reordered.map(r => r.id));
    };

    if (isLoading) {
        return <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
    }

    return (
        <div className="max-w-3xl mx-auto animate-fade-in">
            <h1 className="text-2xl font-bold mb-6">Run Queue</h1>

            {/* Running */}
            <div className="mb-8">
                <div className="flex items-center gap-2 mb-3">
                    <Play className="w-5 h-5 text-blue-400" />
                    <h2 className="text-lg font-semibold">Running Now</h2>
                    <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">{running.length}</span>
                </div>
                {running.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4">No runs currently executing.</p>
                ) : (
                    <div className="space-y-2">
                        {running.map(run => (
                            <SortableRunItem key={run.id} run={run} onCancel={(id) => cancelMutation.mutate(id)} />
                        ))}
                    </div>
                )}
            </div>

            {/* Waiting — Drag and Drop */}
            <div className="mb-8">
                <div className="flex items-center gap-2 mb-3">
                    <Clock className="w-5 h-5 text-amber-400" />
                    <h2 className="text-lg font-semibold">Waiting</h2>
                    <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">{waiting.length}</span>
                </div>
                {waiting.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4">No runs in queue.</p>
                ) : (
                    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                        <SortableContext items={waiting.map(r => r.id)} strategy={verticalListSortingStrategy}>
                            <div className="space-y-2">
                                {waiting.map(run => (
                                    <SortableRunItem key={run.id} run={run} onCancel={(id) => cancelMutation.mutate(id)} />
                                ))}
                            </div>
                        </SortableContext>
                    </DndContext>
                )}
            </div>

            {/* ── Scheduled Runs ── */}
            <div>
                <div className="flex items-center gap-2 mb-3">
                    <Calendar className="w-5 h-5 text-purple-400" />
                    <h2 className="text-lg font-semibold">Scheduled Runs</h2>
                    <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                        {schedules?.length || 0}
                    </span>
                </div>
                {schedulesLoading ? (
                    <div className="flex justify-center py-4"><Loader2 className="w-5 h-5 animate-spin text-primary" /></div>
                ) : !schedules || schedules.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4">No scheduled runs. Create one from the Run Model page.</p>
                ) : (
                    <div className="space-y-2">
                        {schedules.map((sched: Schedule) => (
                            <div
                                key={sched.id}
                                className={`flex items-center justify-between p-4 bg-card border rounded-xl transition-colors ${sched.is_active ? 'border-border' : 'border-border/50 opacity-60'
                                    }`}
                            >
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="font-medium text-sm truncate">{sched.model_name}</span>
                                        <span className={`text-xs px-2 py-0.5 rounded-full ${sched.is_active
                                                ? 'bg-emerald-500/10 text-emerald-400'
                                                : 'bg-muted text-muted-foreground'
                                            }`}>
                                            {sched.is_active ? 'Active' : 'Paused'}
                                        </span>
                                        <span className="text-xs px-2 py-0.5 bg-blue-500/10 text-blue-400 rounded-full">
                                            {repeatLabels[sched.repeat_type] || sched.repeat_type}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                                        <span>
                                            Next: <strong className="text-foreground/80">{formatScheduleDate(sched.next_run_at)}</strong>
                                        </span>
                                        {sched.repeat_count && (
                                            <span>
                                                {sched.executions_done}/{sched.repeat_count} runs
                                            </span>
                                        )}
                                        {sched.last_run_at && (
                                            <span>Last: {formatScheduleDate(sched.last_run_at)}</span>
                                        )}
                                        <span>by {sched.created_by_username}</span>
                                    </div>
                                </div>
                                <div className="flex items-center gap-1 ml-3">
                                    <button
                                        onClick={() => toggleMutation.mutate(sched.id)}
                                        className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                                        title={sched.is_active ? 'Pause schedule' : 'Resume schedule'}
                                    >
                                        {sched.is_active
                                            ? <ToggleRight className="w-5 h-5 text-emerald-400" />
                                            : <ToggleLeft className="w-5 h-5" />
                                        }
                                    </button>
                                    <button
                                        onClick={() => deleteMutation.mutate(sched.id)}
                                        className="p-1.5 rounded-lg text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                                        title="Delete schedule"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useAuthStore } from '../stores/auth';
import {
    Loader2, Play, ChevronDown, ChevronRight, Upload, Clock, Calendar,
    Repeat, X,
} from 'lucide-react';

export default function ModelRunPage() {
    const { isDevelop } = useAuthStore();
    const queryClient = useQueryClient();
    const [selectedModelId, setSelectedModelId] = useState<string>('');
    const [inputs, setInputs] = useState<Record<string, string>>({});
    const [configOverride, setConfigOverride] = useState<Record<string, string>>({});
    const [configOpen, setConfigOpen] = useState(false);
    const [submitted, setSubmitted] = useState(false);

    // Scheduling state
    const [scheduleMode, setScheduleMode] = useState(false);
    const [scheduledDate, setScheduledDate] = useState('');
    const [scheduledTime, setScheduledTime] = useState('');
    const [repeatType, setRepeatType] = useState<'none' | 'daily' | 'weekly' | 'monthly' | 'custom'>('none');
    const [cronExpression, setCronExpression] = useState('');
    const [repeatCount, setRepeatCount] = useState<string>('');

    const { data: models, isLoading: modelsLoading } = useQuery({
        queryKey: ['models'],
        queryFn: () => api.getModels(),
    });

    // Auto-select first model
    useEffect(() => {
        if (models && models.length > 0 && !selectedModelId) {
            setSelectedModelId(models[0].id);
        }
    }, [models, selectedModelId]);

    const model = models?.find(m => m.id === selectedModelId);

    const submitMutation = useMutation({
        mutationFn: () => api.createRun({
            model_id: selectedModelId,
            inputs,
            config_override: configOverride,
        }),
        onSuccess: () => setSubmitted(true),
    });

    const scheduleMutation = useMutation({
        mutationFn: () => {
            // Build ISO string directly — avoid new Date() which fails with AM/PM inputs
            const time24 = scheduledTime || '00:00';
            const scheduledAt = `${scheduledDate}T${time24}:00`;
            return api.createSchedule({
                model_id: selectedModelId,
                model_name: model?.name,
                scheduled_at: scheduledAt,
                repeat_type: repeatType,
                cron_expression: repeatType === 'custom' ? cronExpression : undefined,
                repeat_count: repeatCount ? parseInt(repeatCount) : undefined,
                inputs,
                config: configOverride,
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['schedules'] });
            setScheduleMode(false);
            setScheduledDate('');
            setScheduledTime('');
            setRepeatType('none');
            setCronExpression('');
            setRepeatCount('');
            setSubmitted(true);
        },
    });

    if (modelsLoading) {
        return <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
    }

    if (!models || models.length === 0) {
        return <div className="text-center py-20 text-muted-foreground">No models available</div>;
    }

    if (submitted) {
        return (
            <div className="max-w-2xl mx-auto text-center py-20 animate-fade-in">
                <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto mb-4">
                    {scheduleMode ? <Calendar className="w-8 h-8 text-emerald-400" /> : <Play className="w-8 h-8 text-emerald-400" />}
                </div>
                <h2 className="text-2xl font-bold mb-2">
                    {scheduleMode ? 'Run Scheduled!' : 'Run Submitted!'}
                </h2>
                <p className="text-muted-foreground mb-6">
                    {scheduleMode
                        ? 'Your run has been scheduled and will execute at the specified time.'
                        : 'Your run has been queued and will start shortly.'}
                </p>
                <button
                    onClick={() => { setSubmitted(false); setInputs({}); setConfigOverride({}); setScheduleMode(false); }}
                    className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm hover:bg-primary/90"
                >
                    Submit Another Run
                </button>
            </div>
        );
    }

    const inputSchema = model?.input_schema || [];
    const defaultConfig = model?.default_config || {};

    const handleModelChange = (id: string) => {
        setSelectedModelId(id);
        setInputs({});
        setConfigOverride({});
        setConfigOpen(false);
    };



    return (
        <div className="max-w-3xl mx-auto animate-fade-in">
            <h1 className="text-2xl font-bold mb-4">Run Model</h1>

            {/* Model selector */}
            <div className="mb-6">
                <label className="block text-sm font-medium mb-1.5">Select Model</label>
                <select
                    value={selectedModelId}
                    onChange={(e) => handleModelChange(e.target.value)}
                    className="w-full px-3 py-2.5 bg-card border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                >
                    {models.map(m => (
                        <option key={m.id} value={m.id}>{m.name}</option>
                    ))}
                </select>
            </div>

            {model && (
                <>
                    {model.description && <p className="text-muted-foreground mb-6">{model.description}</p>}

                    <div className="space-y-6">
                        {/* Input fields */}
                        <div className="bg-card border border-border rounded-xl p-6">
                            <h2 className="text-lg font-semibold mb-4">Inputs</h2>
                            {inputSchema.length === 0 ? (
                                <p className="text-muted-foreground text-sm">No inputs required.</p>
                            ) : (
                                <div className="space-y-4">
                                    {inputSchema.map((field: any) => (
                                        <div key={field.name}>
                                            <label className="block text-sm font-medium mb-1.5">
                                                {field.name}
                                                {field.required && <span className="text-red-400 ml-1">*</span>}
                                            </label>
                                            {field.type === 'file' && field.source === 'upload' ? (
                                                <div className="flex items-center gap-2">
                                                    <input
                                                        type="file"
                                                        onChange={(e) => {
                                                            const file = e.target.files?.[0];
                                                            if (file) setInputs(prev => ({ ...prev, [field.name]: file.name }));
                                                        }}
                                                        className="flex-1 text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-sm file:bg-primary/10 file:text-primary hover:file:bg-primary/20"
                                                    />
                                                    <Upload className="w-4 h-4 text-muted-foreground" />
                                                </div>
                                            ) : field.type === 'file' ? (
                                                <input
                                                    type="text"
                                                    value={inputs[field.name] || ''}
                                                    onChange={(e) => setInputs(prev => ({ ...prev, [field.name]: e.target.value }))}
                                                    className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                                                    placeholder={`Server path for ${field.name}`}
                                                />
                                            ) : field.type === 'date' ? (
                                                <input
                                                    type="date"
                                                    value={inputs[field.name] || ''}
                                                    onChange={(e) => setInputs(prev => ({ ...prev, [field.name]: e.target.value }))}
                                                    className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                                                />
                                            ) : field.type === 'number' ? (
                                                <input
                                                    type="number"
                                                    value={inputs[field.name] || ''}
                                                    onChange={(e) => setInputs(prev => ({ ...prev, [field.name]: e.target.value }))}
                                                    className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                                                    placeholder={`Enter ${field.name}`}
                                                />
                                            ) : (
                                                <input
                                                    type="text"
                                                    value={inputs[field.name] || ''}
                                                    onChange={(e) => setInputs(prev => ({ ...prev, [field.name]: e.target.value }))}
                                                    className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                                                    placeholder={`Enter ${field.name}`}
                                                />
                                            )}
                                            <p className="text-xs text-muted-foreground mt-1">
                                                Type: {field.type}{field.source ? ` · Source: ${field.source}` : ''}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Config override */}
                        <div className="bg-card border border-border rounded-xl overflow-hidden">
                            <button
                                onClick={() => setConfigOpen(!configOpen)}
                                className="w-full flex items-center justify-between p-4 hover:bg-accent/50 transition-colors"
                            >
                                <span className="font-semibold">Configuration Override</span>
                                {configOpen ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
                            </button>
                            {configOpen && (
                                <div className="p-6 pt-0 space-y-4 border-t border-border">
                                    {Object.entries(defaultConfig).map(([key, field]: [string, any]) => (
                                        <div key={key}>
                                            <label className="block text-sm font-medium mb-1.5">
                                                {key}
                                                <span className="text-xs text-muted-foreground ml-2">({field.type})</span>
                                            </label>
                                            <input
                                                type="text"
                                                value={configOverride[key] ?? String(field.value ?? '')}
                                                onChange={(e) => setConfigOverride(prev => ({ ...prev, [key]: e.target.value }))}
                                                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                                            />
                                            {field.description && (
                                                <p className="text-xs text-muted-foreground mt-1">{field.description}</p>
                                            )}
                                        </div>
                                    ))}
                                    {Object.keys(defaultConfig).length === 0 && (
                                        <p className="text-sm text-muted-foreground">No configuration options available.</p>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* ── Scheduling Section ── */}
                        <div className="bg-card border border-border rounded-xl overflow-hidden">
                            <button
                                onClick={() => setScheduleMode(!scheduleMode)}
                                className="w-full flex items-center justify-between p-4 hover:bg-accent/50 transition-colors"
                            >
                                <div className="flex items-center gap-2">
                                    <Clock className="w-5 h-5 text-blue-400" />
                                    <span className="font-semibold">Schedule Run</span>
                                    {scheduleMode && (
                                        <span className="text-xs px-2 py-0.5 bg-blue-500/10 text-blue-400 rounded-full">
                                            Active
                                        </span>
                                    )}
                                </div>
                                {scheduleMode ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
                            </button>

                            {scheduleMode && (
                                <div className="p-6 pt-0 space-y-4 border-t border-border">
                                    {/* Date & Time */}
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-sm font-medium mb-1.5">
                                                <Calendar className="w-3.5 h-3.5 inline mr-1" />
                                                Date <span className="text-red-400">*</span>
                                            </label>
                                            <input
                                                type="date"
                                                value={scheduledDate}
                                                onChange={(e) => setScheduledDate(e.target.value)}
                                                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                                                min={new Date().toISOString().split('T')[0]}
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-sm font-medium mb-1.5">
                                                <Clock className="w-3.5 h-3.5 inline mr-1" />
                                                Time <span className="text-red-400">*</span>
                                            </label>
                                            <input
                                                type="time"
                                                value={scheduledTime}
                                                onChange={(e) => setScheduledTime(e.target.value)}
                                                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                                            />
                                        </div>
                                    </div>

                                    {/* Repeat */}
                                    <div>
                                        <label className="block text-sm font-medium mb-1.5">
                                            <Repeat className="w-3.5 h-3.5 inline mr-1" />
                                            Repeat
                                        </label>
                                        <select
                                            value={repeatType}
                                            onChange={(e) => setRepeatType(e.target.value as any)}
                                            className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                                        >
                                            <option value="none">One-time (no repeat)</option>
                                            <option value="daily">Daily</option>
                                            <option value="weekly">Weekly</option>
                                            <option value="monthly">Monthly</option>
                                            <option value="custom">Custom (cron expression)</option>
                                        </select>
                                    </div>

                                    {/* Cron expression (only for custom) */}
                                    {repeatType === 'custom' && (
                                        <div>
                                            <label className="block text-sm font-medium mb-1.5">
                                                Cron Expression
                                            </label>
                                            <input
                                                type="text"
                                                value={cronExpression}
                                                onChange={(e) => setCronExpression(e.target.value)}
                                                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/50"
                                                placeholder="0 9 * * 1-5  (every weekday at 9am)"
                                            />
                                            <p className="text-xs text-muted-foreground mt-1">
                                                Format: minute hour day-of-month month day-of-week
                                            </p>
                                        </div>
                                    )}

                                    {/* Repeat count (only for repeating) */}
                                    {repeatType !== 'none' && (
                                        <div>
                                            <label className="block text-sm font-medium mb-1.5">
                                                Max Repetitions
                                            </label>
                                            <input
                                                type="number"
                                                value={repeatCount}
                                                onChange={(e) => setRepeatCount(e.target.value)}
                                                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                                                placeholder="Leave empty for unlimited"
                                                min="1"
                                            />
                                            <p className="text-xs text-muted-foreground mt-1">
                                                Optional — leave empty to repeat indefinitely.
                                            </p>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Error message */}
                        {(submitMutation.isError || scheduleMutation.isError) && (
                            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400">
                                {((submitMutation.error || scheduleMutation.error) as Error).message}
                            </div>
                        )}

                        {/* Submit / Schedule buttons */}
                        <div className="flex gap-3">
                            {!scheduleMode ? (
                                <button
                                    onClick={() => submitMutation.mutate()}
                                    disabled={submitMutation.isPending}
                                    className="flex-1 py-3 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
                                >
                                    {submitMutation.isPending ? (
                                        <><Loader2 className="w-4 h-4 animate-spin" /> Submitting...</>
                                    ) : (
                                        <><Play className="w-4 h-4" /> Submit Run</>
                                    )}
                                </button>
                            ) : (
                                <>
                                    <button
                                        onClick={() => scheduleMutation.mutate()}
                                        disabled={scheduleMutation.isPending || !scheduledDate || !scheduledTime}
                                        className="flex-1 py-3 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-500 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
                                    >
                                        {scheduleMutation.isPending ? (
                                            <><Loader2 className="w-4 h-4 animate-spin" /> Scheduling...</>
                                        ) : (
                                            <><Calendar className="w-4 h-4" /> Schedule Run</>
                                        )}
                                    </button>
                                    <button
                                        onClick={() => submitMutation.mutate()}
                                        disabled={submitMutation.isPending}
                                        className="py-3 px-4 bg-card border border-border text-foreground rounded-xl text-sm font-medium hover:bg-accent/50 disabled:opacity-50 transition-all flex items-center gap-2"
                                    >
                                        <Play className="w-4 h-4" /> Run Now
                                    </button>
                                </>
                            )}
                        </div>
                    </div>
                </>
            )}


        </div>
    );
}

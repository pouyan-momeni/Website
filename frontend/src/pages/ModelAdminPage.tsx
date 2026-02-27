import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Loader2, Plus, Trash2, Save, GripVertical } from 'lucide-react';
import type { InputField, DockerImageSpec } from '../types';

export default function ModelAdminPage() {
    const queryClient = useQueryClient();
    const [selectedModelId, setSelectedModelId] = useState<string>('');
    const [activeTab, setActiveTab] = useState<'inputs' | 'config' | 'containers'>('inputs');

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

    // ──── Input Schema Editor ────
    const [inputFields, setInputFields] = useState<InputField[]>([]);
    const [inputsLoaded, setInputsLoaded] = useState('');
    if (model && inputsLoaded !== model.id) {
        setInputFields(model.input_schema || []);
        setInputsLoaded(model.id);
    }

    const saveInputsMutation = useMutation({
        mutationFn: () => api.updateInputSchema(selectedModelId, inputFields),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['models'] }),
    });

    const addInputField = () => {
        setInputFields(prev => [...prev, { name: '', type: 'text', required: true }]);
    };
    const removeInputField = (idx: number) => {
        setInputFields(prev => prev.filter((_, i) => i !== idx));
    };
    const updateInputField = (idx: number, updates: Partial<InputField>) => {
        setInputFields(prev => prev.map((f, i) => {
            if (i !== idx) return f;
            const updated = { ...f, ...updates };
            // If type changes away from 'file', remove source
            if (updates.type && updates.type !== 'file') {
                delete updated.source;
            }
            // If type changes to 'file' and no source set, default to 'upload'
            if (updates.type === 'file' && !updated.source) {
                updated.source = 'upload';
            }
            return updated;
        }));
    };

    // ──── Config Editor ────
    const [configEntries, setConfigEntries] = useState<Array<{ key: string; value: any; type: string; description: string }>>([]);
    const [configLoaded, setConfigLoaded] = useState('');
    if (model && configLoaded !== model.id) {
        const entries = Object.entries(model.default_config || {}).map(([key, field]: [string, any]) => ({
            key,
            value: field.value ?? '',
            type: field.type || 'string',
            description: field.description || '',
        }));
        setConfigEntries(entries);
        setConfigLoaded(model.id);
    }

    const saveConfigMutation = useMutation({
        mutationFn: () => {
            const configObj: Record<string, any> = {};
            configEntries.forEach(e => {
                configObj[e.key] = { value: e.value, type: e.type, description: e.description };
            });
            return api.updateConfig(selectedModelId, configObj);
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['models'] }),
    });

    const addConfigEntry = () => {
        setConfigEntries(prev => [...prev, { key: '', value: '', type: 'string', description: '' }]);
    };

    const updateConfigEntry = (idx: number, updates: Partial<typeof configEntries[0]>) => {
        setConfigEntries(prev => prev.map((e, i) => i === idx ? { ...e, ...updates } : e));
    };

    const removeConfigEntry = (idx: number) => {
        setConfigEntries(prev => prev.filter((_, i) => i !== idx));
    };

    // ──── Containers Editor ────
    const [containers, setContainers] = useState<DockerImageSpec[]>([]);
    const [containersLoaded, setContainersLoaded] = useState('');
    if (model && containersLoaded !== model.id) {
        setContainers(model.docker_images || []);
        setContainersLoaded(model.id);
    }

    const saveContainersMutation = useMutation({
        mutationFn: () => api.updateContainers(selectedModelId, containers),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['models'] }),
    });

    const addContainer = () => {
        setContainers(prev => [...prev, { name: '', image: '', order: prev.length + 1, env: {} }]);
    };

    const handleModelChange = (id: string) => {
        setSelectedModelId(id);
        // Reset loaded flags so state reloads from new model
        setInputsLoaded('');
        setConfigLoaded('');
        setContainersLoaded('');
    };

    if (modelsLoading) {
        return <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
    }

    if (!models || models.length === 0) {
        return <div className="text-center py-20 text-muted-foreground">No models available</div>;
    }

    return (
        <div className="max-w-3xl mx-auto animate-fade-in">
            <h1 className="text-2xl font-bold mb-1">Model Settings</h1>
            <p className="text-sm text-muted-foreground mb-4">Develop mode only. Manage input schema, config, and containers.</p>

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
                    {/* Tabs */}
                    <div className="flex gap-1 mb-6 bg-card border border-border rounded-lg p-1">
                        {(['inputs', 'config', 'containers'] as const).map(tab => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`flex-1 py-2 rounded-md text-sm font-medium transition-all ${activeTab === tab ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground'
                                    }`}
                            >
                                {tab === 'inputs' ? 'Input Schema' : tab === 'config' ? 'Configuration' : 'Containers'}
                            </button>
                        ))}
                    </div>

                    {/* Input Schema Tab */}
                    {activeTab === 'inputs' && (
                        <div className="bg-card border border-border rounded-xl p-6 space-y-4">
                            {inputFields.map((field, idx) => (
                                <div key={idx} className="flex gap-3 items-start p-3 rounded-lg bg-background border border-border">
                                    <div className="flex-1 grid grid-cols-2 gap-3">
                                        <input
                                            type="text"
                                            value={field.name}
                                            onChange={(e) => updateInputField(idx, { name: e.target.value })}
                                            className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                            placeholder="Field name"
                                        />
                                        <select
                                            value={field.type}
                                            onChange={(e) => updateInputField(idx, { type: e.target.value })}
                                            className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                        >
                                            <option value="text">Text</option>
                                            <option value="date">Date</option>
                                            <option value="number">Number</option>
                                            <option value="file">File</option>
                                        </select>
                                        {/* Source dropdown only for file type */}
                                        {field.type === 'file' && (
                                            <select
                                                value={field.source || 'upload'}
                                                onChange={(e) => updateInputField(idx, { source: e.target.value as 'upload' | 'server' })}
                                                className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                            >
                                                <option value="upload">Upload</option>
                                                <option value="server">Server</option>
                                            </select>
                                        )}
                                        <label className="flex items-center gap-2 text-sm">
                                            <input
                                                type="checkbox"
                                                checked={field.required}
                                                onChange={(e) => updateInputField(idx, { required: e.target.checked })}
                                                className="rounded"
                                            />
                                            Required
                                        </label>
                                    </div>
                                    <button
                                        onClick={() => removeInputField(idx)}
                                        className="p-2 text-muted-foreground hover:text-red-400 transition-colors"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            ))}
                            <div className="flex gap-3">
                                <button onClick={addInputField} className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-accent">
                                    <Plus className="w-4 h-4" /> Add Field
                                </button>
                                <button
                                    onClick={() => saveInputsMutation.mutate()}
                                    disabled={saveInputsMutation.isPending}
                                    className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
                                >
                                    <Save className="w-4 h-4" /> {saveInputsMutation.isPending ? 'Saving...' : 'Save Schema'}
                                </button>
                            </div>
                            {saveInputsMutation.isSuccess && (
                                <p className="text-sm text-emerald-400">✓ Schema saved successfully</p>
                            )}
                        </div>
                    )}

                    {/* Config Tab */}
                    {activeTab === 'config' && (
                        <div className="bg-card border border-border rounded-xl p-6 space-y-4">
                            {configEntries.map((entry, idx) => (
                                <div key={idx} className="flex gap-3 items-start p-3 rounded-lg bg-background border border-border">
                                    <div className="flex-1 grid grid-cols-3 gap-3">
                                        <input
                                            type="text"
                                            value={entry.key}
                                            onChange={(e) => updateConfigEntry(idx, { key: e.target.value })}
                                            className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                            placeholder="Config key name"
                                        />
                                        <input
                                            type="text"
                                            value={String(entry.value ?? '')}
                                            onChange={(e) => updateConfigEntry(idx, { value: e.target.value })}
                                            className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                            placeholder="Value"
                                        />
                                        <input
                                            type="text"
                                            value={entry.description}
                                            onChange={(e) => updateConfigEntry(idx, { description: e.target.value })}
                                            className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                            placeholder="Description"
                                        />
                                    </div>
                                    <button
                                        onClick={() => removeConfigEntry(idx)}
                                        className="p-2 text-muted-foreground hover:text-red-400 transition-colors"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            ))}
                            <div className="flex gap-3">
                                <button onClick={addConfigEntry} className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-accent">
                                    <Plus className="w-4 h-4" /> Add Config Key
                                </button>
                                <button
                                    onClick={() => saveConfigMutation.mutate()}
                                    disabled={saveConfigMutation.isPending}
                                    className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
                                >
                                    <Save className="w-4 h-4" /> {saveConfigMutation.isPending ? 'Saving...' : 'Save Config'}
                                </button>
                            </div>
                            {saveConfigMutation.isSuccess && (
                                <p className="text-sm text-emerald-400">✓ Config saved successfully</p>
                            )}
                        </div>
                    )}

                    {/* Containers Tab */}
                    {activeTab === 'containers' && (
                        <div className="bg-card border border-border rounded-xl p-6 space-y-4">
                            {containers.map((c, idx) => (
                                <div key={idx} className="flex gap-3 items-start p-3 rounded-lg bg-background border border-border">
                                    <GripVertical className="w-4 h-4 text-muted-foreground mt-3 cursor-grab" />
                                    <div className="flex-1 grid grid-cols-2 gap-3">
                                        <input
                                            type="text"
                                            value={c.name}
                                            onChange={(e) => {
                                                const updated = [...containers];
                                                updated[idx] = { ...updated[idx], name: e.target.value };
                                                setContainers(updated);
                                            }}
                                            className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                            placeholder="Container name"
                                        />
                                        <input
                                            type="text"
                                            value={c.image}
                                            onChange={(e) => {
                                                const updated = [...containers];
                                                updated[idx] = { ...updated[idx], image: e.target.value };
                                                setContainers(updated);
                                            }}
                                            className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                            placeholder="Docker image:tag"
                                        />
                                        <input
                                            type="number"
                                            value={c.order}
                                            onChange={(e) => {
                                                const updated = [...containers];
                                                updated[idx] = { ...updated[idx], order: parseInt(e.target.value) || 0 };
                                                setContainers(updated);
                                            }}
                                            className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                            placeholder="Order"
                                        />
                                        <input
                                            type="text"
                                            value={Object.entries(c.env || {}).map(([k, v]) => `${k}=${v}`).join(', ')}
                                            onChange={(e) => {
                                                const env: Record<string, string> = {};
                                                e.target.value.split(',').forEach(pair => {
                                                    const [k, v] = pair.trim().split('=');
                                                    if (k && v) env[k.trim()] = v.trim();
                                                });
                                                const updated = [...containers];
                                                updated[idx] = { ...updated[idx], env };
                                                setContainers(updated);
                                            }}
                                            className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                            placeholder="ENV_KEY=value, ..."
                                        />
                                    </div>
                                    <button
                                        onClick={() => setContainers(prev => prev.filter((_, i) => i !== idx))}
                                        className="p-2 text-muted-foreground hover:text-red-400 transition-colors"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            ))}
                            <div className="flex gap-3">
                                <button onClick={addContainer} className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-accent">
                                    <Plus className="w-4 h-4" /> Add Container
                                </button>
                                <button
                                    onClick={() => saveContainersMutation.mutate()}
                                    disabled={saveContainersMutation.isPending}
                                    className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
                                >
                                    <Save className="w-4 h-4" /> {saveContainersMutation.isPending ? 'Saving...' : 'Save Containers'}
                                </button>
                            </div>
                            {saveContainersMutation.isSuccess && (
                                <p className="text-sm text-emerald-400">✓ Containers saved successfully</p>
                            )}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

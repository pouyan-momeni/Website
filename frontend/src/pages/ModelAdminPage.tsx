import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Loader2, Plus, Trash2, Save, GripVertical, Download, Upload, ChevronRight, ChevronLeft, Check, X } from 'lucide-react';
import type { InputField, DockerImageSpec, Model } from '../types';
import ModelSelector from '../components/ModelSelector';

/* ────── Wizard Step Component ────── */
function WizardStep({ step, label, current }: { step: number; label: string; current: number }) {
    const done = current > step;
    const active = current === step;
    return (
        <div className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${done ? 'bg-emerald-500 text-white' : active ? 'bg-primary text-white ring-2 ring-primary/30' : 'bg-muted text-muted-foreground'
                }`}>
                {done ? <Check className="w-3.5 h-3.5" /> : step}
            </div>
            <span className={`text-sm font-medium ${active ? 'text-foreground' : 'text-muted-foreground'}`}>{label}</span>
        </div>
    );
}

export default function ModelAdminPage() {
    const queryClient = useQueryClient();
    const [selectedModelId, setSelectedModelId] = useState<string>('');
    const [activeTab, setActiveTab] = useState<'inputs' | 'config' | 'containers'>('inputs');
    const [isDevMode, setIsDevMode] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [importStatus, setImportStatus] = useState<string>('');
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

    // ──── Wizard state ────
    const [showWizard, setShowWizard] = useState(false);
    const [wizardStep, setWizardStep] = useState(1);
    const [wizardData, setWizardData] = useState({
        name: '', slug: '', description: '', category: '',
        input_schema: [] as InputField[],
        default_config: {} as Record<string, { value: unknown; type: string; description: string }>,
        docker_images: [] as DockerImageSpec[],
    });
    const [wizardConfigEntries, setWizardConfigEntries] = useState<Array<{ key: string; value: string; type: string; description: string }>>([]);

    // Check mode on mount
    useEffect(() => {
        api.getMode().then(r => setIsDevMode(r.mode === 'develop')).catch(() => { });
    }, []);

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
            if (updates.type && updates.type !== 'file') {
                delete updated.source;
            }
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
        // Auto-convert old models that still have `env` instead of `extra_args`
        const imgs = (model.docker_images || []).map((c: any) => {
            if ('env' in c && !('extra_args' in c)) {
                const envEntries = Object.entries(c.env || {});
                return {
                    ...c,
                    extra_args: envEntries.map(([k, v]) => `-e ${k}=${v}`).join('\n'),
                };
            }
            return c;
        });
        setContainers(imgs);
        setContainersLoaded(model.id);
    }

    const saveContainersMutation = useMutation({
        mutationFn: () => api.updateContainers(selectedModelId, containers),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['models'] }),
    });

    const addContainer = () => {
        setContainers(prev => [...prev, { name: '', image: '', order: prev.length + 1, extra_args: '' }]);
    };

    // ──── Create Model (Wizard) ────
    const createModelMutation = useMutation({
        mutationFn: () => {
            const configObj: Record<string, any> = {};
            wizardConfigEntries.forEach(e => {
                configObj[e.key] = { value: e.value, type: e.type, description: e.description };
            });
            return api.createModel({
                ...wizardData,
                default_config: configObj,
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['models'] });
            setShowWizard(false);
            setWizardStep(1);
            setWizardData({ name: '', slug: '', description: '', category: '', input_schema: [], default_config: {}, docker_images: [] });
            setWizardConfigEntries([]);
        },
    });

    const deleteModelMutation = useMutation({
        mutationFn: (modelId: string) => api.deleteModel(modelId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['models'] });
            setDeleteConfirmId(null);
            setSelectedModelId('');
        },
    });

    // ──── Export / Import ────
    const handleExport = async () => {
        if (!selectedModelId) return;
        try {
            const data = await api.exportModel(selectedModelId);
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${model?.slug || 'model'}.json`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (err) {
            console.error('Export failed', err);
        }
    };

    const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        try {
            const text = await file.text();
            const data = JSON.parse(text);
            await api.importModel(data);
            queryClient.invalidateQueries({ queryKey: ['models'] });
            setImportStatus('✓ Model imported successfully');
            setTimeout(() => setImportStatus(''), 3000);
        } catch (err: any) {
            setImportStatus(`✗ Import failed: ${err.message}`);
            setTimeout(() => setImportStatus(''), 5000);
        }
        e.target.value = '';
    };

    const handleModelChange = (id: string) => {
        setSelectedModelId(id);
        setInputsLoaded('');
        setConfigLoaded('');
        setContainersLoaded('');
    };

    if (modelsLoading) {
        return <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
    }

    return (
        <div className="max-w-3xl mx-auto animate-fade-in">
            <div className="flex items-center justify-between mb-1">
                <h1 className="text-2xl font-bold">Model Settings</h1>
                <div className="flex items-center gap-2">
                    <button onClick={handleExport} disabled={!selectedModelId} className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-lg text-sm hover:bg-accent transition-colors disabled:opacity-40" title="Export model JSON">
                        <Download className="w-4 h-4" /> Export
                    </button>
                    <button onClick={() => fileInputRef.current?.click()} className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-lg text-sm hover:bg-accent transition-colors" title="Import model from JSON">
                        <Upload className="w-4 h-4" /> Import
                    </button>
                    <input ref={fileInputRef} type="file" accept=".json" onChange={handleImport} className="hidden" />
                    {isDevMode && (
                        <button
                            onClick={() => setShowWizard(true)}
                            className="flex items-center gap-1.5 px-3 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
                        >
                            <Plus className="w-4 h-4" /> New Model
                        </button>
                    )}
                    {isDevMode && selectedModelId && (
                        <button
                            onClick={() => setDeleteConfirmId(selectedModelId)}
                            className="flex items-center gap-1.5 px-3 py-2 border border-red-500/30 text-red-400 rounded-lg text-sm hover:bg-red-500/10 transition-colors"
                            title="Delete this model"
                        >
                            <Trash2 className="w-4 h-4" /> Delete
                        </button>
                    )}
                </div>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
                {isDevMode ? 'Develop mode — manage input schema, config, and containers.' : 'Production mode — read-only. Use Export/Import to transfer settings.'}
            </p>

            {importStatus && (
                <div className={`text-sm mb-4 px-3 py-2 rounded-lg ${importStatus.startsWith('✓') ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                    {importStatus}
                </div>
            )}

            {/* ── Delete Confirmation ── */}
            {deleteConfirmId && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 animate-fade-in">
                    <div className="bg-card border border-border rounded-xl p-6 max-w-md mx-4 shadow-2xl">
                        <h3 className="font-semibold text-lg mb-2">Delete Model</h3>
                        <p className="text-sm text-muted-foreground mb-6">
                            Are you sure you want to delete <strong className="text-foreground">'{model?.name}'</strong>? This action cannot be undone.
                        </p>
                        <div className="flex gap-3 justify-end">
                            <button onClick={() => setDeleteConfirmId(null)} className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent">Cancel</button>
                            <button
                                onClick={() => deleteModelMutation.mutate(deleteConfirmId)}
                                disabled={deleteModelMutation.isPending}
                                className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-500 disabled:opacity-50"
                            >
                                {deleteModelMutation.isPending ? 'Deleting...' : 'Delete Model'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Create Model Wizard ── */}
            {showWizard && isDevMode && (
                <div className="bg-card border border-primary/30 rounded-xl p-6 mb-6 animate-fade-in">
                    <div className="flex items-center justify-between mb-5">
                        <h2 className="text-lg font-semibold">Create New Model</h2>
                        <button onClick={() => { setShowWizard(false); setWizardStep(1); }} className="p-1 text-muted-foreground hover:text-foreground"><X className="w-5 h-5" /></button>
                    </div>

                    {/* Step Indicators */}
                    <div className="flex items-center gap-6 mb-6">
                        <WizardStep step={1} label="Details" current={wizardStep} />
                        <div className="flex-1 h-px bg-border" />
                        <WizardStep step={2} label="Inputs" current={wizardStep} />
                        <div className="flex-1 h-px bg-border" />
                        <WizardStep step={3} label="Config" current={wizardStep} />
                        <div className="flex-1 h-px bg-border" />
                        <WizardStep step={4} label="Containers" current={wizardStep} />
                    </div>

                    {/* Step 1: Details */}
                    {wizardStep === 1 && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">Model Name</label>
                                <input value={wizardData.name} onChange={e => {
                                    const name = e.target.value;
                                    setWizardData(d => ({ ...d, name, slug: name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') }));
                                }} className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm" placeholder="e.g. Interest Rate Model" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1">Slug</label>
                                <input value={wizardData.slug} onChange={e => setWizardData(d => ({ ...d, slug: e.target.value }))} className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm font-mono" placeholder="interest-rate-model" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1">Description</label>
                                <textarea value={wizardData.description} onChange={e => setWizardData(d => ({ ...d, description: e.target.value }))} className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm resize-y" rows={3} placeholder="What does this model do?" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1">Category</label>
                                <input value={wizardData.category} onChange={e => setWizardData(d => ({ ...d, category: e.target.value }))} className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm" placeholder="e.g. Interest Rate, Credit Risk, Liquidity" />
                            </div>
                        </div>
                    )}

                    {/* Step 2: Inputs */}
                    {wizardStep === 2 && (
                        <div className="space-y-3">
                            {wizardData.input_schema.map((field, idx) => (
                                <div key={idx} className="flex gap-3 items-start p-3 rounded-lg bg-background border border-border">
                                    <div className="flex-1 grid grid-cols-2 gap-3">
                                        <input value={field.name} onChange={e => {
                                            const updated = [...wizardData.input_schema];
                                            updated[idx] = { ...updated[idx], name: e.target.value };
                                            setWizardData(d => ({ ...d, input_schema: updated }));
                                        }} className="px-3 py-2 bg-card border border-border rounded-lg text-sm" placeholder="Field name" />
                                        <select value={field.type} onChange={e => {
                                            const updated = [...wizardData.input_schema];
                                            updated[idx] = { ...updated[idx], type: e.target.value };
                                            if (e.target.value === 'file' && !updated[idx].source) updated[idx].source = 'upload';
                                            if (e.target.value !== 'file') delete updated[idx].source;
                                            setWizardData(d => ({ ...d, input_schema: updated }));
                                        }} className="px-3 py-2 bg-card border border-border rounded-lg text-sm">
                                            <option value="text">Text</option>
                                            <option value="date">Date</option>
                                            <option value="number">Number</option>
                                            <option value="file">File</option>
                                        </select>
                                    </div>
                                    <button onClick={() => {
                                        setWizardData(d => ({ ...d, input_schema: d.input_schema.filter((_, i) => i !== idx) }));
                                    }} className="p-2 text-muted-foreground hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
                                </div>
                            ))}
                            <button onClick={() => setWizardData(d => ({ ...d, input_schema: [...d.input_schema, { name: '', type: 'text', required: true }] }))} className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-accent">
                                <Plus className="w-4 h-4" /> Add Input Field
                            </button>
                        </div>
                    )}

                    {/* Step 3: Config */}
                    {wizardStep === 3 && (
                        <div className="space-y-3">
                            {wizardConfigEntries.map((entry, idx) => (
                                <div key={idx} className="flex gap-3 items-start p-3 rounded-lg bg-background border border-border">
                                    <div className="flex-1 grid grid-cols-3 gap-3">
                                        <input value={entry.key} onChange={e => {
                                            const updated = [...wizardConfigEntries];
                                            updated[idx] = { ...updated[idx], key: e.target.value };
                                            setWizardConfigEntries(updated);
                                        }} className="px-3 py-2 bg-card border border-border rounded-lg text-sm" placeholder="Config key" />
                                        <input value={entry.value} onChange={e => {
                                            const updated = [...wizardConfigEntries];
                                            updated[idx] = { ...updated[idx], value: e.target.value };
                                            setWizardConfigEntries(updated);
                                        }} className="px-3 py-2 bg-card border border-border rounded-lg text-sm" placeholder="Value" />
                                        <input value={entry.description} onChange={e => {
                                            const updated = [...wizardConfigEntries];
                                            updated[idx] = { ...updated[idx], description: e.target.value };
                                            setWizardConfigEntries(updated);
                                        }} className="px-3 py-2 bg-card border border-border rounded-lg text-sm" placeholder="Description" />
                                    </div>
                                    <button onClick={() => setWizardConfigEntries(prev => prev.filter((_, i) => i !== idx))} className="p-2 text-muted-foreground hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
                                </div>
                            ))}
                            <button onClick={() => setWizardConfigEntries(prev => [...prev, { key: '', value: '', type: 'string', description: '' }])} className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-accent">
                                <Plus className="w-4 h-4" /> Add Config Key
                            </button>
                        </div>
                    )}

                    {/* Step 4: Containers */}
                    {wizardStep === 4 && (
                        <div className="space-y-3">
                            {wizardData.docker_images.map((c, idx) => (
                                <div key={idx} className="p-3 rounded-lg bg-background border border-border space-y-3">
                                    <div className="grid grid-cols-3 gap-3">
                                        <input value={c.name} onChange={e => {
                                            const updated = [...wizardData.docker_images];
                                            updated[idx] = { ...updated[idx], name: e.target.value };
                                            setWizardData(d => ({ ...d, docker_images: updated }));
                                        }} className="px-3 py-2 bg-card border border-border rounded-lg text-sm" placeholder="Step name" />
                                        <input value={c.image} onChange={e => {
                                            const updated = [...wizardData.docker_images];
                                            updated[idx] = { ...updated[idx], image: e.target.value };
                                            setWizardData(d => ({ ...d, docker_images: updated }));
                                        }} className="px-3 py-2 bg-card border border-border rounded-lg text-sm" placeholder="image:tag" />
                                        <input type="number" value={c.order} onChange={e => {
                                            const updated = [...wizardData.docker_images];
                                            updated[idx] = { ...updated[idx], order: parseInt(e.target.value) || 0 };
                                            setWizardData(d => ({ ...d, docker_images: updated }));
                                        }} className="px-3 py-2 bg-card border border-border rounded-lg text-sm" placeholder="Order" />
                                    </div>
                                    <textarea value={c.extra_args} onChange={e => {
                                        const updated = [...wizardData.docker_images];
                                        updated[idx] = { ...updated[idx], extra_args: e.target.value };
                                        setWizardData(d => ({ ...d, docker_images: updated }));
                                    }} className="w-full px-3 py-2 bg-card border border-border rounded-lg text-sm font-mono resize-y" rows={3} placeholder="-e KEY=value&#10;-v /host:/container&#10;--memory 512m" />
                                    <button onClick={() => setWizardData(d => ({ ...d, docker_images: d.docker_images.filter((_, i) => i !== idx) }))} className="text-xs text-muted-foreground hover:text-red-400 flex items-center gap-1"><Trash2 className="w-3 h-3" /> Remove</button>
                                </div>
                            ))}
                            <button onClick={() => setWizardData(d => ({ ...d, docker_images: [...d.docker_images, { name: '', image: '', order: d.docker_images.length + 1, extra_args: '' }] }))} className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-accent">
                                <Plus className="w-4 h-4" /> Add Container
                            </button>
                        </div>
                    )}

                    {/* Wizard Navigation */}
                    <div className="flex items-center justify-between mt-6 pt-4 border-t border-border">
                        <button onClick={() => setWizardStep(s => Math.max(1, s - 1))} disabled={wizardStep === 1} className="flex items-center gap-1 px-3 py-2 text-sm border border-border rounded-lg hover:bg-accent disabled:opacity-40">
                            <ChevronLeft className="w-4 h-4" /> Back
                        </button>
                        {wizardStep < 4 ? (
                            <button onClick={() => setWizardStep(s => s + 1)} className="flex items-center gap-1 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90">
                                Next <ChevronRight className="w-4 h-4" />
                            </button>
                        ) : (
                            <button onClick={() => createModelMutation.mutate()} disabled={createModelMutation.isPending || !wizardData.name || !wizardData.slug} className="flex items-center gap-1 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-500 disabled:opacity-50">
                                {createModelMutation.isPending ? 'Creating...' : 'Create Model'}
                            </button>
                        )}
                    </div>
                    {createModelMutation.isError && (
                        <p className="text-sm text-red-400 mt-3">{(createModelMutation.error as Error).message}</p>
                    )}
                </div>
            )}

            {/* Model selector */}
            {(!models || models.length === 0) ? (
                <div className="text-center py-20 text-muted-foreground">No models available</div>
            ) : (
                <>
                    <div className="mb-6">
                        <ModelSelector
                            models={models}
                            selectedId={selectedModelId}
                            onChange={handleModelChange}
                        />
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
                                                    readOnly={!isDevMode}
                                                />
                                                <select
                                                    value={field.type}
                                                    onChange={(e) => updateInputField(idx, { type: e.target.value })}
                                                    className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                                    disabled={!isDevMode}
                                                >
                                                    <option value="text">Text</option>
                                                    <option value="date">Date</option>
                                                    <option value="number">Number</option>
                                                    <option value="file">File</option>
                                                </select>
                                                {field.type === 'file' && (
                                                    <select
                                                        value={field.source || 'upload'}
                                                        onChange={(e) => updateInputField(idx, { source: e.target.value as 'upload' | 'server' })}
                                                        className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                                        disabled={!isDevMode}
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
                                                        disabled={!isDevMode}
                                                    />
                                                    Required
                                                </label>
                                            </div>
                                            {isDevMode && (
                                                <button
                                                    onClick={() => removeInputField(idx)}
                                                    className="p-2 text-muted-foreground hover:text-red-400 transition-colors"
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            )}
                                        </div>
                                    ))}
                                    {isDevMode && (
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
                                    )}
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
                                                    readOnly={!isDevMode}
                                                />
                                                <input
                                                    type="text"
                                                    value={String(entry.value ?? '')}
                                                    onChange={(e) => updateConfigEntry(idx, { value: e.target.value })}
                                                    className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                                    placeholder="Value"
                                                    readOnly={!isDevMode}
                                                />
                                                <input
                                                    type="text"
                                                    value={entry.description}
                                                    onChange={(e) => updateConfigEntry(idx, { description: e.target.value })}
                                                    className="px-3 py-2 bg-card border border-border rounded-lg text-sm"
                                                    placeholder="Description"
                                                    readOnly={!isDevMode}
                                                />
                                            </div>
                                            {isDevMode && (
                                                <button
                                                    onClick={() => removeConfigEntry(idx)}
                                                    className="p-2 text-muted-foreground hover:text-red-400 transition-colors"
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            )}
                                        </div>
                                    ))}
                                    {isDevMode && (
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
                                    )}
                                    {saveConfigMutation.isSuccess && (
                                        <p className="text-sm text-emerald-400">✓ Config saved successfully</p>
                                    )}
                                </div>
                            )}

                            {/* Containers Tab */}
                            {activeTab === 'containers' && (
                                <div className="bg-card border border-border rounded-xl p-6 space-y-4">
                                    {containers.map((c, idx) => (
                                        <div key={idx} className="p-3 rounded-lg bg-background border border-border space-y-3">
                                            <div className="flex gap-3 items-start">
                                                <GripVertical className="w-4 h-4 text-muted-foreground mt-3 cursor-grab" />
                                                <div className="flex-1 grid grid-cols-3 gap-3">
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
                                                        readOnly={!isDevMode}
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
                                                        readOnly={!isDevMode}
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
                                                        readOnly={!isDevMode}
                                                    />
                                                </div>
                                                {isDevMode && (
                                                    <button
                                                        onClick={() => setContainers(prev => prev.filter((_, i) => i !== idx))}
                                                        className="p-2 text-muted-foreground hover:text-red-400 transition-colors"
                                                    >
                                                        <Trash2 className="w-4 h-4" />
                                                    </button>
                                                )}
                                            </div>
                                            <div>
                                                <label className="block text-xs text-muted-foreground mb-1">Extra Arguments (docker run flags)</label>
                                                <textarea
                                                    value={c.extra_args || ''}
                                                    onChange={(e) => {
                                                        const updated = [...containers];
                                                        updated[idx] = { ...updated[idx], extra_args: e.target.value };
                                                        setContainers(updated);
                                                    }}
                                                    className="w-full px-3 py-2 bg-card border border-border rounded-lg text-sm font-mono resize-y"
                                                    rows={4}
                                                    placeholder={"-e KEY=value\n-v /host/path:/container/path\n--memory 512m"}
                                                    readOnly={!isDevMode}
                                                />
                                            </div>
                                        </div>
                                    ))}
                                    {isDevMode && (
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
                                    )}
                                    {saveContainersMutation.isSuccess && (
                                        <p className="text-sm text-emerald-400">✓ Containers saved successfully</p>
                                    )}
                                </div>
                            )}
                        </>
                    )}
                </>
            )}
        </div>
    );
}

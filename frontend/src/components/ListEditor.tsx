import { useState, useRef } from 'react';
import { Plus, X } from 'lucide-react';

interface Props {
    items: string[];
    onChange: (items: string[]) => void;
    readOnly?: boolean;
    placeholder?: string;
}

export default function ListEditor({ items, onChange, readOnly = false, placeholder = 'Add item…' }: Props) {
    const [draft, setDraft] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);

    const add = () => {
        const val = draft.trim();
        if (!val) return;
        onChange([...items, val]);
        setDraft('');
        inputRef.current?.focus();
    };

    const remove = (idx: number) => {
        onChange(items.filter((_, i) => i !== idx));
    };

    return (
        <div className="flex flex-wrap gap-1.5 items-center min-h-[38px] px-2 py-1.5 bg-card border border-border rounded-lg">
            {items.map((item, idx) => (
                <span
                    key={idx}
                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary/10 text-primary rounded-md text-xs font-medium"
                >
                    {item}
                    {!readOnly && (
                        <button
                            type="button"
                            onClick={() => remove(idx)}
                            className="hover:text-red-400 transition-colors"
                        >
                            <X className="w-3 h-3" />
                        </button>
                    )}
                </span>
            ))}
            {!readOnly && (
                <div className="flex items-center gap-1 flex-1 min-w-[100px]">
                    <input
                        ref={inputRef}
                        value={draft}
                        onChange={e => setDraft(e.target.value)}
                        onKeyDown={e => {
                            if (e.key === 'Enter') { e.preventDefault(); add(); }
                            if (e.key === 'Backspace' && !draft && items.length > 0) {
                                remove(items.length - 1);
                            }
                        }}
                        className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/50 min-w-0"
                        placeholder={items.length === 0 ? placeholder : ''}
                    />
                    {draft.trim() && (
                        <button
                            type="button"
                            onClick={add}
                            className="p-0.5 text-primary hover:text-primary/70 transition-colors"
                        >
                            <Plus className="w-3.5 h-3.5" />
                        </button>
                    )}
                </div>
            )}
            {readOnly && items.length === 0 && (
                <span className="text-xs text-muted-foreground/50 px-1">—</span>
            )}
        </div>
    );
}

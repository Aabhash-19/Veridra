import {
  Bot,
  Check,
  ChevronDown,
  Globe,
  ShieldCheck,
  Sparkles,
  Zap,
} from 'lucide-react';
import { useState } from 'react';
import { DEFAULT_MODEL_ID, DEFAULT_MODELS, resolveActiveModelId } from '../lib/models';
import type { SupportedModelInfo } from '../lib/types';

const PROVIDER_STYLES: Record<
  string,
  { icon: typeof Sparkles; gradient: string; badge: string; glow: string }
> = {
  openai: {
    icon: Bot,
    gradient: 'from-emerald-400 via-teal-500 to-cyan-500',
    badge: 'bg-emerald-500/15 text-emerald-800 dark:bg-emerald-400/20 dark:text-emerald-200',
    glow: 'border-emerald-400/80 bg-emerald-50/70 ring-emerald-500/40 dark:border-emerald-400/60 dark:bg-emerald-500/20',
  },
  groq: {
    icon: Zap,
    gradient: 'from-amber-400 via-orange-500 to-rose-500',
    badge: 'bg-orange-500/15 text-orange-800 dark:bg-orange-400/20 dark:text-orange-200',
    glow: 'border-orange-400/80 bg-orange-50/70 ring-orange-500/40 dark:border-orange-400/60 dark:bg-orange-500/20',
  },
  openrouter: {
    icon: Globe,
    gradient: 'from-violet-500 via-purple-500 to-indigo-500',
    badge: 'bg-violet-500/15 text-violet-800 dark:bg-violet-400/20 dark:text-violet-200',
    glow: 'border-violet-400/80 bg-violet-50/70 ring-violet-500/40 dark:border-violet-400/60 dark:bg-violet-500/20',
  },
  gemini: {
    icon: Sparkles,
    gradient: 'from-indigo-500 via-violet-500 to-fuchsia-500',
    badge: 'bg-indigo-500/15 text-indigo-700 dark:bg-indigo-400/20 dark:text-indigo-200',
    glow: 'border-indigo-400/80 bg-indigo-50/70 ring-indigo-500/40 dark:border-indigo-400/60 dark:bg-indigo-500/20',
  },
};

export function ModelSelector({
  models,
  value,
  onChange,
  defaultModelLabel,
  compact = false,
}: {
  models?: SupportedModelInfo[];
  value: string;
  onChange: (modelId: string) => void;
  defaultModelLabel?: string;
  compact?: boolean;
}) {
  const rawList = models && models.length > 0 ? models : DEFAULT_MODELS;
  // Show ready/connected AI assistants first so creators immediately see what works right now
  const list = [...rawList].sort((a, b) => Number(Boolean(b.configured)) - Number(Boolean(a.configured)));

  const normalizedValue = resolveActiveModelId(value);
  const normalizedDefault = resolveActiveModelId(defaultModelLabel) || DEFAULT_MODEL_ID;
  const knownIds = new Set(list.map((m) => m.id));
  const isCustom = Boolean(normalizedValue && !knownIds.has(normalizedValue));
  const [showCustom, setShowCustom] = useState(isCustom);

  return (
    <div className="space-y-3">
      <div className={`grid gap-3 ${compact ? 'sm:grid-cols-2' : 'sm:grid-cols-2'}`}>
        {list.map((m) => {
          const selected =
            normalizedValue === m.id || (!normalizedValue && m.id === normalizedDefault);
          const theme = PROVIDER_STYLES[m.provider] || {
            icon: ShieldCheck,
            gradient: 'from-indigo-500 to-violet-500',
            badge: 'bg-indigo-500/15 text-indigo-700',
            glow: 'border-indigo-400/80 bg-indigo-50/70 ring-indigo-500/40',
          };
          const Icon = theme.icon;

          return (
            <button
              key={m.id}
              type="button"
              onClick={() => onChange(m.id)}
              aria-pressed={selected}
              className={`group relative flex flex-col justify-between rounded-2xl border p-4 text-left transition-all duration-200 ${
                selected
                  ? `${theme.glow} ring-1 shadow-md`
                  : 'glass-subtle hover:-translate-y-0.5 hover:border-indigo-300/70 hover:bg-white/80 dark:hover:bg-slate-800/65'
              }`}
            >
              <div className="flex items-start justify-between gap-2.5">
                <div className="flex items-center gap-2.5">
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${theme.gradient} text-white shadow-sm`}
                  >
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <div>
                    <div className="text-[14px] font-semibold text-[#131B2E] dark:text-white">
                      {m.label}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${theme.badge}`}
                      >
                        {m.tier}
                      </span>
                      {typeof m.configured === 'boolean' ? (
                        m.configured ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-teal-500/15 px-2 py-0.5 text-[10px] font-semibold text-teal-800 dark:text-teal-200">
                            <span className="h-1.5 w-1.5 rounded-full bg-teal-500" />
                            Ready
                          </span>
                        ) : (
                          <span className="inline-block rounded-full bg-slate-500/10 px-2 py-0.5 text-[10px] font-medium text-[#5E6A82] dark:text-slate-400">
                            Needs key
                          </span>
                        )
                      ) : null}
                    </div>
                  </div>
                </div>

                {selected ? (
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 text-white shadow-sm">
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                ) : null}
              </div>

              {!compact ? (
                <p className="mt-2.5 text-[12px] leading-relaxed text-[#5E6A82] dark:text-slate-300">
                  {m.description}
                </p>
              ) : null}
            </button>
          );
        })}
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowCustom((v) => !v)}
          className="inline-flex items-center gap-1 text-[12px] font-medium text-[#5E6A82] transition hover:text-[#131B2E] dark:text-slate-400 dark:hover:text-slate-200"
        >
          <span>Use a custom AI model name</span>
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${showCustom ? 'rotate-180' : ''}`}
            aria-hidden="true"
          />
        </button>

        {showCustom ? (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <label htmlFor="custom-model-input" className="sr-only">
              Custom AI model name
            </label>
            <input
              id="custom-model-input"
              type="text"
              value={isCustom ? normalizedValue : ''}
              onChange={(e) => onChange(e.target.value.trim())}
              placeholder="e.g., gpt-4.1-mini, claude-3-5-haiku-latest, gemini-3.6-flash"
              className="w-80 max-w-full rounded-xl border border-[#DCE2EC]/90 bg-white/80 px-3 py-1.5 text-[13px] text-[#131B2E] backdrop-blur-md focus:border-[#5B5CE2] focus:outline-none dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

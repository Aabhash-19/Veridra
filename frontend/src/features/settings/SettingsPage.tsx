import { useQuery } from '@tanstack/react-query';
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Copy,
  KeyRound,
  Monitor,
  Moon,
  Shield,
  Sliders,
  Sparkles,
  Sun,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { ModelSelector } from '../../components/ModelSelector';
import { useTheme } from '../../components/themeContext';
import { useToast } from '../../components/toastContext';
import { api } from '../../lib/api';
import {
  DEFAULT_MODEL_ID,
  getSavedPreferredModel,
  resolveActiveModelId,
  savePreferredModel,
} from '../../lib/models';

const ENV_SNIPPET = `# Copy into backend/.env and add at least ONE AI key (never commit .env)
# ChatGPT (OpenAI)
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini

# Fast free-tier alternative (Groq)
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b

# Optional OpenRouter / Google Gemini
OPENROUTER_API_KEY=
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.6-flash

# Web Search
TAVILY_API_KEY=your_tavily_api_key`;

const PROVIDER_CARDS = [
  { key: 'openai', name: 'ChatGPT (OpenAI)', envKey: 'OPENAI_API_KEY' },
  { key: 'groq', name: 'Groq (Llama 3.3)', envKey: 'GROQ_API_KEY' },
  { key: 'openrouter', name: 'OpenRouter Hub', envKey: 'OPENROUTER_API_KEY' },
  { key: 'gemini', name: 'Google Gemini', envKey: 'GEMINI_API_KEY' },
] as const;

export function SettingsPage() {
  const { pushToast } = useToast();
  const { preference, setPreference } = useTheme();
  const [showEnvSnippet, setShowEnvSnippet] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [preferredModel, setPreferredModel] = useState<string>(() => getSavedPreferredModel());

  const integrationsQuery = useQuery({
    queryKey: ['integrations'],
    queryFn: api.getIntegrations,
  });

  const info = integrationsQuery.data;

  useEffect(() => {
    if (!preferredModel && info?.llm_model) {
      setPreferredModel(resolveActiveModelId(info.llm_model) || DEFAULT_MODEL_ID);
    }
  }, [info, preferredModel]);

  const handleModelChange = (modelId: string) => {
    const resolved = resolveActiveModelId(modelId);
    setPreferredModel(resolved);
    savePreferredModel(resolved);
    pushToast({
      title: 'Default AI assistant saved',
      description: resolved || info?.llm_model || DEFAULT_MODEL_ID,
      variant: 'success',
    });
  };

  const copyEnvSnippet = async () => {
    try {
      await navigator.clipboard.writeText(ENV_SNIPPET);
      pushToast({ title: 'Copied setup template', variant: 'success' });
    } catch {
      pushToast({ title: 'Could not copy template', variant: 'error' });
    }
  };

  if (integrationsQuery.isLoading) {
    return <div className="glass-panel h-64 animate-pulse rounded-3xl" />;
  }

  const statuses = info?.provider_statuses || {};

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Appearance */}
      <section className="glass-panel rounded-3xl p-6">
        <h2 className="text-[16px] font-bold text-[#131B2E] dark:text-white">Look &amp; theme</h2>
        <p className="mt-1 text-[13px] text-[#5E6A82] dark:text-slate-300">
          Pick the frosted glass look that feels best to create in.
        </p>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {(
            [
              {
                value: 'light',
                label: 'Light editorial',
                icon: Sun,
                swatch: 'from-indigo-400 via-pink-300 to-teal-300',
              },
              {
                value: 'dark',
                label: 'Midnight dark',
                icon: Moon,
                swatch: 'from-indigo-700 via-purple-700 to-slate-900',
              },
              {
                value: 'system',
                label: 'System match',
                icon: Monitor,
                swatch: 'from-sky-400 via-violet-500 to-slate-700',
              },
            ] as const
          ).map((opt) => {
            const Icon = opt.icon;
            const active = preference === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => setPreference(opt.value)}
                aria-pressed={active}
                className={`flex items-center gap-3 rounded-2xl p-3.5 text-left text-[13px] font-semibold transition ${
                  active
                    ? 'border border-indigo-400 bg-indigo-500/15 text-indigo-800 ring-1 ring-indigo-400/50 dark:text-indigo-200'
                    : 'glass-subtle text-[#131B2E] hover:bg-white/85 dark:text-slate-200'
                }`}
              >
                <span
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${opt.swatch} text-white shadow-xs`}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <span>{opt.label}</span>
              </button>
            );
          })}
        </div>
      </section>

      {/* Default AI Assistant */}
      <section className="glass-panel rounded-3xl p-6">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-indigo-500" aria-hidden="true" />
          <h2 className="text-[16px] font-bold text-[#131B2E] dark:text-white">
            Default AI assistant
          </h2>
        </div>
        <p className="mt-1 text-[13px] text-[#5E6A82] dark:text-slate-300">
          Choose ChatGPT, Groq, Claude, OpenRouter, or Gemini as your everyday writer.
        </p>
        <div className="mt-4">
          <ModelSelector
            models={info?.available_models}
            value={preferredModel}
            onChange={handleModelChange}
            defaultModelLabel={info?.llm_model}
          />
        </div>
      </section>

      {/* Connected Services */}
      <section className="glass-panel rounded-3xl p-6">
        <div className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-indigo-500" aria-hidden="true" />
          <h2 className="text-[16px] font-bold text-[#131B2E] dark:text-white">
            Connected AI &amp; web search
          </h2>
        </div>
        <p className="mt-1 text-[13px] text-[#5E6A82] dark:text-slate-300">
          {info?.llm_masked_label || 'Add any supported AI key in backend/.env — keys never leave your server.'}
        </p>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {PROVIDER_CARDS.map((p) => {
            const ok = Boolean(statuses[p.key]);
            return (
              <div key={p.key} className="glass-subtle rounded-2xl p-3.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-bold text-[#131B2E] dark:text-white">
                    {p.name}
                  </span>
                  {ok ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-teal-500/15 px-2 py-0.5 text-[11px] font-semibold text-teal-800 dark:text-teal-200">
                      <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                      Ready
                    </span>
                  ) : (
                    <span className="rounded-full bg-slate-500/10 px-2 py-0.5 text-[11px] font-medium text-[#5E6A82] dark:text-slate-400">
                      Not added
                    </span>
                  )}
                </div>
                <p className="mt-1.5 font-mono text-[11px] text-[#5E6A82] dark:text-slate-400">
                  {p.envKey}
                </p>
              </div>
            );
          })}

          <div className="glass-tint-teal rounded-2xl p-3.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[13px] font-bold text-[#131B2E] dark:text-white">
                Web Research (Tavily)
              </span>
              {info?.search_configured ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-teal-500/15 px-2 py-0.5 text-[11px] font-semibold text-teal-800 dark:text-teal-200">
                  <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                  Ready
                </span>
              ) : (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-900 dark:bg-amber-500/20 dark:text-amber-200">
                  Not added
                </span>
              )}
            </div>
            <p className="mt-1.5 font-mono text-[11px] text-[#5E6A82] dark:text-slate-300">
              TAVILY_API_KEY
            </p>
          </div>
        </div>

        <div className="mt-5 border-t border-[#DCE2EC]/70 pt-5 dark:border-slate-800">
          <h3 className="text-[14px] font-bold text-[#131B2E] dark:text-white">
            1-Click Publishing &amp; Connected Social Accounts
          </h3>
          <p className="mt-1 text-[12px] text-[#5E6A82] dark:text-slate-300">
            1-Click Composer works out of the box for LinkedIn, X, and Instagram with bold,
            italics, and bullets pre-formatted. Optionally add API tokens in{' '}
            <code className="rounded bg-black/5 px-1 py-0.5 dark:bg-white/10">backend/.env</code>{' '}
            for direct background posting.
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {[
              {
                key: 'linkedin',
                name: 'LinkedIn',
                envHint: 'LINKEDIN_ACCESS_TOKEN + LINKEDIN_PERSON_URN',
              },
              {
                key: 'x',
                name: 'X (Twitter)',
                envHint: 'X_ACCESS_TOKEN',
              },
              {
                key: 'instagram',
                name: 'Instagram',
                envHint: '1-Click copy & launch composer',
              },
            ].map((soc) => {
              const directOk = Boolean(info?.social_connections?.[soc.key]);
              return (
                <div key={soc.key} className="glass-subtle rounded-2xl p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[13px] font-bold text-[#131B2E] dark:text-white">
                      {soc.name}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                        directOk
                          ? 'bg-teal-500/15 text-teal-800 dark:text-teal-200'
                          : 'bg-indigo-500/15 text-indigo-800 dark:text-indigo-200'
                      }`}
                    >
                      {directOk ? 'Direct API Ready' : '1-Click Ready'}
                    </span>
                  </div>
                  <p className="mt-1.5 font-mono text-[10px] text-[#5E6A82] dark:text-slate-400">
                    {soc.envHint}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        <div className="glass-subtle mt-4 flex items-start gap-2.5 rounded-2xl p-3.5 text-[12px] text-[#5E6A82] dark:text-slate-300">
          <Shield className="mt-0.5 h-4 w-4 shrink-0 text-teal-500" aria-hidden="true" />
          <p>
            To add ChatGPT, Groq, or Claude, paste its key line into <code className="font-mono">backend/.env</code> and restart the backend server.
          </p>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-[#DCE2EC]/60 pt-4 dark:border-slate-800">
          <button
            type="button"
            onClick={() => setShowEnvSnippet((v) => !v)}
            className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-indigo-600 dark:text-indigo-300"
          >
            <span>{showEnvSnippet ? 'Hide key setup template' : 'Key setup template (.env)'}</span>
            {showEnvSnippet ? (
              <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </button>

          <button
            type="button"
            onClick={() => void copyEnvSnippet()}
            className="glass-subtle inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium text-[#131B2E] dark:text-slate-200"
          >
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            Copy snippet
          </button>
        </div>

        {showEnvSnippet ? (
          <pre className="mt-3 overflow-x-auto rounded-2xl bg-[#0B1120] p-4 font-mono text-[12px] leading-relaxed text-slate-200">
            {ENV_SNIPPET}
          </pre>
        ) : null}
      </section>

      {/* Optional studio limits */}
      <div className="glass-panel rounded-3xl p-5">
        <button
          type="button"
          onClick={() => setShowDetails((v) => !v)}
          className="flex w-full items-center justify-between text-left"
        >
          <span className="inline-flex items-center gap-2 text-[14px] font-semibold text-[#131B2E] dark:text-white">
            <Sliders className="h-4 w-4 text-indigo-500" aria-hidden="true" />
            Quality guardrails &amp; workspace details
          </span>
          {showDetails ? (
            <ChevronUp className="h-4 w-4 text-[#5E6A82]" aria-hidden="true" />
          ) : (
            <ChevronDown className="h-4 w-4 text-[#5E6A82]" aria-hidden="true" />
          )}
        </button>

        {showDetails ? (
          <div className="mt-4 space-y-3 border-t border-[#DCE2EC]/60 pt-4 text-[13px] dark:border-slate-800">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="glass-subtle rounded-2xl p-3">
                <div className="text-[12px] text-[#5E6A82] dark:text-slate-400">
                  Max polish rounds
                </div>
                <div className="mt-0.5 text-[16px] font-bold tabular-nums">
                  {info?.guardrails?.max_editor_revisions ?? 3}
                </div>
              </div>
              <div className="glass-subtle rounded-2xl p-3">
                <div className="text-[12px] text-[#5E6A82] dark:text-slate-400">
                  Max fact-check fixes
                </div>
                <div className="mt-0.5 text-[16px] font-bold tabular-nums">
                  {info?.guardrails?.max_fact_remediations ?? 2}
                </div>
              </div>
              <div className="glass-subtle rounded-2xl p-3">
                <div className="text-[12px] text-[#5E6A82] dark:text-slate-400">
                  Quality target
                </div>
                <div className="mt-0.5 text-[16px] font-bold tabular-nums">
                  {info?.guardrails?.editor_approval_threshold ?? 85}/100
                </div>
              </div>
            </div>
            <p className="text-[12px] text-[#5E6A82] dark:text-slate-400">{info?.privacy_note}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

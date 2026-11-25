import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BarChart3, Play, Sparkles } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { DemoModeBanner } from '../../components/DemoModeBanner';
import { EmptyState } from '../../components/EmptyState';
import { ModelSelector } from '../../components/ModelSelector';
import { useToast } from '../../components/toastContext';
import { api, ApiClientError } from '../../lib/api';
import { formatDateTime } from '../../lib/format';
import { DEFAULT_MODEL_ID, getSavedPreferredModel, resolveActiveModelId } from '../../lib/models';
import type { WorkflowStrategyType } from '../../lib/types';

export function BenchmarksPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();

  const integrationsQuery = useQuery({
    queryKey: ['integrations'],
    queryFn: api.getIntegrations,
  });
  const datasetQuery = useQuery({
    queryKey: ['benchmark-dataset'],
    queryFn: api.listBenchmarkDataset,
  });
  const benchmarksQuery = useQuery({
    queryKey: ['benchmarks'],
    queryFn: () => api.listBenchmarks(20, 0),
    refetchInterval: 4000,
  });

  const integrations = integrationsQuery.data;
  const dataset = datasetQuery.data || [];
  const experiments = benchmarksQuery.data?.items || [];

  const [name, setName] = useState('Full Studio vs Quick Draft Comparison');
  const [topicCount, setTopicCount] = useState(4);
  const [repeats, setRepeats] = useState(1);
  const [includeHoldout, setIncludeHoldout] = useState(false);
  const [strategies, setStrategies] = useState<WorkflowStrategyType[]>([
    'single_agent',
    'multi_agent',
  ]);
  const [selectedModel, setSelectedModel] = useState<string>(() => getSavedPreferredModel());
  const [useDemoMode, setUseDemoMode] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showDataset, setShowDataset] = useState(false);

  useEffect(() => {
    if (!integrations) return;
    if (!integrations.llm_configured) {
      setUseDemoMode(true);
    }
    if (!selectedModel && integrations.llm_model) {
      setSelectedModel(resolveActiveModelId(integrations.llm_model) || DEFAULT_MODEL_ID);
    }
  }, [integrations, selectedModel]);

  const createMutation = useMutation({
    mutationFn: api.createBenchmark,
    onSuccess: (exp) => {
      queryClient.invalidateQueries({ queryKey: ['benchmarks'] });
      pushToast({
        title: 'Comparison started',
        description: `Running ${exp.cases.length} side-by-side tests.`,
        variant: 'success',
      });
      navigate(`/benchmarks/${exp.benchmark_id}`);
    },
    onError: (err) => {
      setErrorMsg(err instanceof ApiClientError ? err.message : 'Could not start comparison.');
    },
  });

  const toggleStrategy = (s: WorkflowStrategyType) => {
    setStrategies((prev) => {
      if (prev.includes(s)) {
        return prev.length > 1 ? prev.filter((x) => x !== s) : prev;
      }
      return [...prev, s];
    });
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    createMutation.mutate({
      name: name.trim() || 'Writing Comparison',
      topic_count: topicCount,
      include_holdout: includeHoldout,
      strategies,
      repeats,
      model_override: resolveActiveModelId(selectedModel) || null,
      use_demo_mode: useDemoMode,
    });
  };

  return (
    <div className="space-y-6">
      {integrations && !integrations.llm_configured ? (
        <DemoModeBanner reason="Live AI keys are not added yet — test comparisons cleanly in Demo Mode." />
      ) : null}

      <form onSubmit={handleSubmit} className="glass-panel space-y-5 rounded-3xl p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-[18px] font-bold text-[#131B2E] dark:text-white">
              Compare writing styles side by side
            </h2>
            <p className="mt-0.5 text-[13px] text-[#5E6A82] dark:text-slate-300">
              See how the full 4-step studio stacks up against a quick 1-pass draft on accuracy and
              polish.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowDataset((v) => !v)}
            className="glass-subtle rounded-full px-3.5 py-1.5 text-[12px] font-semibold text-[#131B2E] dark:text-slate-200"
          >
            {showDataset ? 'Hide starter topics' : `Browse topics (${dataset.length})`}
          </button>
        </div>

        {errorMsg ? (
          <div
            role="alert"
            className="rounded-xl border border-rose-300 bg-rose-50/90 p-3 text-[13px] text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/15 dark:text-rose-200"
          >
            {errorMsg}
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="bmk-name" className="block text-[13px] font-semibold">
              Test name
            </label>
            <input
              id="bmk-name"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[14px] dark:border-slate-700 dark:bg-slate-900/65"
            />
          </div>

          <div>
            <label htmlFor="bmk-count" className="block text-[13px] font-semibold">
              Sample topics (1–30)
            </label>
            <input
              id="bmk-count"
              type="number"
              min={1}
              max={30}
              value={topicCount}
              onChange={(e) =>
                setTopicCount(Math.max(1, Math.min(30, parseInt(e.target.value, 10) || 1)))
              }
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[14px] tabular-nums dark:border-slate-700 dark:bg-slate-900/65"
            />
          </div>

          <div>
            <label htmlFor="bmk-repeats" className="block text-[13px] font-semibold">
              Tries per topic
            </label>
            <select
              id="bmk-repeats"
              value={repeats}
              onChange={(e) => setRepeats(parseInt(e.target.value, 10))}
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[14px] dark:border-slate-700 dark:bg-slate-900/65"
            >
              <option value={1}>1 try each</option>
              <option value={2}>2 tries each</option>
              <option value={3}>3 tries each</option>
            </select>
          </div>
        </div>

        <div>
          <span className="mb-2 block text-[13px] font-semibold">
            AI assistant used for every test
          </span>
          <ModelSelector
            models={integrations?.available_models}
            value={selectedModel}
            onChange={setSelectedModel}
            defaultModelLabel={integrations?.llm_model}
            compact
          />
        </div>

        <div>
          <span className="block text-[13px] font-semibold">Styles to compare</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {(
              [
                { id: 'single_agent', label: 'Quick 1-pass draft' },
                { id: 'multi_agent', label: 'Full 4-step studio' },
                { id: 'no_editor', label: 'Without polish step' },
                { id: 'no_fact_checker', label: 'Without fact-check step' },
              ] as const
            ).map((opt) => {
              const active = strategies.includes(opt.id);
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => toggleStrategy(opt.id)}
                  aria-pressed={active}
                  className={`rounded-full px-4 py-1.5 text-[13px] font-semibold transition ${
                    active
                      ? 'border border-indigo-400 bg-gradient-to-r from-indigo-500/20 to-violet-500/20 text-indigo-800 dark:text-indigo-200'
                      : 'glass-subtle text-[#5E6A82] dark:text-slate-300'
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-[#DCE2EC]/60 pt-4 dark:border-slate-800">
          <div className="flex flex-wrap items-center gap-5 text-[13px]">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={includeHoldout}
                onChange={(e) => setIncludeHoldout(e.target.checked)}
              />
              <span>Include extra challenge topics</span>
            </label>
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={useDemoMode}
                onChange={(e) => setUseDemoMode(e.target.checked)}
              />
              <Sparkles
                className="h-4 w-4 text-amber-600 dark:text-amber-300"
                aria-hidden="true"
              />
              <span>Practice in Demo Mode</span>
            </label>
          </div>

          <button
            type="submit"
            disabled={createMutation.isPending}
            className="btn-aurora inline-flex items-center gap-2 rounded-full px-5 py-2 text-[14px] font-semibold disabled:opacity-60"
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            <span>{createMutation.isPending ? 'Starting...' : 'Run comparison'}</span>
          </button>
        </div>
      </form>

      {showDataset ? (
        <section className="glass-panel rounded-3xl p-5">
          <h3 className="text-[15px] font-bold text-[#131B2E] dark:text-white">
            Included creator topics ({dataset.length})
          </h3>
          <div className="mt-3 max-h-72 divide-y divide-[#DCE2EC]/70 overflow-y-auto text-[12px] dark:divide-slate-800">
            {dataset.map((t, i) => (
              <div
                key={t.topic_id}
                className="flex flex-wrap items-center justify-between gap-2 py-2.5"
              >
                <div className="min-w-0 flex-1">
                  <span className="font-semibold text-indigo-600 dark:text-indigo-300">
                    #{i + 1}
                  </span>{' '}
                  · <strong className="text-[#131B2E] dark:text-slate-100">{t.topic}</strong>
                </div>
                <span className="glass-subtle rounded-full px-2.5 py-0.5 text-[#5E6A82] dark:text-slate-300">
                  {t.category}
                </span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-[16px] font-bold text-[#131B2E] dark:text-white">Past comparisons</h2>
        {benchmarksQuery.isLoading ? (
          <div className="glass-panel h-32 animate-pulse rounded-2xl" />
        ) : experiments.length === 0 ? (
          <EmptyState
            icon={<BarChart3 className="h-5 w-5" aria-hidden="true" />}
            title="No comparisons yet"
            description="Run your first side-by-side test above to see which writing style works best."
          />
        ) : (
          <div className="space-y-2.5">
            {experiments.map((exp) => (
              <Link
                key={exp.benchmark_id}
                to={`/benchmarks/${exp.benchmark_id}`}
                className="glass-panel block rounded-2xl p-4.5 transition hover:-translate-y-0.5 hover:border-indigo-400/60"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className="text-[15px] font-bold text-[#131B2E] dark:text-white">
                      {exp.name}
                    </span>
                    <span className="glass-subtle rounded-full px-2.5 py-0.5 text-[11px] font-semibold capitalize text-[#131B2E] dark:text-slate-200">
                      {exp.status}
                    </span>
                    {exp.execution_mode === 'demo' ? (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-900 dark:bg-amber-500/20 dark:text-amber-200">
                        DEMO
                      </span>
                    ) : null}
                  </div>
                  <span className="text-[12px] tabular-nums text-[#5E6A82] dark:text-slate-400">
                    {formatDateTime(exp.created_at)}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

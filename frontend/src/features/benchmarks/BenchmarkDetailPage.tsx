import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Info, Star } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { DemoModeBanner } from '../../components/DemoModeBanner';
import { EmptyState } from '../../components/EmptyState';
import { RunStatusBadge } from '../../components/StatusBadge';
import { useToast } from '../../components/toastContext';
import { api } from '../../lib/api';
import { formatCostUsd, formatDurationMs, formatPercent, formatTokens } from '../../lib/format';

const STYLE_NAMES: Record<string, string> = {
  single_agent: 'Quick 1-pass draft',
  multi_agent: 'Full 4-step studio',
  no_editor: 'Without polish step',
  no_fact_checker: 'Without fact-check step',
};

export function BenchmarkDetailPage() {
  const { benchmarkId = '' } = useParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [ratingCaseId, setRatingCaseId] = useState<string | null>(null);
  const [ratingVal, setRatingVal] = useState(4);
  const [ratingNotes, setRatingNotes] = useState('');

  const bmkQuery = useQuery({
    queryKey: ['benchmarks', benchmarkId],
    queryFn: () => api.getBenchmark(benchmarkId),
    enabled: Boolean(benchmarkId),
    refetchInterval: (q) => (q.state.data?.status !== 'completed' ? 2500 : false),
  });

  const rateMutation = useMutation({
    mutationFn: () => {
      if (!ratingCaseId) throw new Error('No topic selected');
      return api.rateBenchmarkCase(benchmarkId, ratingCaseId, {
        rating: ratingVal,
        notes: ratingNotes.trim() || undefined,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['benchmarks', benchmarkId] });
      setRatingCaseId(null);
      setRatingNotes('');
      pushToast({ title: 'Rating saved', variant: 'success' });
    },
  });

  if (bmkQuery.isLoading) {
    return <div className="glass-panel h-64 animate-pulse rounded-3xl" />;
  }

  const bmk = bmkQuery.data;
  if (!bmk) {
    return (
      <EmptyState
        icon={<ArrowLeft className="h-5 w-5" aria-hidden="true" />}
        title="Comparison not found"
        description="We couldn't find that style comparison."
        ctaLabel="Back to Compare"
        ctaTo="/benchmarks"
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/benchmarks"
          className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-[#5E6A82] hover:text-[#131B2E] dark:text-slate-300 dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to Compare
        </Link>
      </div>

      {bmk.execution_mode === 'demo' ? (
        <DemoModeBanner compact reason="Practicing comparison in Demo Mode." />
      ) : null}

      <section className="glass-panel rounded-3xl p-6">
        <h2 className="text-[20px] font-bold text-[#131B2E] dark:text-white">{bmk.name}</h2>
        <p className="mt-1 text-[13px] text-[#5E6A82] dark:text-slate-300">
          Status: <strong className="capitalize text-[#131B2E] dark:text-white">{bmk.status}</strong>
        </p>

        {bmk.limitations.length > 0 ? (
          <div className="glass-subtle mt-4 rounded-2xl p-3.5 text-[12px] text-[#131B2E] dark:text-slate-300">
            <div className="flex items-center gap-1.5 font-semibold">
              <Info className="h-4 w-4 text-indigo-500" aria-hidden="true" />
              <span>Things to keep in mind</span>
            </div>
            <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[#5E6A82] dark:text-slate-400">
              {bmk.limitations.map((lim, idx) => (
                <li key={idx}>{lim}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        {bmk.condition_summaries.map((cond) => (
          <div key={cond.condition} className="glass-panel space-y-4 rounded-3xl p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-[16px] font-bold text-[#131B2E] dark:text-white">
                {STYLE_NAMES[cond.condition] || cond.condition.replace(/_/g, ' ')}
              </h3>
              <span className="glass-subtle rounded-full px-3 py-0.5 text-[12px] font-semibold tabular-nums text-[#5E6A82] dark:text-slate-300">
                {cond.sample_size} tests
              </span>
            </div>

            <div className="space-y-3 text-[13px]">
              <div>
                <div className="flex justify-between text-[12px]">
                  <span className="text-[#5E6A82] dark:text-slate-300">Avg Polish Score</span>
                  <strong className="tabular-nums text-[#131B2E] dark:text-white">
                    {cond.avg_editor_score !== null ? `${cond.avg_editor_score}/100` : '—'}
                  </strong>
                </div>
                <div className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-white/70 dark:bg-slate-800">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500"
                    style={{ width: `${Math.min(100, cond.avg_editor_score || 0)}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-[12px]">
                  <span className="text-[#5E6A82] dark:text-slate-300">Claims Supported</span>
                  <strong className="tabular-nums text-teal-700 dark:text-teal-300">
                    {formatPercent(cond.avg_evidence_coverage)}
                  </strong>
                </div>
                <div className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-white/70 dark:bg-slate-800">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-teal-400 to-emerald-500"
                    style={{ width: `${Math.round((cond.avg_evidence_coverage || 0) * 100)}%` }}
                  />
                </div>
              </div>
            </div>

            <dl className="grid grid-cols-2 gap-3 border-t border-[#DCE2EC]/70 pt-3 text-[12px] tabular-nums dark:border-slate-800">
              <div>
                <dt className="text-[#5E6A82] dark:text-slate-400">Unverified rate</dt>
                <dd className="font-semibold text-[#131B2E] dark:text-slate-100">
                  {formatPercent(cond.avg_unsupported_rate)}
                </dd>
              </div>
              <div>
                <dt className="text-[#5E6A82] dark:text-slate-400">Conflict rate</dt>
                <dd className="font-semibold text-[#131B2E] dark:text-slate-100">
                  {formatPercent(cond.avg_contradiction_rate)}
                </dd>
              </div>
              <div>
                <dt className="text-[#5E6A82] dark:text-slate-400">Typical speed</dt>
                <dd className="font-semibold text-[#131B2E] dark:text-slate-100">
                  {formatDurationMs(
                    cond.median_duration_ms ? Math.round(cond.median_duration_ms) : null,
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-[#5E6A82] dark:text-slate-400">AI usage / Cost</dt>
                <dd className="font-semibold text-[#131B2E] dark:text-slate-100">
                  {formatTokens(cond.total_tokens)} ·{' '}
                  {formatCostUsd(cond.total_estimated_cost, cond.cost_status, bmk.execution_mode)}
                </dd>
              </div>
            </dl>
          </div>
        ))}
      </section>

      {ratingCaseId ? (
        <div className="glass-panel rounded-3xl border-indigo-400/70 p-5 shadow-xl">
          <h3 className="text-[15px] font-bold text-[#131B2E] dark:text-white">Rate this post</h3>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="human-rating-score" className="block text-[12px] font-semibold">
                Your score (1–5)
              </label>
              <input
                id="human-rating-score"
                type="number"
                min={1}
                max={5}
                step={0.5}
                value={ratingVal}
                onChange={(e) => setRatingVal(parseFloat(e.target.value) || 3)}
                className="mt-1 w-full rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[13px] dark:border-slate-700 dark:bg-slate-900/65"
              />
            </div>
            <div>
              <label htmlFor="human-rating-notes" className="block text-[12px] font-semibold">
                Notes (optional)
              </label>
              <input
                id="human-rating-notes"
                type="text"
                value={ratingNotes}
                onChange={(e) => setRatingNotes(e.target.value)}
                placeholder="What did you like or dislike?"
                className="mt-1 w-full rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[13px] dark:border-slate-700 dark:bg-slate-900/65"
              />
            </div>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setRatingCaseId(null)}
              className="glass-subtle rounded-full px-4 py-1.5 text-[13px]"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => rateMutation.mutate()}
              className="btn-aurora rounded-full px-5 py-1.5 text-[13px] font-semibold"
            >
              Save rating
            </button>
          </div>
        </div>
      ) : null}

      <section className="glass-panel overflow-hidden rounded-3xl">
        <div className="border-b border-[#DCE2EC]/70 px-5 py-3.5 dark:border-slate-800">
          <h3 className="text-[15px] font-bold text-[#131B2E] dark:text-white">
            Topic-by-topic results
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-[12px]">
            <thead className="border-b border-[#DCE2EC]/70 bg-white/45 font-semibold text-[#5E6A82] dark:border-slate-800/80 dark:bg-slate-900/45 dark:text-slate-400">
              <tr>
                <th className="px-4 py-3">Topic</th>
                <th className="px-4 py-3">Style</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Polish</th>
                <th className="px-4 py-3">Supported</th>
                <th className="px-4 py-3 text-right">View</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#DCE2EC]/70 tabular-nums dark:divide-slate-800">
              {bmk.cases.map((c) => (
                <tr key={c.case_id} className="hover:bg-white/45 dark:hover:bg-slate-800/35">
                  <td className="max-w-xs px-4 py-3">
                    <div className="font-semibold text-[#131B2E] dark:text-slate-100">{c.topic}</div>
                  </td>
                  <td className="px-4 py-3">
                    {STYLE_NAMES[c.condition] || c.condition.replace(/_/g, ' ')}
                  </td>
                  <td className="px-4 py-3">
                    <RunStatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-3 font-semibold">
                    {c.editor_score !== null ? `${c.editor_score}/100` : '—'}
                  </td>
                  <td className="px-4 py-3">{formatPercent(c.evidence_coverage)}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <div className="inline-flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setRatingCaseId(c.case_id);
                          setRatingVal(c.human_rating || 4);
                          setRatingNotes(c.human_notes || '');
                        }}
                        className="glass-subtle inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium"
                      >
                        <Star className="h-3 w-3 text-amber-500" aria-hidden="true" />
                        {c.human_rating ? `${c.human_rating}/5` : 'Rate'}
                      </button>
                      {c.run_id ? (
                        <Link
                          to={`/runs/${c.run_id}/studio`}
                          className="btn-aurora rounded-full px-3 py-1 text-[11px] font-semibold"
                        >
                          Open
                        </Link>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

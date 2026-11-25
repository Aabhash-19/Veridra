import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  FileText,
  FolderHeart,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { DemoModeBanner } from '../../components/DemoModeBanner';
import { EmptyState } from '../../components/EmptyState';
import { RunStatusBadge } from '../../components/StatusBadge';
import { api } from '../../lib/api';
import { formatDateTime, formatDurationMs, formatPercent, platformLabel } from '../../lib/format';
import { QUICK_START_EXAMPLES, type SampleBrief } from '../../lib/sampleBriefs';

const PLATFORM_PILLS: Record<string, string> = {
  linkedin:
    'bg-gradient-to-r from-sky-500/15 to-blue-500/15 text-sky-800 border-sky-300/60 dark:text-sky-200 dark:border-sky-400/30',
  x: 'bg-gradient-to-r from-violet-500/15 to-indigo-500/15 text-violet-800 border-violet-300/60 dark:text-violet-200 dark:border-violet-400/30',
  instagram:
    'bg-gradient-to-r from-rose-500/15 to-amber-500/15 text-rose-800 border-rose-300/60 dark:text-rose-200 dark:border-rose-400/30',
};

export function DashboardPage() {
  const navigate = useNavigate();

  const summaryQuery = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: api.getDashboardSummary,
  });

  const runsQuery = useQuery({
    queryKey: ['runs', 'recent'],
    queryFn: () => api.listRuns({ limit: 5, offset: 0 }),
  });

  const projectsQuery = useQuery({
    queryKey: ['projects', 'dashboard'],
    queryFn: () => api.listProjects(4, 0),
  });

  const integrationsQuery = useQuery({
    queryKey: ['integrations'],
    queryFn: api.getIntegrations,
  });

  const summary = summaryQuery.data;
  const recentRuns = runsQuery.data?.items || [];
  const projects = projectsQuery.data?.items || [];
  const integrations = integrationsQuery.data;

  const applySampleBrief = (ex: SampleBrief) => {
    navigate('/runs/new', { state: { prefill: ex } });
  };

  return (
    <div className="space-y-7">
      {integrations && !integrations.llm_configured ? (
        <DemoModeBanner
          reason={
            integrations.demo_mode_env
              ? 'Sample practice mode is active.'
              : 'Live AI keys are not added yet — try Demo Mode anytime or connect keys in Settings.'
          }
        />
      ) : null}

      {/* Colorful Dynamic Hero Showcase */}
      <section className="glass-panel relative overflow-hidden rounded-3xl p-7 sm:p-9">
        <div
          className="pointer-events-none absolute -right-12 -top-16 h-64 w-64 rounded-full bg-gradient-to-br from-indigo-500/25 via-fuchsia-500/20 to-transparent blur-2xl"
          aria-hidden="true"
        />
        <div
          className="pointer-events-none absolute -bottom-20 left-1/4 h-52 w-80 rounded-full bg-gradient-to-tr from-teal-400/20 via-sky-400/15 to-transparent blur-2xl"
          aria-hidden="true"
        />

        <div className="relative grid items-center gap-8 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <div className="inline-flex flex-wrap items-center gap-1.5 rounded-full border border-indigo-300/60 bg-white/70 px-3.5 py-1 text-[11px] font-semibold tracking-wide text-indigo-700 backdrop-blur-md dark:border-indigo-400/30 dark:bg-white/10 dark:text-indigo-200">
              <span>1. Find Facts</span>
              <span className="opacity-40">•</span>
              <span>2. Write</span>
              <span className="opacity-40">•</span>
              <span>3. Polish</span>
              <span className="opacity-40">•</span>
              <span className="text-teal-600 dark:text-teal-300">4. Fact-Check</span>
            </div>

            <h2 className="mt-4 text-[28px] font-bold leading-tight tracking-tight text-[#131B2E] sm:text-[34px] dark:text-white">
              Turn any idea into{' '}
              <span className="aurora-text">verified, ready-to-share</span> content.
            </h2>

            <p className="mt-3 max-w-xl text-[14px] leading-relaxed text-[#5E6A82] dark:text-slate-300">
              Share your topic and audience. Veridra finds trustworthy sources, writes in your voice,
              polishes the flow, and double-checks facts before you publish.
            </p>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link
                to="/runs/new"
                className="btn-aurora inline-flex items-center gap-2 rounded-full px-6 py-3 text-[14px] font-semibold"
              >
                <span>Create a post</span>
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link
                to="/benchmarks"
                className="glass-subtle rounded-full px-5 py-3 text-[14px] font-medium text-[#131B2E] transition hover:bg-white/85 dark:text-slate-100 dark:hover:bg-slate-800/75"
              >
                Compare writing styles
              </Link>
            </div>
          </div>

          {/* Dynamic Layered Floating Showcase */}
          <div className="hidden lg:col-span-5 lg:block" aria-hidden="true">
            <div className="relative space-y-3">
              <div className="glass-tint-indigo rounded-2xl p-4 shadow-md backdrop-blur-xl transition-transform hover:-translate-y-0.5">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-indigo-700 dark:text-indigo-200">
                    <Sparkles className="h-3.5 w-3.5" />
                    Tailored for your channel
                  </span>
                  <div className="flex gap-1.5 text-[10px] font-semibold">
                    <span className="rounded-full bg-sky-500/20 px-2 py-0.5 text-sky-800 dark:text-sky-200">
                      LinkedIn
                    </span>
                    <span className="rounded-full bg-violet-500/20 px-2 py-0.5 text-violet-800 dark:text-violet-200">
                      X Thread
                    </span>
                    <span className="rounded-full bg-rose-500/20 px-2 py-0.5 text-rose-800 dark:text-rose-200">
                      Instagram
                    </span>
                  </div>
                </div>
                <div className="mt-2.5 h-2 w-4/5 rounded-full bg-gradient-to-r from-indigo-400/50 via-violet-400/40 to-pink-400/40" />
                <div className="mt-1.5 h-2 w-3/5 rounded-full bg-indigo-300/40 dark:bg-indigo-400/25" />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="glass-tint-teal rounded-2xl p-3.5 shadow-sm backdrop-blur-xl">
                  <div className="flex items-center gap-1.5 text-[12px] font-semibold text-teal-800 dark:text-teal-200">
                    <ShieldCheck className="h-4 w-4 text-teal-600 dark:text-teal-300" />
                    Source-checked
                  </div>
                  <p className="mt-1 text-[11px] text-teal-900/75 dark:text-teal-200/80">
                    Every claim links back to real sources
                  </p>
                </div>

                <div className="glass-tint-rose rounded-2xl p-3.5 shadow-sm backdrop-blur-xl">
                  <div className="flex items-center gap-1.5 text-[12px] font-semibold text-rose-800 dark:text-rose-200">
                    <TrendingUp className="h-4 w-4 text-rose-600 dark:text-rose-300" />
                    Style polish
                  </div>
                  <p className="mt-1 text-[11px] text-rose-900/75 dark:text-rose-200/80">
                    Hook, clarity &amp; tone refined automatically
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Truthful Colorful Bento Stats (only when runs exist) */}
      {summaryQuery.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="glass-panel h-24 animate-pulse rounded-2xl" />
          ))}
        </div>
      ) : summary && summary.total_runs > 0 ? (
        <section
          aria-label="Your studio overview"
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          <div className="glass-tint-indigo rounded-2xl p-4.5 backdrop-blur-xl transition hover:-translate-y-0.5">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-semibold text-indigo-800 dark:text-indigo-200">
                Posts created
              </span>
              <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
                <FileText className="h-3.5 w-3.5" aria-hidden="true" />
              </span>
            </div>
            <div className="mt-1.5 text-[24px] font-bold tabular-nums text-[#131B2E] dark:text-white">
              {summary.total_runs}
            </div>
            <div className="mt-1 text-[12px] text-[#5E6A82] dark:text-slate-300">
              {summary.completed_runs} clean · {summary.completed_with_warnings_runs} with notes
            </div>
          </div>

          <div className="glass-tint-rose rounded-2xl p-4.5 backdrop-blur-xl transition hover:-translate-y-0.5">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-semibold text-rose-800 dark:text-rose-200">
                Avg polish score
              </span>
              <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-gradient-to-br from-pink-500 to-rose-500 text-white">
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              </span>
            </div>
            <div className="mt-1.5 text-[24px] font-bold tabular-nums text-[#131B2E] dark:text-white">
              {summary.avg_editor_score !== null ? `${summary.avg_editor_score}/100` : '—'}
            </div>
            <div className="mt-1 text-[12px] text-[#5E6A82] dark:text-slate-300">
              Based on {summary.editor_score_sample_size} reviewed post(s)
            </div>
          </div>

          <div className="glass-tint-teal rounded-2xl p-4.5 backdrop-blur-xl transition hover:-translate-y-0.5">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-semibold text-teal-800 dark:text-teal-200">
                Claims supported
              </span>
              <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-gradient-to-br from-teal-400 to-emerald-500 text-white">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
              </span>
            </div>
            <div className="mt-1.5 text-[24px] font-bold tabular-nums text-teal-700 dark:text-teal-300">
              {formatPercent(summary.avg_evidence_coverage)}
            </div>
            <div className="mt-1 text-[12px] text-[#5E6A82] dark:text-slate-300">
              {summary.total_unsupported_claims} unverified · {summary.total_contradicted_claims}{' '}
              flagged
            </div>
          </div>

          <div className="glass-tint-sky rounded-2xl p-4.5 backdrop-blur-xl transition hover:-translate-y-0.5">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-semibold text-sky-800 dark:text-sky-200">
                Typical speed
              </span>
              <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-blue-500 text-white">
                <Clock className="h-3.5 w-3.5" aria-hidden="true" />
              </span>
            </div>
            <div className="mt-1.5 text-[24px] font-bold tabular-nums text-[#131B2E] dark:text-white">
              {formatDurationMs(summary.median_duration_ms)}
            </div>
            <div className="mt-1 text-[12px] text-[#5E6A82] dark:text-slate-300">
              Per finished draft
            </div>
          </div>
        </section>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="space-y-3 lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="text-[16px] font-bold text-[#131B2E] dark:text-white">Recent posts</h2>
            <Link
              to="/runs"
              className="text-[13px] font-semibold text-indigo-600 hover:underline dark:text-indigo-300"
            >
              See all
            </Link>
          </div>

          {runsQuery.isLoading ? (
            <div className="space-y-3">
              {[1, 2].map((i) => (
                <div key={i} className="glass-panel h-20 animate-pulse rounded-2xl" />
              ))}
            </div>
          ) : recentRuns.length === 0 ? (
            <EmptyState
              icon={<FileText className="h-5 w-5" aria-hidden="true" />}
              title="No content runs yet"
              description="Write your first topic or click one of the starter ideas on the right."
              ctaLabel="Create first post"
              ctaTo="/runs/new"
            />
          ) : (
            <div className="space-y-3">
              {recentRuns.map((run) => (
                <Link
                  key={run.run_id}
                  to={
                    run.status === 'completed' || run.status === 'completed_with_warnings'
                      ? `/runs/${run.run_id}/studio`
                      : `/runs/${run.run_id}`
                  }
                  className="glass-panel flex flex-wrap items-center justify-between gap-3 rounded-2xl px-4.5 py-4 transition hover:-translate-y-0.5 hover:border-indigo-400/50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <RunStatusBadge status={run.status} />
                      <span
                        className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${
                          PLATFORM_PILLS[run.platform] || 'glass-subtle text-[#5E6A82]'
                        }`}
                      >
                        {platformLabel(run.platform)}
                      </span>
                      {run.execution_mode === 'demo' ? (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-900 dark:bg-amber-500/20 dark:text-amber-200">
                          DEMO
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-2 truncate text-[14px] font-semibold text-[#131B2E] dark:text-slate-100">
                      {run.topic}
                    </p>
                  </div>
                  <div className="text-right text-[12px] tabular-nums text-[#5E6A82] dark:text-slate-400">
                    <div>{formatDateTime(run.created_at)}</div>
                    <div className="mt-0.5 font-semibold text-[#131B2E] dark:text-slate-200">
                      {run.editor_score !== null
                        ? `${run.editor_score}/100 polish`
                        : formatDurationMs(run.duration_ms)}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>

        <aside className="space-y-5">
          <div className="glass-panel rounded-3xl p-5">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-pink-500 text-white">
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              </span>
              <h2 className="text-[15px] font-bold text-[#131B2E] dark:text-white">
                Quick ideas to try
              </h2>
            </div>
            <div className="mt-3.5 space-y-2.5">
              {QUICK_START_EXAMPLES.map((ex) => (
                <button
                  key={ex.id}
                  type="button"
                  onClick={() => applySampleBrief(ex)}
                  className="glass-subtle w-full rounded-2xl p-3.5 text-left transition hover:-translate-y-0.5 hover:border-indigo-400/55 hover:bg-white/85 dark:hover:bg-slate-800/70"
                >
                  <div className="flex items-center justify-between gap-2 text-[11px] font-semibold">
                    <span className="text-indigo-600 dark:text-indigo-300">{ex.label}</span>
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] ${
                        PLATFORM_PILLS[ex.platform] || ''
                      }`}
                    >
                      {platformLabel(ex.platform)}
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-[13px] font-medium text-[#131B2E] dark:text-slate-200">
                    {ex.topic}
                  </p>
                </button>
              ))}
            </div>
          </div>

          <div className="glass-panel rounded-3xl p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-[14px] font-bold text-[#131B2E] dark:text-white">Connections</h2>
              <Link
                to="/settings"
                className="text-[12px] font-semibold text-indigo-600 hover:underline dark:text-indigo-300"
              >
                Manage
              </Link>
            </div>
            <div className="mt-3 space-y-2.5 text-[13px]">
              <div className="flex items-center justify-between">
                <span className="text-[#5E6A82] dark:text-slate-400">AI Writer</span>
                <span className="flex items-center gap-1.5 font-semibold text-[#131B2E] dark:text-slate-200">
                  {integrations?.llm_configured ? (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5 text-teal-500" aria-hidden="true" />
                      {integrations.llm_model}
                    </>
                  ) : (
                    <span className="text-amber-600 dark:text-amber-300">Demo mode</span>
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#5E6A82] dark:text-slate-400">Web Search</span>
                <span className="flex items-center gap-1.5 font-semibold text-[#131B2E] dark:text-slate-200">
                  {integrations?.search_configured ? (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5 text-teal-500" aria-hidden="true" />
                      Connected
                    </>
                  ) : (
                    <span className="text-amber-600 dark:text-amber-300">Not added yet</span>
                  )}
                </span>
              </div>
            </div>

            {projects.length > 0 ? (
              <div className="mt-4 border-t border-[#DCE2EC]/70 pt-3.5 dark:border-slate-800">
                <div className="flex items-center justify-between text-[12px] font-semibold text-[#5E6A82] dark:text-slate-400">
                  <span>Projects</span>
                  <Link to="/projects" className="text-indigo-600 dark:text-indigo-300">
                    All
                  </Link>
                </div>
                <ul className="mt-2 space-y-1.5">
                  {projects.map((p) => (
                    <li key={p.project_id}>
                      <Link
                        to={`/projects/${p.project_id}`}
                        className="flex items-center justify-between rounded-xl px-2.5 py-1.5 text-[13px] transition hover:bg-white/70 dark:hover:bg-slate-800/70"
                      >
                        <span className="flex items-center gap-2 font-medium text-[#131B2E] dark:text-slate-200">
                          <FolderHeart className="h-3.5 w-3.5 text-rose-500" aria-hidden="true" />
                          {p.name}
                        </span>
                        <span className="tabular-nums text-[12px] text-[#5E6A82] dark:text-slate-400">
                          {p.run_count}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </aside>
      </div>
    </div>
  );
}

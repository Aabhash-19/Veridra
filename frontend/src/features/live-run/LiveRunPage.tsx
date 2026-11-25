import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  FileEdit,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Slash,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { DemoModeBanner } from '../../components/DemoModeBanner';
import { EmptyState } from '../../components/EmptyState';
import { RunStatusBadge } from '../../components/StatusBadge';
import { useToast } from '../../components/toastContext';
import { api } from '../../lib/api';
import { formatDateTime, formatDurationMs, platformLabel } from '../../lib/format';
import type { RunEvent } from '../../lib/types';
import { useRunEvents } from '../../lib/useRunEvents';

type StageVisualStatus =
  | 'waiting'
  | 'active'
  | 'complete'
  | 'retrying'
  | 'warning'
  | 'failed'
  | 'skipped';

interface AgentStageDef {
  id: string;
  label: string;
  subtitle: string;
  nodes: string[];
  icon: typeof Search;
  gradient: string;
}

const MULTI_AGENT_STAGES: AgentStageDef[] = [
  {
    id: 'researcher',
    label: '1. Exploring Sources',
    subtitle: 'Finding trustworthy articles and reading your links',
    nodes: ['plan_research', 'researcher', 'evidence_gate'],
    icon: Search,
    gradient: 'from-sky-400 to-blue-600',
  },
  {
    id: 'writer',
    label: '2. Writing Your Draft',
    subtitle: 'Turning ideas and takeaways into a clean story',
    nodes: ['writer'],
    icon: FileEdit,
    gradient: 'from-indigo-500 to-violet-600',
  },
  {
    id: 'editor',
    label: '3. Polishing Tone & Hook',
    subtitle: 'Making the opening stronger and easier to read',
    nodes: ['editor', 'editor_router'],
    icon: Sparkles,
    gradient: 'from-pink-500 to-rose-500',
  },
  {
    id: 'fact_checker',
    label: '4. Checking Facts',
    subtitle: 'Double-checking claims against retrieved sources',
    nodes: ['fact_checker', 'fact_router'],
    icon: ShieldCheck,
    gradient: 'from-teal-400 to-emerald-500',
  },
  {
    id: 'finalizer',
    label: '5. Saving Final Post',
    subtitle: 'Formatting cleanly for your studio',
    nodes: ['finalizer', 'safe_stop', 'persist_result'],
    icon: CheckCircle2,
    gradient: 'from-indigo-500 via-purple-500 to-teal-400',
  },
];

const SINGLE_AGENT_STAGES: AgentStageDef[] = [
  {
    id: 'researcher',
    label: '1. Exploring Sources',
    subtitle: 'Finding trustworthy articles and reading your links',
    nodes: ['plan_research', 'researcher', 'evidence_gate'],
    icon: Search,
    gradient: 'from-sky-400 to-blue-600',
  },
  {
    id: 'single_agent_run',
    label: '2. Quick Draft',
    subtitle: 'Writing and reviewing your post in one pass',
    nodes: ['single_agent_run'],
    icon: FileEdit,
    gradient: 'from-indigo-500 to-violet-600',
  },
  {
    id: 'finalizer',
    label: '3. Saving Final Post',
    subtitle: 'Formatting cleanly for your studio',
    nodes: ['finalizer', 'safe_stop', 'persist_result'],
    icon: CheckCircle2,
    gradient: 'from-teal-400 to-emerald-500',
  },
];

function deriveStageState(
  stage: AgentStageDef,
  events: RunEvent[],
  runStatus: string,
  currentNode: string | null,
): {
  status: StageVisualStatus;
  latestEvent: RunEvent | null;
  stageEvents: RunEvent[];
} {
  const stageEvents = events.filter((e) => e.node && stage.nodes.includes(e.node));
  const latest = stageEvents.length > 0 ? stageEvents[stageEvents.length - 1] : null;
  const isTerminalRun = ['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(
    runStatus,
  );

  if (!latest) {
    if (currentNode && stage.nodes.includes(currentNode) && !isTerminalRun) {
      return { status: 'active', latestEvent: null, stageEvents };
    }
    return { status: isTerminalRun ? 'skipped' : 'waiting', latestEvent: null, stageEvents };
  }

  if (latest.event_type === 'node.retrying' || latest.status === 'retrying') {
    return { status: 'retrying', latestEvent: latest, stageEvents };
  }
  if (latest.status === 'failed' || latest.event_type === 'run.failed') {
    return { status: 'failed', latestEvent: latest, stageEvents };
  }
  if (latest.status === 'warning' || latest.event_type === 'run.warning') {
    return { status: 'warning', latestEvent: latest, stageEvents };
  }
  if (latest.event_type === 'node.started' || latest.status === 'running') {
    return {
      status: isTerminalRun ? 'complete' : 'active',
      latestEvent: latest,
      stageEvents,
    };
  }
  return { status: 'complete', latestEvent: latest, stageEvents };
}

function StageStatusPill({ status }: { status: StageVisualStatus }) {
  switch (status) {
    case 'active':
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-indigo-700 dark:bg-indigo-500/25 dark:text-indigo-200">
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
          Working
        </span>
      );
    case 'complete':
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-teal-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-teal-800 dark:bg-teal-500/20 dark:text-teal-200">
          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
          Done
        </span>
      );
    case 'retrying':
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/20 px-2.5 py-0.5 text-[12px] font-semibold text-amber-900 dark:text-amber-200">
          <RefreshCw className="h-3 w-3" aria-hidden="true" />
          Retrying
        </span>
      );
    case 'warning':
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-rose-800 dark:text-rose-200">
          <AlertTriangle className="h-3 w-3" aria-hidden="true" />
          Note
        </span>
      );
    case 'failed':
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-red-700 dark:text-red-300">
          <XCircle className="h-3 w-3" aria-hidden="true" />
          Issue
        </span>
      );
    case 'skipped':
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-slate-500/10 px-2.5 py-0.5 text-[12px] font-medium text-[#5E6A82] dark:text-slate-400">
          <Slash className="h-3 w-3" aria-hidden="true" />
          Skipped
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-white/70 px-2.5 py-0.5 text-[12px] font-medium text-[#5E6A82] dark:bg-slate-800 dark:text-slate-400">
          <Clock className="h-3 w-3" aria-hidden="true" />
          Up next
        </span>
      );
  }
}

export function LiveRunPage() {
  const { runId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [expandedStage, setExpandedStage] = useState<string | null>(null);
  const [showRawEvents, setShowRawEvents] = useState(false);
  const [liveElapsedMs, setLiveElapsedMs] = useState<number>(0);

  const runQuery = useQuery({
    queryKey: ['run', runId],
    queryFn: () => api.getRunDetail(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || status === 'queued' || status === 'running') {
        return 2500;
      }
      return false;
    },
  });

  const run = runQuery.data;

  const { events } = useRunEvents({
    runId,
    initialEvents: run?.events,
    runStatus: run?.status,
    onEvent: (evt) => {
      if (
        evt.event_type === 'node.completed' ||
        evt.event_type === 'node.retrying' ||
        evt.event_type === 'run.warning'
      ) {
        queryClient.invalidateQueries({ queryKey: ['run', runId] });
      }
    },
    onTerminal: () => {
      queryClient.invalidateQueries({ queryKey: ['run', runId] });
      queryClient.invalidateQueries({ queryKey: ['runs'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
    },
  });

  useEffect(() => {
    if (!run || !run.started_at) return;
    if (run.metrics.duration_ms !== null && run.metrics.duration_ms !== undefined) {
      setLiveElapsedMs(run.metrics.duration_ms);
      return;
    }
    if (run.status !== 'running' && run.status !== 'queued') return;

    const startMs = new Date(run.started_at).getTime();
    const tick = () => setLiveElapsedMs(Math.max(0, Date.now() - startMs));
    tick();
    const handle = window.setInterval(tick, 250);
    return () => window.clearInterval(handle);
  }, [run]);

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelRun(runId),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['run', runId] });
      pushToast({
        title: res.cancellation_accepted ? 'Stopping your draft' : 'Already finished',
        description: res.message,
        variant: 'info',
      });
    },
  });

  const retryMutation = useMutation({
    mutationFn: () => api.retryRun(runId),
    onSuccess: (res) => {
      pushToast({ title: 'Starting a fresh attempt', variant: 'success' });
      navigate(`/runs/${res.run_id}`);
    },
  });

  const stages = useMemo(
    () =>
      run?.workflow_strategy === 'single_agent' ? SINGLE_AGENT_STAGES : MULTI_AGENT_STAGES,
    [run?.workflow_strategy],
  );

  if (runQuery.isLoading) {
    return (
      <div className="space-y-4">
        <div className="glass-panel h-32 animate-pulse rounded-3xl" />
        <div className="glass-panel h-64 animate-pulse rounded-3xl" />
      </div>
    );
  }

  if (!run) {
    return (
      <EmptyState
        icon={<AlertTriangle className="h-5 w-5" aria-hidden="true" />}
        title="Post not found"
        description="We couldn't find this draft."
        ctaLabel="Back to My Posts"
        ctaTo="/runs"
      />
    );
  }

  const isRunning = run.status === 'queued' || run.status === 'running';
  const latestEvent = events.length > 0 ? events[events.length - 1] : null;
  const hasArtifact = run.artifacts.length > 0 || Boolean(run.latest_artifact);

  const stageStates = stages.map((st) => ({
    stage: st,
    derived: deriveStageState(st, events, run.status, run.current_node),
  }));
  const completedCount = stageStates.filter((s) => s.derived.status === 'complete').length;
  const progressPercent = Math.round((completedCount / stages.length) * 100);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {run.execution_mode === 'demo' ? (
        <DemoModeBanner compact reason="Practicing with sample data." />
      ) : null}

      {/* Header + Gradient Progress Ribbon */}
      <section className="glass-panel relative overflow-hidden rounded-3xl p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <RunStatusBadge status={run.status} />
              <span className="glass-subtle rounded-full px-3 py-0.5 text-[12px] font-semibold text-[#131B2E] dark:text-slate-200">
                {platformLabel(run.platform)}
              </span>
            </div>
            <h2 className="mt-2.5 text-[20px] font-bold text-[#131B2E] dark:text-white">
              {String(run.request?.topic || '')}
            </h2>
            {latestEvent ? (
              <p className="mt-1.5 text-[13px] text-[#5E6A82] dark:text-slate-300">
                {latestEvent.message}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {isRunning ? (
              <button
                type="button"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
                className="inline-flex items-center gap-1.5 rounded-full border border-rose-300 bg-rose-50/80 px-4 py-2 text-[13px] font-semibold text-rose-800 hover:bg-rose-100 disabled:opacity-60 dark:border-rose-400/40 dark:bg-rose-500/15 dark:text-rose-200"
              >
                <Slash className="h-4 w-4" aria-hidden="true" />
                <span>{cancelMutation.isPending ? 'Stopping...' : 'Stop'}</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => retryMutation.mutate()}
                disabled={retryMutation.isPending}
                className="glass-subtle inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-[13px] font-semibold text-[#131B2E] hover:bg-white/85 dark:text-slate-200"
              >
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                <span>Try again</span>
              </button>
            )}

            {hasArtifact ? (
              <Link
                to={`/runs/${run.run_id}/studio`}
                className="btn-aurora inline-flex items-center gap-1.5 rounded-full px-5 py-2 text-[13px] font-semibold"
              >
                <span>Open Post Studio</span>
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            ) : null}
          </div>
        </div>

        {/* Truthful Stage Completion Track */}
        <div className="mt-5">
          <div className="flex items-center justify-between text-[12px] font-semibold text-[#5E6A82] dark:text-slate-300">
            <span>
              {completedCount} of {stages.length} steps finished
            </span>
            <span className="tabular-nums">{progressPercent}%</span>
          </div>
          <div className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-white/70 dark:bg-slate-800/80">
            <div
              className="h-full rounded-full bg-gradient-to-r from-sky-400 via-indigo-500 to-teal-400 transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Simple 4-stat summary */}
        <div className="mt-5 grid gap-3 border-t border-[#DCE2EC]/70 pt-4 sm:grid-cols-2 lg:grid-cols-4 dark:border-slate-800">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-[#5E6A82] dark:text-slate-400">
              Time taken
            </div>
            <div className="mt-0.5 text-[16px] font-bold tabular-nums text-[#131B2E] dark:text-white">
              {formatDurationMs(run.metrics.duration_ms ?? liveElapsedMs)}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-[#5E6A82] dark:text-slate-400">
              Sources found
            </div>
            <div className="mt-0.5 text-[16px] font-bold tabular-nums text-[#131B2E] dark:text-white">
              {run.sources.length}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-[#5E6A82] dark:text-slate-400">
              Polish pass
            </div>
            <div className="mt-0.5 text-[15px] font-bold tabular-nums text-[#131B2E] dark:text-white">
              Revision {run.metrics.editor_revision_count} of 3
            </div>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-[#5E6A82] dark:text-slate-400">
              Fact check
            </div>
            <div className="mt-0.5 text-[15px] font-bold tabular-nums text-[#131B2E] dark:text-white">
              Pass {run.metrics.fact_remediation_count} of 2
            </div>
          </div>
        </div>
      </section>

      {run.status === 'failed' ? (
        <div
          role="alert"
          className="glass-tint-rose rounded-3xl p-5 text-[#131B2E] backdrop-blur-xl dark:text-slate-100"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-rose-600 dark:text-rose-300" aria-hidden="true" />
              <div>
                <h3 className="text-[15px] font-bold text-rose-900 dark:text-rose-200">
                  Couldn&apos;t finish this draft right now
                </h3>
                <p className="mt-1 text-[13px] text-[#5E6A82] dark:text-slate-200">
                  {run.errors?.[0]?.message ||
                    run.warnings?.[run.warnings.length - 1]?.message ||
                    'Something interrupted generation. Try another AI assistant or retry in a moment.'}
                </p>
              </div>
            </div>
            <Link
              to="/runs/new"
              className="glass-subtle rounded-full px-4 py-1.5 text-[12px] font-semibold text-[#131B2E] hover:bg-white/90 dark:text-white"
            >
              Start fresh &amp; pick another AI
            </Link>
          </div>
        </div>
      ) : null}

      {/* Colorful Dynamic Step Tracker */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[16px] font-bold text-[#131B2E] dark:text-white">
            Step-by-step progress
          </h3>
          <button
            type="button"
            onClick={() => setShowRawEvents((v) => !v)}
            className="text-[12px] font-semibold text-indigo-600 hover:underline dark:text-indigo-300"
          >
            {showRawEvents ? 'Hide detailed log' : `Detailed log (${events.length})`}
          </button>
        </div>

        <div className="space-y-3">
          {stageStates.map(({ stage, derived }) => {
            const Icon = stage.icon;
            const isOpen = expandedStage === stage.id;
            const isActive = derived.status === 'active' || derived.status === 'retrying';

            return (
              <div
                key={stage.id}
                className={`glass-panel rounded-2xl p-4 transition-all ${
                  isActive ? 'ring-2 ring-indigo-400/70 shadow-lg' : ''
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3.5">
                    <div
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${stage.gradient} text-white shadow-sm ${
                        isActive ? 'pulse-soft' : ''
                      }`}
                    >
                      <Icon className="h-4.5 w-4.5" aria-hidden="true" />
                    </div>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[15px] font-bold text-[#131B2E] dark:text-white">
                          {stage.label}
                        </span>
                        <StageStatusPill status={derived.status} />
                      </div>
                      <p className="mt-0.5 text-[13px] text-[#5E6A82] dark:text-slate-300">
                        {derived.latestEvent ? derived.latestEvent.message : stage.subtitle}
                      </p>
                    </div>
                  </div>

                  {derived.stageEvents.length > 0 ? (
                    <button
                      type="button"
                      onClick={() => setExpandedStage(isOpen ? null : stage.id)}
                      aria-expanded={isOpen}
                      aria-label={`Toggle details for ${stage.label}`}
                      className="glass-subtle rounded-full p-1.5 text-[#5E6A82] hover:text-[#131B2E] dark:text-slate-300"
                    >
                      {isOpen ? (
                        <ChevronUp className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <ChevronDown className="h-4 w-4" aria-hidden="true" />
                      )}
                    </button>
                  ) : null}
                </div>

                {isOpen && derived.stageEvents.length > 0 ? (
                  <ul className="mt-3 space-y-2 border-t border-[#DCE2EC]/70 pt-3 dark:border-slate-800">
                    {derived.stageEvents.map((ev) => (
                      <li
                        key={ev.event_id}
                        className="flex flex-wrap items-baseline justify-between gap-2 text-[12px]"
                      >
                        <span className="text-[#131B2E] dark:text-slate-200">{ev.message}</span>
                        <span className="tabular-nums text-[#5E6A82] dark:text-slate-400">
                          {formatDateTime(ev.created_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            );
          })}
        </div>

        {showRawEvents ? (
          <div className="glass-panel max-h-72 overflow-y-auto rounded-3xl p-4">
            <ol className="space-y-2.5">
              {events.map((ev) => (
                <li
                  key={ev.event_id}
                  className="border-l-2 border-indigo-400/50 pl-3 text-[12px]"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-[#131B2E] dark:text-slate-200">
                      Step {ev.sequence}
                    </span>
                    <span className="tabular-nums text-[#5E6A82] dark:text-slate-400">
                      {formatDateTime(ev.created_at)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[#5E6A82] dark:text-slate-300">{ev.message}</p>
                </li>
              ))}
            </ol>
          </div>
        ) : null}
      </section>
    </div>
  );
}

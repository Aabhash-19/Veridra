import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText, Search, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState } from '../../components/EmptyState';
import { RunStatusBadge } from '../../components/StatusBadge';
import { useToast } from '../../components/toastContext';
import { api } from '../../lib/api';
import {
  formatCostUsd,
  formatDateTime,
  formatDurationMs,
  formatPercent,
  platformLabel,
} from '../../lib/format';

export function RunsListPage() {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [statusFilter, setStatusFilter] = useState('');
  const [platformFilter, setPlatformFilter] = useState('');
  const [projectFilter, setProjectFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 15;

  const projectsQuery = useQuery({
    queryKey: ['projects', 'filter'],
    queryFn: () => api.listProjects(50, 0),
  });

  const runsQuery = useQuery({
    queryKey: ['runs', { statusFilter, platformFilter, projectFilter, searchQuery, offset }],
    queryFn: () =>
      api.listRuns({
        status: statusFilter || undefined,
        platform: platformFilter || undefined,
        project_id: projectFilter || undefined,
        search: searchQuery || undefined,
        limit,
        offset,
      }),
  });

  const deleteMutation = useMutation({
    mutationFn: api.deleteRun,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      pushToast({ title: 'Post removed', variant: 'info' });
    },
  });

  const runs = runsQuery.data?.items || [];
  const total = runsQuery.data?.total || 0;
  const projects = projectsQuery.data?.items || [];

  return (
    <div className="space-y-5">
      <div className="glass-panel grid gap-3 rounded-2xl p-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#5E6A82]"
            aria-hidden="true"
          />
          <input
            type="search"
            aria-label="Search posts by topic"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setOffset(0);
            }}
            placeholder="Search your posts..."
            className="w-full rounded-xl border border-[#DCE2EC]/90 bg-white/80 py-2 pl-9 pr-3 text-[13px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
          />
        </div>

        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setOffset(0);
          }}
          className="rounded-xl border border-[#DCE2EC]/90 bg-white/80 px-3 py-2 text-[13px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
        >
          <option value="">All statuses</option>
          <option value="queued">Starting</option>
          <option value="running">Writing</option>
          <option value="completed">Ready</option>
          <option value="completed_with_warnings">Needs review notes</option>
          <option value="failed">Issue / Stopped</option>
          <option value="cancelled">Cancelled</option>
        </select>

        <select
          aria-label="Filter by platform"
          value={platformFilter}
          onChange={(e) => {
            setPlatformFilter(e.target.value);
            setOffset(0);
          }}
          className="rounded-xl border border-[#DCE2EC]/90 bg-white/80 px-3 py-2 text-[13px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
        >
          <option value="">All channels</option>
          <option value="linkedin">LinkedIn</option>
          <option value="x">X Thread</option>
          <option value="instagram">Instagram</option>
        </select>

        <select
          aria-label="Filter by project"
          value={projectFilter}
          onChange={(e) => {
            setProjectFilter(e.target.value);
            setOffset(0);
          }}
          className="rounded-xl border border-[#DCE2EC]/90 bg-white/80 px-3 py-2 text-[13px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
        >
          <option value="">All folders</option>
          {projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {runsQuery.isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="glass-panel h-20 animate-pulse rounded-2xl" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-5 w-5" aria-hidden="true" />}
          title="No matching posts yet"
          description="Try clearing a filter or start writing something fresh."
          ctaLabel="Create a post"
          ctaTo="/runs/new"
        />
      ) : (
        <div className="glass-panel overflow-hidden rounded-3xl">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-[13px]">
              <thead className="border-b border-[#DCE2EC]/70 bg-white/45 text-[12px] font-semibold text-[#5E6A82] dark:border-slate-800/80 dark:bg-slate-900/45 dark:text-slate-400">
                <tr>
                  <th className="px-5 py-3.5">Status &amp; Topic</th>
                  <th className="px-4 py-3.5">Channel</th>
                  <th className="px-4 py-3.5">Quality &amp; Sources</th>
                  <th className="px-4 py-3.5">Time &amp; Cost</th>
                  <th className="px-5 py-3.5 text-right">Open</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#DCE2EC]/70 dark:divide-slate-800/80">
                {runs.map((run) => (
                  <tr key={run.run_id} className="transition hover:bg-white/45 dark:hover:bg-slate-800/35">
                    <td className="max-w-md px-5 py-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <RunStatusBadge status={run.status} />
                        {run.execution_mode === 'demo' ? (
                          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-900 dark:bg-amber-500/20 dark:text-amber-200">
                            DEMO
                          </span>
                        ) : null}
                      </div>
                      <Link
                        to={`/runs/${run.run_id}`}
                        className="mt-1.5 block truncate font-semibold text-[#131B2E] hover:text-indigo-600 dark:text-slate-100 dark:hover:text-indigo-300"
                      >
                        {run.topic}
                      </Link>
                      <div className="mt-0.5 text-[12px] text-[#5E6A82] dark:text-slate-400">
                        {formatDateTime(run.created_at)}
                      </div>
                    </td>

                    <td className="px-4 py-4 whitespace-nowrap">
                      <span className="glass-subtle rounded-full px-3 py-1 text-[12px] font-semibold text-[#131B2E] dark:text-slate-200">
                        {platformLabel(run.platform)}
                      </span>
                    </td>

                    <td className="px-4 py-4 tabular-nums whitespace-nowrap">
                      <div>
                        Polish:{' '}
                        <strong>
                          {run.editor_score !== null ? `${run.editor_score}/100` : '—'}
                        </strong>
                      </div>
                      <div className="text-[12px] text-[#5E6A82] dark:text-slate-400">
                        Supported: {formatPercent(run.evidence_coverage)}
                      </div>
                    </td>

                    <td className="px-4 py-4 tabular-nums whitespace-nowrap">
                      <div>{formatDurationMs(run.duration_ms)}</div>
                      <div className="text-[12px] text-[#5E6A82] dark:text-slate-400">
                        {formatCostUsd(run.estimated_cost, run.cost_status, run.execution_mode)}
                      </div>
                    </td>

                    <td className="px-5 py-4 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-2">
                        <Link
                          to={`/runs/${run.run_id}`}
                          className="glass-subtle rounded-full px-3 py-1 text-[12px] font-medium text-[#131B2E] hover:bg-white/85 dark:text-slate-200"
                        >
                          Progress
                        </Link>
                        {run.status === 'completed' ||
                        run.status === 'completed_with_warnings' ||
                        run.status === 'failed' ? (
                          <Link
                            to={`/runs/${run.run_id}/studio`}
                            className="btn-aurora rounded-full px-3.5 py-1 text-[12px] font-semibold"
                          >
                            Edit Post
                          </Link>
                        ) : null}
                        <button
                          type="button"
                          aria-label={`Delete post ${run.run_id}`}
                          onClick={() => deleteMutation.mutate(run.run_id)}
                          className="rounded-full p-1.5 text-[#5E6A82] hover:bg-rose-500/15 hover:text-rose-700 dark:text-slate-400 dark:hover:text-rose-300"
                        >
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {total > limit ? (
            <div className="flex items-center justify-between border-t border-[#DCE2EC]/70 px-5 py-3 text-[12px] text-[#5E6A82] dark:border-slate-800 dark:text-slate-400">
              <span className="tabular-nums">
                Showing {offset + 1}–{Math.min(offset + limit, total)} of {total}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  className="glass-subtle rounded-full px-3 py-1 font-medium text-[#131B2E] disabled:opacity-40 dark:text-slate-200"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={offset + limit >= total}
                  onClick={() => setOffset(offset + limit)}
                  className="glass-subtle rounded-full px-3 py-1 font-medium text-[#131B2E] disabled:opacity-40 dark:text-slate-200"
                >
                  Next
                </button>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

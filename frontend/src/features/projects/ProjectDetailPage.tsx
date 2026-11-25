import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Save } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { EmptyState } from '../../components/EmptyState';
import { RunStatusBadge } from '../../components/StatusBadge';
import { useToast } from '../../components/toastContext';
import { api } from '../../lib/api';
import { formatDateTime, formatDurationMs, platformLabel } from '../../lib/format';
import type { DepthType, PlatformType } from '../../lib/types';

export function ProjectDetailPage() {
  const { projectId = '' } = useParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();

  const projQuery = useQuery({
    queryKey: ['projects', projectId],
    queryFn: () => api.getProject(projectId),
    enabled: Boolean(projectId),
  });

  const runsQuery = useQuery({
    queryKey: ['runs', { projectId }],
    queryFn: () => api.listRuns({ project_id: projectId, limit: 25 }),
    enabled: Boolean(projectId),
  });

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [platform, setPlatform] = useState<PlatformType>('linkedin');
  const [audience, setAudience] = useState('');
  const [tone, setTone] = useState('');
  const [depth, setDepth] = useState<DepthType>('standard');

  useEffect(() => {
    if (!projQuery.data) return;
    const p = projQuery.data;
    setName(p.name);
    setDescription(p.description || '');
    setPlatform(p.defaults.platform);
    setAudience(p.defaults.audience || '');
    setTone(p.defaults.tone || '');
    setDepth(p.defaults.depth);
  }, [projQuery.data]);

  const updateMutation = useMutation({
    mutationFn: () =>
      api.updateProject(projectId, {
        name: name.trim(),
        description: description.trim() || null,
        defaults: {
          platform,
          audience: audience.trim() || null,
          tone: tone.trim() || null,
          depth,
          language: projQuery.data?.defaults.language || 'en',
          required_points: projQuery.data?.defaults.required_points || [],
          prohibited_points: projQuery.data?.defaults.prohibited_points || [],
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects', projectId] });
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      pushToast({ title: 'Folder settings saved', variant: 'success' });
    },
  });

  const handleSave = (e: FormEvent) => {
    e.preventDefault();
    updateMutation.mutate();
  };

  if (projQuery.isLoading) {
    return <div className="glass-panel h-48 animate-pulse rounded-3xl" />;
  }

  if (!projQuery.data) {
    return (
      <EmptyState
        icon={<ArrowLeft className="h-5 w-5" aria-hidden="true" />}
        title="Folder not found"
        description="This folder may have been deleted."
        ctaLabel="Back to folders"
        ctaTo="/projects"
      />
    );
  }

  const runs = runsQuery.data?.items || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/projects"
          className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-[#5E6A82] hover:text-[#131B2E] dark:text-slate-300 dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to folders
        </Link>
        <Link
          to={`/runs/new?projectId=${projectId}`}
          className="btn-aurora inline-flex items-center gap-1.5 rounded-full px-4.5 py-2 text-[13px] font-semibold"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          New post in folder
        </Link>
      </div>

      <form onSubmit={handleSave} className="glass-panel rounded-3xl p-6">
        <h2 className="text-[16px] font-bold text-[#131B2E] dark:text-white">Folder defaults</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="edit-proj-name" className="block text-[13px] font-semibold">
              Folder name
            </label>
            <input
              id="edit-proj-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/80 bg-white/75 px-3 py-2 text-[14px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/60"
            />
          </div>
          <div>
            <label htmlFor="edit-proj-platform" className="block text-[13px] font-semibold">
              Default channel
            </label>
            <select
              id="edit-proj-platform"
              value={platform}
              onChange={(e) => setPlatform(e.target.value as PlatformType)}
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/80 bg-white/75 px-3 py-2 text-[14px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/60"
            >
              <option value="linkedin">LinkedIn</option>
              <option value="x">X Thread</option>
              <option value="instagram">Instagram</option>
            </select>
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="edit-proj-desc" className="block text-[13px] font-semibold">
              Description
            </label>
            <textarea
              id="edit-proj-desc"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/80 bg-white/75 px-3 py-2 text-[14px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/60"
            />
          </div>
          <div>
            <label htmlFor="edit-proj-audience" className="block text-[13px] font-semibold">
              Target audience
            </label>
            <input
              id="edit-proj-audience"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/80 bg-white/75 px-3 py-2 text-[14px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/60"
            />
          </div>
          <div>
            <label htmlFor="edit-proj-tone" className="block text-[13px] font-semibold">
              Default vibe
            </label>
            <input
              id="edit-proj-tone"
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/80 bg-white/75 px-3 py-2 text-[14px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/60"
            />
          </div>
          <div>
            <label htmlFor="edit-proj-depth" className="block text-[13px] font-semibold">
              Default length
            </label>
            <select
              id="edit-proj-depth"
              value={depth}
              onChange={(e) => setDepth(e.target.value as DepthType)}
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/80 bg-white/75 px-3 py-2 text-[14px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/60"
            >
              <option value="concise">Short</option>
              <option value="standard">Balanced</option>
              <option value="deep">Deep Dive</option>
            </select>
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="submit"
            disabled={updateMutation.isPending}
            className="btn-aurora inline-flex items-center gap-1.5 rounded-full px-5 py-2 text-[13px] font-semibold"
          >
            <Save className="h-4 w-4" aria-hidden="true" />
            {updateMutation.isPending ? 'Saving...' : 'Save changes'}
          </button>
        </div>
      </form>

      <section className="space-y-3">
        <h2 className="text-[16px] font-bold text-[#131B2E] dark:text-white">
          Posts in this folder
        </h2>
        {runs.length === 0 ? (
          <EmptyState
            icon={<Plus className="h-5 w-5" aria-hidden="true" />}
            title="No posts in this folder yet"
            description="Create a post using these saved settings."
            ctaLabel="Create post"
            ctaTo={`/runs/new?projectId=${projectId}`}
          />
        ) : (
          <div className="space-y-2.5">
            {runs.map((r) => (
              <Link
                key={r.run_id}
                to={
                  r.status === 'completed' || r.status === 'completed_with_warnings'
                    ? `/runs/${r.run_id}/studio`
                    : `/runs/${r.run_id}`
                }
                className="glass-panel flex flex-wrap items-center justify-between gap-3 rounded-2xl p-4 transition hover:-translate-y-0.5 hover:border-indigo-400/50"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <RunStatusBadge status={r.status} />
                    <span className="text-[12px] text-[#5E6A82] dark:text-slate-400">
                      {platformLabel(r.platform)}
                    </span>
                  </div>
                  <div className="mt-1 font-semibold text-[#131B2E] dark:text-slate-100">
                    {r.topic}
                  </div>
                </div>
                <div className="text-right text-[12px] tabular-nums text-[#5E6A82] dark:text-slate-400">
                  <div>{formatDateTime(r.created_at)}</div>
                  <div>{formatDurationMs(r.duration_ms)}</div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

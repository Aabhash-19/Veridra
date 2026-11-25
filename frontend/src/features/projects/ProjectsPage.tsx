import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FolderHeart, Plus, Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState } from '../../components/EmptyState';
import { useToast } from '../../components/toastContext';
import { api, ApiClientError } from '../../lib/api';
import { formatDateTime, platformLabel } from '../../lib/format';
import type { DepthType, PlatformType } from '../../lib/types';

const FOLDER_GRADIENTS = [
  'from-indigo-500 to-violet-500',
  'from-rose-400 to-amber-400',
  'from-teal-400 to-cyan-500',
  'from-fuchsia-500 to-pink-500',
];

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [platform, setPlatform] = useState<PlatformType>('linkedin');
  const [audience, setAudience] = useState('');
  const [tone, setTone] = useState('friendly, crisp');
  const [depth, setDepth] = useState<DepthType>('standard');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const projectsQuery = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.listProjects(50, 0),
  });

  const createMutation = useMutation({
    mutationFn: api.createProject,
    onSuccess: (proj) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      setShowForm(false);
      setName('');
      setDescription('');
      setAudience('');
      setErrorMsg(null);
      pushToast({
        title: 'Folder created',
        description: proj.name,
        variant: 'success',
      });
    },
    onError: (err) => {
      setErrorMsg(err instanceof ApiClientError ? err.message : 'Could not create folder.');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: api.deleteProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      pushToast({ title: 'Folder deleted', variant: 'info' });
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (name.trim().length < 2) {
      setErrorMsg('Please enter a name with at least 2 characters.');
      return;
    }
    createMutation.mutate({
      name: name.trim(),
      description: description.trim() || null,
      defaults: {
        platform,
        audience: audience.trim() || null,
        tone: tone.trim() || null,
        depth,
        language: 'en',
        required_points: [],
        prohibited_points: [],
      },
    });
  };

  const projects = projectsQuery.data?.items || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-[14px] text-[#5E6A82] dark:text-slate-300">
          Group posts by content series or brand so your audience, vibe, and channel are ready in
          one click.
        </p>
        <button
          type="button"
          onClick={() => setShowForm((v) => !v)}
          className="btn-aurora inline-flex items-center gap-1.5 rounded-full px-4.5 py-2 text-[13px] font-semibold"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span>{showForm ? 'Cancel' : 'New project'}</span>
        </button>
      </div>

      {showForm ? (
        <form onSubmit={handleSubmit} className="glass-panel rounded-3xl p-6">
          <h2 className="text-[16px] font-bold text-[#131B2E] dark:text-white">
            Create content folder
          </h2>
          {errorMsg ? (
            <div className="mt-3 rounded-xl border border-rose-300 bg-rose-50 px-3.5 py-2 text-[13px] text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/15 dark:text-rose-200">
              {errorMsg}
            </div>
          ) : null}

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="proj-name" className="block text-[13px] font-semibold">
                Folder name *
              </label>
              <input
                id="proj-name"
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., Weekly Creator Tips"
                className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/80 bg-white/75 px-3 py-2 text-[14px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/60"
              />
            </div>

            <div>
              <label htmlFor="proj-platform" className="block text-[13px] font-semibold">
                Default channel
              </label>
              <select
                id="proj-platform"
                value={platform}
                onChange={(e) => setPlatform(e.target.value as PlatformType)}
                className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/80 bg-white/75 px-3 py-2 text-[14px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/60"
              >
                <option value="linkedin">LinkedIn post</option>
                <option value="x">X thread</option>
                <option value="instagram">Instagram caption</option>
              </select>
            </div>

            <div className="sm:col-span-2">
              <label htmlFor="proj-desc" className="block text-[13px] font-semibold">
                What is this series about?
              </label>
              <textarea
                id="proj-desc"
                rows={2}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional notes about this series..."
                className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/80 bg-white/75 px-3 py-2 text-[14px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/60"
              />
            </div>

            <div>
              <label htmlFor="proj-audience" className="block text-[13px] font-semibold">
                Target audience
              </label>
              <input
                id="proj-audience"
                type="text"
                value={audience}
                onChange={(e) => setAudience(e.target.value)}
                placeholder="e.g., Solo creators & indie makers"
                className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/80 bg-white/75 px-3 py-2 text-[14px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/60"
              />
            </div>

            <div>
              <label htmlFor="proj-tone" className="block text-[13px] font-semibold">
                Default vibe
              </label>
              <input
                id="proj-tone"
                type="text"
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/80 bg-white/75 px-3 py-2 text-[14px] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/60"
              />
            </div>

            <div>
              <label htmlFor="proj-depth" className="block text-[13px] font-semibold">
                Default length
              </label>
              <select
                id="proj-depth"
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

          <div className="mt-5 flex justify-end gap-3">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="glass-subtle rounded-full px-4 py-2 text-[13px] font-medium"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="btn-aurora rounded-full px-5 py-2 text-[13px] font-semibold disabled:opacity-60"
            >
              {createMutation.isPending ? 'Saving...' : 'Create folder'}
            </button>
          </div>
        </form>
      ) : null}

      {projectsQuery.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {[1, 2].map((i) => (
            <div key={i} className="glass-panel h-36 animate-pulse rounded-3xl" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <EmptyState
          icon={<FolderHeart className="h-5 w-5" aria-hidden="true" />}
          title="No folders yet"
          description="Create a folder to save your favorite channel, voice, and audience settings."
          ctaLabel="Create first folder"
          onAction={() => setShowForm(true)}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {projects.map((p, idx) => (
            <div
              key={p.project_id}
              className="glass-panel flex flex-col justify-between rounded-3xl p-5 transition hover:-translate-y-0.5 hover:border-indigo-400/50"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <span
                      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${
                        FOLDER_GRADIENTS[idx % FOLDER_GRADIENTS.length]
                      } text-white shadow-xs`}
                    >
                      <FolderHeart className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <Link
                      to={`/projects/${p.project_id}`}
                      className="text-[16px] font-bold text-[#131B2E] hover:text-indigo-600 dark:text-white dark:hover:text-indigo-300"
                    >
                      {p.name}
                    </Link>
                  </div>
                  <button
                    type="button"
                    aria-label={`Delete project ${p.name}`}
                    onClick={() => deleteMutation.mutate(p.project_id)}
                    className="rounded-full p-1.5 text-[#5E6A82] hover:bg-rose-500/15 hover:text-rose-700 dark:text-slate-400 dark:hover:text-rose-300"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
                {p.description ? (
                  <p className="mt-2.5 text-[13px] text-[#5E6A82] dark:text-slate-300">
                    {p.description}
                  </p>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
                  <span className="glass-subtle rounded-full px-2.5 py-0.5 font-semibold text-[#131B2E] dark:text-slate-200">
                    {platformLabel(p.defaults.platform)}
                  </span>
                  <span className="glass-subtle rounded-full px-2.5 py-0.5 text-[#5E6A82] dark:text-slate-300">
                    {p.defaults.depth === 'concise'
                      ? 'Short'
                      : p.defaults.depth === 'deep'
                        ? 'Deep Dive'
                        : 'Balanced'}
                  </span>
                  {p.defaults.audience ? (
                    <span className="glass-subtle truncate rounded-full px-2.5 py-0.5 text-[#5E6A82] dark:text-slate-300">
                      {p.defaults.audience}
                    </span>
                  ) : null}
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-[#DCE2EC]/70 pt-3 text-[12px] text-[#5E6A82] dark:border-slate-800 dark:text-slate-400">
                <span className="tabular-nums font-medium">{p.run_count} post(s)</span>
                <span>{formatDateTime(p.updated_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

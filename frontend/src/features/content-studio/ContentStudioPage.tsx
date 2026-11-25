import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  ExternalLink,
  FileText,
  Gauge,
  RefreshCw,
  Save,
  Send,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { DemoModeBanner } from '../../components/DemoModeBanner';
import { EmptyState } from '../../components/EmptyState';
import { FormattedPostPreview } from '../../components/FormattedPostPreview';
import {
  ClaimStatusBadge,
  RunStatusBadge,
  SourceStatusBadge,
} from '../../components/StatusBadge';
import { useToast } from '../../components/toastContext';
import { api, ApiClientError } from '../../lib/api';
import {
  downloadTextFile,
  formatCostUsd,
  formatDateTime,
  formatDurationMs,
  formatPercent,
  formatTokens,
  platformLabel,
} from '../../lib/format';
import { buildComposerUrl, formatForSocialPlatform } from '../../lib/socialFormat';
import type { ClaimRecord, PlatformType } from '../../lib/types';

type StudioTab = 'draft' | 'evidence' | 'fact_checks' | 'activity' | 'metrics';

const ACTION_LABELS: Record<string, string> = {
  keep: 'Keep as written',
  qualify: 'Add softer context',
  rewrite: 'Rewrite carefully',
  remove: 'Consider removing',
};

const PLATFORM_CARD_ACCENTS: Record<string, string> = {
  linkedin: 'from-sky-500 to-blue-600',
  x: 'from-violet-500 to-indigo-600',
  instagram: 'from-pink-500 via-rose-500 to-amber-400',
};

export function ContentStudioPage() {
  const { runId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();

  const [activeTab, setActiveTab] = useState<StudioTab>('draft');
  const [selectedArtifactId, setSelectedArtifactId] = useState<string>('');
  const [editTitle, setEditTitle] = useState('');
  const [editBody, setEditBody] = useState('');
  const [includeSourcesOnCopy, setIncludeSourcesOnCopy] = useState(true);
  const [copyWarningOpen, setCopyWarningOpen] = useState(false);
  const [claimFilter, setClaimFilter] = useState<'all' | 'attention'>('all');
  const [highlightedSourceId, setHighlightedSourceId] = useState<string | null>(null);
  const [expandedSourceIds, setExpandedSourceIds] = useState<Record<string, boolean>>({});
  const [showTechMetrics, setShowTechMetrics] = useState(false);
  const [previewMode, setPreviewMode] = useState<'styled' | 'social'>('styled');
  const [publishingPlatform, setPublishingPlatform] = useState<PlatformType | null>(null);

  const runQuery = useQuery({
    queryKey: ['run', runId],
    queryFn: () => api.getRunDetail(runId),
    enabled: Boolean(runId),
  });

  const run = runQuery.data;

  const artifactQuery = useQuery({
    queryKey: ['artifact', selectedArtifactId],
    queryFn: () => api.getArtifact(selectedArtifactId),
    enabled: Boolean(selectedArtifactId),
  });

  useEffect(() => {
    if (!run) return;
    if (!selectedArtifactId && run.latest_artifact) {
      setSelectedArtifactId(run.latest_artifact.artifact_id);
    }
  }, [run, selectedArtifactId]);

  const currentArtifact = artifactQuery.data || run?.latest_artifact || null;

  useEffect(() => {
    if (!currentArtifact) return;
    setEditTitle(currentArtifact.title);
    setEditBody(currentArtifact.body_markdown);
  }, [currentArtifact]);

  const saveEditMutation = useMutation({
    mutationFn: () => {
      if (!currentArtifact) throw new Error('No draft selected');
      return api.saveArtifactEdit(currentArtifact.artifact_id, {
        title: editTitle.trim(),
        body_markdown: editBody,
        expected_parent_version_id: currentArtifact.artifact_id,
      });
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['run', runId] });
      setSelectedArtifactId(created.artifact_id);
      pushToast({
        title: `Saved Version ${created.version}`,
        description: 'Your original AI version is still safely kept in the dropdown.',
        variant: 'success',
      });
    },
    onError: (err) => {
      pushToast({
        title: 'Save failed',
        description: err instanceof ApiClientError ? err.message : 'Unable to save edits.',
        variant: 'error',
      });
    },
  });

  const regenerateMutation = useMutation({
    mutationFn: () => api.retryRun(runId),
    onSuccess: (res) => {
      pushToast({ title: 'Writing a fresh version', variant: 'info' });
      navigate(`/runs/${res.run_id}`);
    },
  });

  if (runQuery.isLoading) {
    return <div className="glass-panel h-72 animate-pulse rounded-3xl" />;
  }

  if (!run) {
    return (
      <EmptyState
        icon={<FileText className="h-5 w-5" aria-hidden="true" />}
        title="Post not found"
        description="We couldn't find this draft."
        ctaLabel="Back to My Posts"
        ctaTo="/runs"
      />
    );
  }

  const attentionClaims: ClaimRecord[] = run.claims.filter((c) =>
    ['partially_supported', 'uncertain', 'unsupported', 'contradicted'].includes(c.status),
  );
  const filteredClaims = claimFilter === 'attention' ? attentionClaims : run.claims;
  const hasUnresolvedWarnings =
    run.status === 'completed_with_warnings' || attentionClaims.length > 0;

  const isDirty = Boolean(
    currentArtifact &&
      (editBody !== currentArtifact.body_markdown || editTitle !== currentArtifact.title),
  );

  const performCopy = async () => {
    try {
      const formatted = formatForSocialPlatform(editBody, {
        includeSources: includeSourcesOnCopy,
      });
      await navigator.clipboard.writeText(formatted);
      setCopyWarningOpen(false);
      pushToast({
        title: 'Copied to clipboard',
        description: includeSourcesOnCopy
          ? 'Post-ready text (bold, italics & bullets) and sources copied.'
          : 'Post-ready text (bold, italics & bullets) copied.',
        variant: 'success',
      });
    } catch {
      pushToast({
        title: 'Clipboard copy failed',
        description: 'Try Export .md or .txt instead.',
        variant: 'error',
      });
    }
  };

  const handleOneClickPublish = async (targetPlatform: PlatformType) => {
    if (!currentArtifact) return;
    setPublishingPlatform(targetPlatform);
    const formattedFull = formatForSocialPlatform(editBody, {
      includeSources: includeSourcesOnCopy,
    });
    const xFirstSegment =
      targetPlatform === 'x' && currentArtifact.thread_segments.length > 0
        ? formatForSocialPlatform(currentArtifact.thread_segments[0], { includeSources: false })
        : formattedFull;

    try {
      await navigator.clipboard.writeText(formattedFull);
    } catch {
      // Clipboard may be blocked in non-focused contexts; still proceed with publish/composer.
    }

    try {
      const res = await api.publishArtifact(currentArtifact.artifact_id, {
        platform: targetPlatform,
        text: targetPlatform === 'x' ? xFirstSegment : formattedFull,
      });
      if (res.published && res.post_url) {
        window.open(res.post_url, '_blank', 'noopener,noreferrer');
        pushToast({
          title: `Published to ${platformLabel(targetPlatform)}`,
          description: res.message,
          variant: 'success',
        });
      } else {
        const targetUrl =
          res.composer_url || buildComposerUrl(targetPlatform, targetPlatform === 'x' ? xFirstSegment : formattedFull);
        window.open(targetUrl, '_blank', 'noopener,noreferrer');
        pushToast({
          title:
            targetPlatform === 'instagram'
              ? 'Caption copied — paste in Instagram'
              : `${platformLabel(targetPlatform)} composer opened`,
          description: res.message,
          variant: 'success',
        });
      }
    } catch (err) {
      if (err instanceof ApiClientError && err.code === 'SOCIAL_PUBLISH_FAILED') {
        pushToast({
          title: `Direct ${platformLabel(targetPlatform)} publish failed`,
          description: err.message,
          variant: 'error',
        });
      } else {
        window.open(
          buildComposerUrl(targetPlatform, targetPlatform === 'x' ? xFirstSegment : formattedFull),
          '_blank',
          'noopener,noreferrer',
        );
        pushToast({
          title: `${platformLabel(targetPlatform)} composer opened`,
          description: 'Post-ready text copied to your clipboard.',
          variant: 'success',
        });
      }
    } finally {
      setPublishingPlatform(null);
    }
  };

  const handleCopyClick = () => {
    if (hasUnresolvedWarnings) {
      setCopyWarningOpen(true);
    } else {
      void performCopy();
    }
  };

  const handleExport = async (fmt: 'md' | 'txt') => {
    if (!currentArtifact) return;
    try {
      const { text, filename } = await api.exportArtifact(currentArtifact.artifact_id, fmt);
      downloadTextFile(
        filename,
        text,
        fmt === 'md' ? 'text/markdown;charset=utf-8' : 'text/plain;charset=utf-8',
      );
      pushToast({ title: `Downloaded ${filename}`, variant: 'success' });
    } catch {
      pushToast({ title: 'Download failed', variant: 'error' });
    }
  };

  const openEvidenceForSource = (evidenceId: string) => {
    const ev = run.evidence_items.find((item) => item.evidence_id === evidenceId);
    if (ev) {
      setHighlightedSourceId(ev.source_id);
      setActiveTab('evidence');
    }
  };

  const wordCount = editBody.split(/\s+/).filter(Boolean).length;
  const charCount = editBody.length;
  const channelGradient = PLATFORM_CARD_ACCENTS[run.platform] || 'from-indigo-500 to-violet-500';

  return (
    <div className="space-y-5">
      {run.execution_mode === 'demo' ? (
        <DemoModeBanner compact reason="Created in Demo Mode using sample practice text." />
      ) : null}

      {/* Studio Header */}
      <section className="glass-panel rounded-3xl p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Link
                to={`/runs/${run.run_id}`}
                className="inline-flex items-center gap-1 text-[12px] font-semibold text-[#5E6A82] hover:text-[#131B2E] dark:text-slate-300 dark:hover:text-white"
              >
                <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
                Progress
              </Link>
              <span className="text-[#DCE2EC] dark:text-slate-700">•</span>
              <RunStatusBadge status={run.status} />
              <span
                className={`inline-flex items-center rounded-full bg-gradient-to-r ${channelGradient} px-3 py-0.5 text-[11px] font-semibold text-white shadow-xs`}
              >
                {platformLabel(run.platform)}
              </span>
              <span className="glass-subtle inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[12px] font-medium text-[#131B2E] dark:text-slate-200">
                <ShieldCheck className="h-3.5 w-3.5 text-teal-500" aria-hidden="true" />
                Checked against sources
              </span>
            </div>

            <h2 className="mt-2.5 text-[21px] font-bold text-[#131B2E] dark:text-white">
              {currentArtifact?.title || String(run.request?.topic || 'Post Studio')}
            </h2>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {run.artifacts.length > 0 ? (
              <select
                aria-label="Select artifact version"
                value={currentArtifact?.artifact_id || ''}
                onChange={(e) => setSelectedArtifactId(e.target.value)}
                className="glass-subtle rounded-full px-3 py-1.5 text-[13px] font-medium text-[#131B2E] dark:text-slate-100"
              >
                {run.artifacts.map((a) => (
                  <option key={a.artifact_id} value={a.artifact_id}>
                    Version {a.version} · {a.created_by === 'user' ? 'Your edit' : 'AI draft'}
                  </option>
                ))}
              </select>
            ) : null}

            <button
              type="button"
              onClick={() => regenerateMutation.mutate()}
              disabled={regenerateMutation.isPending}
              className="glass-subtle inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[13px] font-semibold text-[#131B2E] hover:bg-white/85 dark:text-slate-200"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Write fresh take</span>
            </button>
          </div>
        </div>

        {currentArtifact?.differs_from_agent_approved ? (
          <div className="glass-tint-indigo mt-3 rounded-2xl px-4 py-2.5 text-[12px] text-[#131B2E] dark:text-slate-200">
            <strong>Version {currentArtifact.version}</strong> includes your personal edits.
            Original verified sources and fact checks are still preserved in the tabs below.
          </div>
        ) : null}
      </section>

      {/* Colorful Pill Tabs */}
      <div
        role="tablist"
        aria-label="Post Studio sections"
        className="glass-panel flex flex-wrap gap-1.5 rounded-2xl p-1.5"
      >
        {(
          [
            { id: 'draft', label: 'Write & Edit', icon: FileText },
            { id: 'evidence', label: `Sources (${run.sources.length})`, icon: ExternalLink },
            {
              id: 'fact_checks',
              label: `Fact Checks (${run.claims.length})`,
              icon: ShieldCheck,
            },
            { id: 'activity', label: `History (${run.events.length})`, icon: Activity },
            { id: 'metrics', label: 'Stats & Metrics', icon: Gauge },
          ] as const
        ).map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              role="tab"
              type="button"
              aria-selected={active}
              onClick={() => setActiveTab(tab.id)}
              className={`inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-[13px] font-semibold transition ${
                active
                  ? 'btn-aurora shadow-sm'
                  : 'text-[#5E6A82] hover:bg-white/70 hover:text-[#131B2E] dark:text-slate-300 dark:hover:bg-slate-800/70 dark:hover:text-white'
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Warning confirmation dialog */}
      {copyWarningOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="copy-warn-title"
          className="glass-panel rounded-3xl border-amber-300/80 bg-amber-50/90 p-5 shadow-xl dark:border-amber-500/40 dark:bg-amber-950/70"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle
              className="mt-0.5 h-5 w-5 shrink-0 text-amber-700 dark:text-amber-300"
              aria-hidden="true"
            />
            <div className="flex-1">
              <h3
                id="copy-warn-title"
                className="text-[15px] font-bold text-amber-950 dark:text-amber-100"
              >
                Review unresolved claims before copying
              </h3>
              <p className="mt-1 text-[13px] text-amber-900 dark:text-amber-200">
                {attentionClaims.length} point(s) in this post have notes in Fact Checks. Take a
                quick look before publishing!
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void performCopy()}
                  className="btn-aurora rounded-full px-4 py-1.5 text-[13px] font-semibold"
                >
                  Copy anyway
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCopyWarningOpen(false);
                    setActiveTab('fact_checks');
                  }}
                  className="glass-subtle rounded-full border-amber-400/70 px-4 py-1.5 text-[13px] font-semibold text-amber-950 dark:text-amber-200"
                >
                  Inspect Fact Checks
                </button>
                <button
                  type="button"
                  onClick={() => setCopyWarningOpen(false)}
                  className="px-3 py-1.5 text-[13px] text-[#5E6A82] dark:text-slate-300"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* TAB 1: DRAFT */}
      {activeTab === 'draft' ? (
        !currentArtifact ? (
          <EmptyState
            icon={<FileText className="h-5 w-5" aria-hidden="true" />}
            title="No draft finished yet"
            description="Check the History or Sources tabs to see what stopped this run."
          />
        ) : (
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="glass-panel space-y-4 rounded-3xl p-6 lg:col-span-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-[12px] text-[#5E6A82] dark:text-slate-400">
                  <span className="font-semibold text-[#131B2E] dark:text-slate-200">
                    Version {currentArtifact.version}
                  </span>
                  <span>·</span>
                  <span className="tabular-nums">{wordCount} words</span>
                  <span>·</span>
                  <span className="tabular-nums">{charCount} chars</span>
                </div>

                <button
                  type="button"
                  disabled={!isDirty || saveEditMutation.isPending}
                  onClick={() => saveEditMutation.mutate()}
                  className="btn-aurora inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-[13px] font-semibold disabled:opacity-45"
                >
                  <Save className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{saveEditMutation.isPending ? 'Saving...' : 'Save new version'}</span>
                </button>
              </div>

              <div>
                <label
                  htmlFor="studio-title"
                  className="block text-[12px] font-semibold text-[#5E6A82] dark:text-slate-300"
                >
                  Headline / Title
                </label>
                <input
                  id="studio-title"
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-[#DCE2EC]/90 bg-white/80 px-3.5 py-2 text-[15px] font-semibold text-[#131B2E] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/65 dark:text-white"
                />
              </div>

              <div>
                <label
                  htmlFor="studio-body"
                  className="block text-[12px] font-semibold text-[#5E6A82] dark:text-slate-300"
                >
                  Post body
                </label>
                <textarea
                  id="studio-body"
                  rows={16}
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  className="mt-1 w-full rounded-2xl border border-[#DCE2EC]/90 bg-white/80 px-4 py-3.5 font-sans text-[14px] leading-relaxed text-[#131B2E] backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
                />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#DCE2EC]/70 pt-4 dark:border-slate-800">
                <label className="flex cursor-pointer items-center gap-2 text-[12px] text-[#5E6A82] dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={includeSourcesOnCopy}
                    onChange={(e) => setIncludeSourcesOnCopy(e.target.checked)}
                    className="rounded border-[#DCE2EC]"
                  />
                  <span>Include source links when copying</span>
                </label>

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={publishingPlatform !== null}
                    onClick={() => void handleOneClickPublish(run.platform)}
                    className="btn-aurora inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-[13px] font-semibold shadow-sm disabled:opacity-60"
                  >
                    <Send className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>
                      {publishingPlatform === run.platform
                        ? 'Publishing...'
                        : `1-Click Post to ${platformLabel(run.platform)}`}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={handleCopyClick}
                    className="glass-subtle inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[13px] font-semibold text-[#131B2E] hover:bg-white/90 dark:text-slate-200"
                  >
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Copy</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleExport('md')}
                    className="glass-subtle inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[13px] font-semibold text-[#131B2E] hover:bg-white/90 dark:text-slate-200"
                  >
                    <Download className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Export .md</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleExport('txt')}
                    className="glass-subtle inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[13px] font-semibold text-[#131B2E] hover:bg-white/90 dark:text-slate-200"
                  >
                    <Download className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Export .txt</span>
                  </button>
                </div>
              </div>
            </div>

            <aside className="space-y-4">
              {/* Styled Channel Preview */}
              <div className="glass-panel rounded-3xl p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br ${channelGradient} text-xs font-bold text-white shadow-xs`}
                    >
                      V
                    </span>
                    <div>
                      <div className="text-[13px] font-bold text-[#131B2E] dark:text-white">
                        Your Creator Post
                      </div>
                      <div className="text-[11px] text-[#5E6A82] dark:text-slate-400">
                        {platformLabel(run.platform)} preview
                      </div>
                    </div>
                  </div>

                  <div className="glass-subtle inline-flex rounded-full p-0.5 text-[11px] font-semibold">
                    <button
                      type="button"
                      onClick={() => setPreviewMode('styled')}
                      className={`rounded-full px-2.5 py-1 transition ${
                        previewMode === 'styled'
                          ? 'bg-indigo-500 text-white shadow-xs'
                          : 'text-[#5E6A82] dark:text-slate-300'
                      }`}
                    >
                      Styled
                    </button>
                    <button
                      type="button"
                      onClick={() => setPreviewMode('social')}
                      className={`rounded-full px-2.5 py-1 transition ${
                        previewMode === 'social'
                          ? 'bg-indigo-500 text-white shadow-xs'
                          : 'text-[#5E6A82] dark:text-slate-300'
                      }`}
                    >
                      Social text
                    </button>
                  </div>
                </div>

                {run.platform === 'x' && currentArtifact.thread_segments.length > 0 ? (
                  <div className="mt-4 space-y-2.5">
                    {currentArtifact.thread_segments.map((seg, idx) => (
                      <div key={idx} className="glass-subtle rounded-2xl p-3 text-[13px]">
                        {previewMode === 'styled' ? (
                          <FormattedPostPreview content={seg} />
                        ) : (
                          <p className="whitespace-pre-wrap text-[#131B2E] dark:text-slate-200">
                            {formatForSocialPlatform(seg, { includeSources: false })}
                          </p>
                        )}
                        <div className="mt-1.5 text-right text-[11px] tabular-nums text-[#5E6A82] dark:text-slate-400">
                          Post {idx + 1} · {seg.length} chars
                        </div>
                      </div>
                    ))}
                  </div>
                ) : previewMode === 'styled' ? (
                  <div className="glass-subtle mt-4 max-h-96 overflow-y-auto rounded-2xl p-4">
                    <FormattedPostPreview content={editBody} />
                  </div>
                ) : (
                  <div className="glass-subtle mt-4 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-2xl p-3.5 text-[13px] leading-relaxed text-[#131B2E] dark:text-slate-200">
                    {formatForSocialPlatform(editBody, { includeSources: includeSourcesOnCopy })}
                  </div>
                )}

                <div className="mt-3 flex flex-wrap gap-1.5 border-t border-[#DCE2EC]/60 pt-3 dark:border-slate-800">
                  {(['linkedin', 'x', 'instagram'] as const).map((plat) => (
                    <button
                      key={plat}
                      type="button"
                      disabled={publishingPlatform !== null}
                      onClick={() => void handleOneClickPublish(plat)}
                      className="glass-subtle inline-flex items-center gap-1 rounded-full px-3 py-1 text-[11px] font-semibold text-[#131B2E] hover:bg-white/90 dark:text-slate-200"
                    >
                      <Send className="h-3 w-3 text-indigo-500" aria-hidden="true" />
                      <span>Post to {platformLabel(plat)}</span>
                    </button>
                  ))}
                </div>
              </div>

              {attentionClaims.length > 0 ? (
                <div className="glass-tint-rose rounded-3xl p-4.5 backdrop-blur-xl">
                  <div className="flex items-center gap-2 text-[14px] font-bold text-rose-900 dark:text-rose-200">
                    <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                    <span>{attentionClaims.length} point(s) to double-check</span>
                  </div>
                  <p className="mt-1 text-[12px] text-rose-900/80 dark:text-rose-200/80">
                    Some details couldn&apos;t be fully backed up by sources.
                  </p>
                  <button
                    type="button"
                    onClick={() => setActiveTab('fact_checks')}
                    className="mt-2.5 text-[12px] font-bold text-indigo-600 hover:underline dark:text-indigo-300"
                  >
                    Open Fact Checks →
                  </button>
                </div>
              ) : run.claims.length > 0 ? (
                <div className="glass-tint-teal rounded-3xl p-4.5 text-[13px] backdrop-blur-xl">
                  <div className="flex items-center gap-2 font-bold text-teal-800 dark:text-teal-200">
                    <Check className="h-4 w-4" aria-hidden="true" />
                    All {run.claims.length} checked claim(s) supported
                  </div>
                </div>
              ) : null}
            </aside>
          </div>
        )
      ) : null}

      {/* TAB 2: EVIDENCE / SOURCES */}
      {activeTab === 'evidence' ? (
        <div className="space-y-4">
          {run.research_brief?.open_questions && run.research_brief.open_questions.length > 0 ? (
            <div className="glass-panel rounded-2xl border-amber-300/70 bg-amber-50/75 p-4 text-[13px] text-amber-950 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100">
              <strong className="font-semibold">Things sources didn&apos;t cover:</strong>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[12px]">
                {run.research_brief.open_questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {run.sources.length === 0 ? (
            <EmptyState
              icon={<ExternalLink className="h-5 w-5" aria-hidden="true" />}
              title="No web sources saved"
              description="No links were pulled or included for this draft."
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {run.sources.map((src) => {
                const evItems = run.evidence_items.filter((e) => e.source_id === src.source_id);
                const isHighlighted = highlightedSourceId === src.source_id;
                const isExpanded = Boolean(expandedSourceIds[src.source_id]);
                const rawExcerpt =
                  src.fetched_text_excerpt || src.snippet || src.fetch_error || 'No preview available.';
                return (
                  <article
                    key={src.source_id}
                    className={`glass-panel rounded-3xl p-5 transition ${
                      isHighlighted ? 'border-indigo-500 ring-2 ring-indigo-500/35' : ''
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <SourceStatusBadge status={src.status} />
                      <span className="glass-subtle rounded-full px-2.5 py-0.5 text-[11px] font-medium text-[#5E6A82] dark:text-slate-300">
                        {src.publisher}
                      </span>
                    </div>

                    <h3 className="mt-2.5 text-[15px] font-bold text-[#131B2E] dark:text-white">
                      {src.title}
                    </h3>
                    <p className="text-[12px] text-[#5E6A82] dark:text-slate-400">
                      Read {formatDateTime(src.accessed_at)}
                    </p>

                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-flex items-center gap-1 break-all text-[12px] font-medium text-indigo-600 hover:underline dark:text-indigo-300"
                    >
                      <span>{src.url}</span>
                      <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
                    </a>

                    <div className="glass-subtle mt-3 rounded-2xl p-3.5 text-[13px] text-[#131B2E] dark:text-slate-200">
                      <p className={isExpanded ? '' : 'line-clamp-3'}>{rawExcerpt}</p>
                      {rawExcerpt.length > 180 ? (
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedSourceIds((prev) => ({
                              ...prev,
                              [src.source_id]: !isExpanded,
                            }))
                          }
                          className="mt-1.5 text-[12px] font-semibold text-indigo-600 hover:underline dark:text-indigo-300"
                        >
                          {isExpanded ? 'Show less' : 'Read full snippet'}
                        </button>
                      ) : null}
                    </div>

                    {evItems.length > 0 ? (
                      <div className="mt-3 space-y-1.5 border-t border-[#DCE2EC]/70 pt-2.5 dark:border-slate-800">
                        {evItems.map((ev) => (
                          <div
                            key={ev.evidence_id}
                            className="text-[12px] text-[#5E6A82] dark:text-slate-300"
                          >
                            <span className="font-semibold text-teal-600 dark:text-teal-300">
                              Key quote:
                            </span>{' '}
                            <span className="line-clamp-2 inline">{ev.quote_or_paraphrase}</span>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          )}
        </div>
      ) : null}

      {/* TAB 3: FACT CHECKS */}
      {activeTab === 'fact_checks' ? (
        <div className="space-y-4">
          <div className="glass-panel flex flex-wrap items-center justify-between gap-3 rounded-2xl px-4.5 py-3.5">
            <p className="text-[13px] text-[#5E6A82] dark:text-slate-300">
              Every statement checked strictly against the sources found for this post.
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setClaimFilter('all')}
                className={`rounded-full px-3.5 py-1.5 text-[12px] font-semibold ${
                  claimFilter === 'all'
                    ? 'btn-aurora'
                    : 'glass-subtle text-[#5E6A82] dark:text-slate-300'
                }`}
              >
                All ({run.claims.length})
              </button>
              <button
                type="button"
                onClick={() => setClaimFilter('attention')}
                className={`rounded-full px-3.5 py-1.5 text-[12px] font-semibold ${
                  claimFilter === 'attention'
                    ? 'bg-gradient-to-r from-rose-500 to-orange-400 text-white'
                    : 'glass-subtle text-[#5E6A82] dark:text-slate-300'
                }`}
              >
                Needs review ({attentionClaims.length})
              </button>
            </div>
          </div>

          {filteredClaims.length === 0 ? (
            <EmptyState
              icon={<ShieldCheck className="h-5 w-5" aria-hidden="true" />}
              title={claimFilter === 'attention' ? 'Everything looks good!' : 'No claims checked'}
              description="No flagged statements in this view."
            />
          ) : (
            <div className="space-y-3">
              {filteredClaims.map((claim) => (
                <article key={claim.claim_id} className="glass-panel rounded-3xl p-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <ClaimStatusBadge status={claim.status} />
                    <span className="glass-subtle rounded-full px-3 py-0.5 text-[11px] font-semibold text-[#131B2E] dark:text-slate-200">
                      {ACTION_LABELS[claim.recommended_action] || claim.recommended_action}
                    </span>
                  </div>

                  <p className="mt-3 text-[14px] font-bold text-[#131B2E] dark:text-white">
                    {claim.claim_text}
                  </p>
                  <p className="mt-1 text-[13px] text-[#5E6A82] dark:text-slate-300">
                    {claim.explanation}
                  </p>

                  {claim.supporting_evidence_ids.length > 0 ||
                  claim.contradicting_evidence_ids.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {claim.supporting_evidence_ids.map((eid) => (
                        <button
                          key={eid}
                          type="button"
                          onClick={() => openEvidenceForSource(eid)}
                          className="rounded-full border border-teal-400/50 bg-teal-500/15 px-3 py-1 text-[12px] font-semibold text-teal-800 hover:bg-teal-500/25 dark:text-teal-200"
                        >
                          Supports: {eid}
                        </button>
                      ))}
                      {claim.contradicting_evidence_ids.map((eid) => (
                        <button
                          key={eid}
                          type="button"
                          onClick={() => openEvidenceForSource(eid)}
                          className="rounded-full border border-rose-400/50 bg-rose-500/15 px-3 py-1 text-[12px] font-semibold text-rose-800 dark:text-rose-200"
                        >
                          Conflicts: {eid}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {/* TAB 4: ACTIVITY / HISTORY */}
      {activeTab === 'activity' ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="glass-panel rounded-3xl p-5">
            <h3 className="text-[15px] font-bold text-[#131B2E] dark:text-white">
              How this post was created
            </h3>
            <ol className="mt-4 space-y-3">
              {run.events.map((ev) => (
                <li
                  key={ev.event_id}
                  className="border-l-2 border-indigo-400/50 pl-3 text-[13px]"
                >
                  <div className="flex items-center justify-between gap-2 text-[12px]">
                    <span className="font-semibold text-indigo-600 dark:text-indigo-300">
                      Step {ev.sequence}
                    </span>
                    <span className="tabular-nums text-[#5E6A82] dark:text-slate-400">
                      {formatDateTime(ev.created_at)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[#131B2E] dark:text-slate-200">{ev.message}</p>
                </li>
              ))}
            </ol>
          </div>

          <div className="space-y-4">
            {run.editor_result ? (
              <div className="glass-panel rounded-3xl p-5">
                <div className="flex items-center justify-between">
                  <h3 className="inline-flex items-center gap-1.5 text-[15px] font-bold text-[#131B2E] dark:text-white">
                    <Sparkles className="h-4 w-4 text-pink-500" aria-hidden="true" />
                    Polish score
                  </h3>
                  <span className="aurora-text text-[18px] font-bold tabular-nums">
                    {run.editor_result.score}/100
                  </span>
                </div>
                <p className="mt-1.5 text-[13px] text-[#5E6A82] dark:text-slate-300">
                  {run.editor_result.summary}
                </p>
                <div className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
                  {Object.entries(run.editor_result.score_breakdown || {}).map(([k, v]) => (
                    <div
                      key={k}
                      className="glass-subtle flex items-center justify-between rounded-xl px-3 py-2"
                    >
                      <span className="capitalize text-[#5E6A82] dark:text-slate-300">
                        {k.replace('_', ' ')}
                      </span>
                      <strong className="tabular-nums text-[#131B2E] dark:text-white">{v}</strong>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* TAB 5: STATS & METRICS */}
      {activeTab === 'metrics' ? (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="glass-tint-sky rounded-2xl p-4 backdrop-blur-xl">
              <div className="text-[12px] font-semibold text-sky-800 dark:text-sky-200">
                Total time
              </div>
              <div className="mt-1 text-[20px] font-bold tabular-nums text-[#131B2E] dark:text-white">
                {formatDurationMs(run.metrics.duration_ms)}
              </div>
            </div>
            <div className="glass-tint-indigo rounded-2xl p-4 backdrop-blur-xl">
              <div className="text-[12px] font-semibold text-indigo-800 dark:text-indigo-200">
                AI words processed
              </div>
              <div className="mt-1 text-[20px] font-bold tabular-nums text-[#131B2E] dark:text-white">
                {formatTokens(run.metrics.total_tokens)}
              </div>
            </div>
            <div className="glass-tint-rose rounded-2xl p-4 backdrop-blur-xl">
              <div className="text-[12px] font-semibold text-rose-800 dark:text-rose-200">
                Estimated API cost
              </div>
              <div className="mt-1 text-[20px] font-bold tabular-nums text-[#131B2E] dark:text-white">
                {formatCostUsd(
                  run.metrics.estimated_cost,
                  run.metrics.cost_status,
                  run.execution_mode,
                )}
              </div>
            </div>
            <div className="glass-tint-teal rounded-2xl p-4 backdrop-blur-xl">
              <div className="text-[12px] font-semibold text-teal-800 dark:text-teal-200">
                Claims supported
              </div>
              <div className="mt-1 text-[20px] font-bold tabular-nums text-teal-700 dark:text-teal-300">
                {formatPercent(run.quality.evidence_coverage)}
              </div>
            </div>
          </div>

          <div className="glass-panel rounded-3xl p-5">
            <button
              type="button"
              onClick={() => setShowTechMetrics((v) => !v)}
              className="flex w-full items-center justify-between text-left text-[13px] font-semibold text-[#131B2E] dark:text-white"
            >
              <span>Detailed step-by-step breakdown</span>
              {showTechMetrics ? (
                <ChevronUp className="h-4 w-4 text-[#5E6A82]" aria-hidden="true" />
              ) : (
                <ChevronDown className="h-4 w-4 text-[#5E6A82]" aria-hidden="true" />
              )}
            </button>

            {showTechMetrics ? (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full border-collapse text-left text-[12px]">
                  <thead className="border-b border-[#DCE2EC]/70 text-[#5E6A82] dark:border-slate-800 dark:text-slate-400">
                    <tr>
                      <th className="px-3 py-2.5">Step</th>
                      <th className="px-3 py-2.5">AI Model</th>
                      <th className="px-3 py-2.5">Time</th>
                      <th className="px-3 py-2.5">Usage</th>
                      <th className="px-3 py-2.5">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#DCE2EC]/60 tabular-nums dark:divide-slate-800">
                    {run.node_metrics.map((m) => (
                      <tr key={m.metric_id}>
                        <td className="px-3 py-2.5 font-medium capitalize">
                          {m.node_name.replace(/_/g, ' ')} (#{m.attempt})
                        </td>
                        <td className="px-3 py-2.5 text-[#5E6A82] dark:text-slate-300">
                          {m.model || 'Check'}
                        </td>
                        <td className="px-3 py-2.5">{formatDurationMs(m.duration_ms)}</td>
                        <td className="px-3 py-2.5">
                          {m.total_tokens !== null ? m.total_tokens.toLocaleString() : '—'}
                        </td>
                        <td className="px-3 py-2.5 capitalize">{m.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

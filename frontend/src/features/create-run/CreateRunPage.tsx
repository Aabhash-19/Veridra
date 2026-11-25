import { useMutation, useQuery } from '@tanstack/react-query';
import {
  ChevronDown,
  ChevronUp,
  Eye,
  Link as LinkIcon,
  Plus,
  Send,
  Sparkles,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { DemoModeBanner } from '../../components/DemoModeBanner';
import { ModelSelector } from '../../components/ModelSelector';
import { useToast } from '../../components/toastContext';
import { api, ApiClientError } from '../../lib/api';
import { platformLabel } from '../../lib/format';
import { DEFAULT_MODEL_ID, getSavedPreferredModel, resolveActiveModelId } from '../../lib/models';
import { QUICK_START_EXAMPLES, type SampleBrief } from '../../lib/sampleBriefs';
import type {
  ContentRequestPayload,
  DepthType,
  PlatformType,
  WorkflowStrategyType,
} from '../../lib/types';

const GOAL_OPTIONS = [
  'Share helpful tips & insights',
  'Explain a concept clearly',
  'Compare options & trade-offs',
  'Recap an event or trend',
  'Share career advice',
  'Custom',
];

const TONE_OPTIONS = ['friendly', 'warm', 'crisp', 'educational', 'persuasive'];

const PLATFORM_OPTIONS: {
  value: PlatformType;
  title: string;
  desc: string;
  activeClass: string;
  dot: string;
}[] = [
  {
    value: 'linkedin',
    title: 'LinkedIn post',
    desc: 'Thoughtful story or insights',
    activeClass:
      'border-sky-400/80 bg-sky-50/80 ring-1 ring-sky-400/50 dark:border-sky-400/60 dark:bg-sky-500/20',
    dot: 'from-sky-400 to-blue-600',
  },
  {
    value: 'x',
    title: 'X thread',
    desc: 'Short connected posts',
    activeClass:
      'border-violet-400/80 bg-violet-50/80 ring-1 ring-violet-400/50 dark:border-violet-400/60 dark:bg-violet-500/20',
    dot: 'from-violet-500 to-indigo-600',
  },
  {
    value: 'instagram',
    title: 'Instagram caption',
    desc: 'Catchy, scannable story',
    activeClass:
      'border-rose-400/80 bg-rose-50/80 ring-1 ring-rose-400/50 dark:border-rose-400/60 dark:bg-rose-500/20',
    dot: 'from-pink-500 via-rose-500 to-amber-400',
  },
];

const LENGTH_LABELS: { value: DepthType; label: string }[] = [
  { value: 'concise', label: 'Short' },
  { value: 'standard', label: 'Balanced' },
  { value: 'deep', label: 'Deep Dive' },
];

function validateHttpUrl(raw: string): string | null {
  try {
    const parsed = new URL(raw.trim());
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return 'Only http:// and https:// links are allowed.';
    }
    return null;
  } catch {
    return 'Please paste a full link starting with https:// or http://.';
  }
}

export function CreateRunPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { pushToast } = useToast();

  const integrationsQuery = useQuery({
    queryKey: ['integrations'],
    queryFn: api.getIntegrations,
  });
  const projectsQuery = useQuery({
    queryKey: ['projects', 'select'],
    queryFn: () => api.listProjects(50, 0),
  });

  const integrations = integrationsQuery.data;
  const projects = useMemo(() => projectsQuery.data?.items || [], [projectsQuery.data]);

  const prefill = (location.state as { prefill?: Partial<SampleBrief> } | null)?.prefill;

  const [topic, setTopic] = useState<string>(prefill?.topic || '');
  const [goalChoice, setGoalChoice] = useState<string>(
    prefill?.goal && GOAL_OPTIONS.includes(prefill.goal) ? prefill.goal : GOAL_OPTIONS[0],
  );
  const [customGoal, setCustomGoal] = useState<string>(
    prefill?.goal && !GOAL_OPTIONS.includes(prefill.goal) ? prefill.goal : '',
  );
  const [platform, setPlatform] = useState<PlatformType>(prefill?.platform || 'linkedin');
  const [audience, setAudience] = useState<string>(prefill?.audience || '');
  const [selectedTones, setSelectedTones] = useState<string[]>(
    prefill?.tone
      ? prefill.tone
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean)
      : ['friendly', 'crisp'],
  );
  const [customTone, setCustomTone] = useState('');
  const [depth, setDepth] = useState<DepthType>(prefill?.depth || 'standard');
  const [language, setLanguage] = useState('en');
  const [callToAction, setCallToAction] = useState<string>(prefill?.call_to_action || '');
  const [projectId, setProjectId] = useState<string>(searchParams.get('projectId') || '');

  const [selectedModel, setSelectedModel] = useState<string>(() => getSavedPreferredModel());

  const [requiredPoints, setRequiredPoints] = useState<string[]>(prefill?.required_points || []);
  const [reqInput, setReqInput] = useState('');
  const [prohibitedPoints, setProhibitedPoints] = useState<string[]>(
    prefill?.prohibited_points || [],
  );
  const [prohInput, setProhInput] = useState('');

  const [sourceUrls, setSourceUrls] = useState<string[]>(prefill?.source_urls || []);
  const [urlInput, setUrlInput] = useState('');
  const [urlError, setUrlError] = useState<string | null>(null);
  const [sourceNotes, setSourceNotes] = useState('');
  const [sourcePrefs, setSourcePrefs] = useState('');

  const [showSourcesAndConstraints, setShowSourcesAndConstraints] = useState(
    Boolean(
      (prefill?.required_points && prefill.required_points.length > 0) ||
        (prefill?.source_urls && prefill.source_urls.length > 0),
    ),
  );
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [workflowStrategy, setWorkflowStrategy] = useState<WorkflowStrategyType>('multi_agent');
  const [temperature, setTemperature] = useState(0.2);
  const [searchDepth, setSearchDepth] = useState<'basic' | 'advanced'>('advanced');
  const [timeScope, setTimeScope] = useState<'' | 'day' | 'week' | 'month' | 'year'>('');
  const [editorThreshold, setEditorThreshold] = useState<number>(85);
  const [useDemoMode, setUseDemoMode] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!projectId) return;
    const found = projects.find((p) => p.project_id === projectId);
    if (!found) return;
    setPlatform(found.defaults.platform);
    setDepth(found.defaults.depth);
    if (found.defaults.audience && !audience) setAudience(found.defaults.audience);
    if (found.defaults.tone) {
      setSelectedTones(
        found.defaults.tone
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      );
    }
  }, [projectId, projects, audience]);

  useEffect(() => {
    if (!integrations) return;
    if (!integrations.llm_configured) {
      setUseDemoMode(true);
    }
    if (!selectedModel && integrations.llm_model) {
      setSelectedModel(resolveActiveModelId(integrations.llm_model) || DEFAULT_MODEL_ID);
    }
  }, [integrations, selectedModel]);

  const fillExample = (ex: SampleBrief) => {
    setTopic(ex.topic);
    setPlatform(ex.platform);
    setAudience(ex.audience);
    setDepth(ex.depth);
    setCallToAction(ex.call_to_action);
    setRequiredPoints(ex.required_points);
    setProhibitedPoints(ex.prohibited_points);
    setSourceUrls(ex.source_urls);
    setSelectedTones(
      ex.tone
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
    );
    if (GOAL_OPTIONS.includes(ex.goal)) {
      setGoalChoice(ex.goal);
    } else {
      setGoalChoice('Custom');
      setCustomGoal(ex.goal);
    }
    setShowSourcesAndConstraints(true);
    setFieldErrors({});
  };

  const effectiveGoal = goalChoice === 'Custom' ? customGoal.trim() || GOAL_OPTIONS[0] : goalChoice;
  const effectiveTone =
    [...selectedTones, customTone.trim()].filter(Boolean).join(', ') || 'friendly, crisp';

  const buildPayload = (): ContentRequestPayload => ({
    topic: topic.trim(),
    goal: effectiveGoal,
    platform,
    audience: audience.trim() || null,
    tone: effectiveTone,
    depth,
    language,
    call_to_action: callToAction.trim() || null,
    constraints: [],
    required_points: requiredPoints,
    prohibited_points: prohibitedPoints,
    source_urls: sourceUrls,
    source_notes: sourceNotes.trim() || null,
    source_preference: sourcePrefs
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    length_hint: null,
    project_id: projectId || null,
    workflow_strategy: workflowStrategy,
    use_demo_mode: useDemoMode,
    advanced: {
      model_override: resolveActiveModelId(selectedModel) || null,
      temperature,
      search_depth: searchDepth,
      time_scope: timeScope || null,
      editor_threshold: editorThreshold,
    },
  });

  const createMutation = useMutation({
    mutationFn: api.createRun,
    onSuccess: (res) => {
      pushToast({
        title: 'Creating your post',
        description: res.execution_mode === 'demo' ? 'Running in Demo Mode' : 'Writing with live AI',
        variant: 'success',
      });
      navigate(`/runs/${res.run_id}`);
    },
    onError: (err) => {
      if (err instanceof ApiClientError) {
        setFormError(err.message);
        const mapped: Record<string, string> = {};
        for (const fe of err.fieldErrors) mapped[fe.field] = fe.message;
        setFieldErrors(mapped);
      } else {
        setFormError('Something went wrong while starting your post.');
      }
    },
  });

  const toggleTone = (t: string) => {
    setSelectedTones((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));
  };

  const addRequired = () => {
    const val = reqInput.trim();
    if (!val || requiredPoints.includes(val)) return;
    setRequiredPoints((prev) => [...prev, val]);
    setReqInput('');
  };

  const addProhibited = () => {
    const val = prohInput.trim();
    if (!val || prohibitedPoints.includes(val)) return;
    setProhibitedPoints((prev) => [...prev, val]);
    setProhInput('');
  };

  const addUrl = () => {
    const val = urlInput.trim();
    if (!val) return;
    const err = validateHttpUrl(val);
    if (err) {
      setUrlError(err);
      return;
    }
    if (sourceUrls.includes(val)) {
      setUrlError('This link is already added.');
      return;
    }
    setUrlError(null);
    setSourceUrls((prev) => [...prev, val]);
    setUrlInput('');
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFieldErrors({});

    const cleanedTopic = topic.trim().replace(/\s+/g, ' ');
    if (cleanedTopic.length < 5) {
      setFieldErrors({ topic: 'Please tell us a little more about your topic (at least 5 characters).' });
      return;
    }
    if (urlInput.trim()) {
      const uErr = validateHttpUrl(urlInput);
      if (uErr) {
        setUrlError(uErr);
        return;
      }
    }

    createMutation.mutate(buildPayload());
  };

  const normalizedPreview = buildPayload();

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      {integrations && !integrations.llm_configured ? (
        <DemoModeBanner reason="Live AI keys are not configured yet — Demo Mode is ready for practice." />
      ) : null}

      {/* Starter Ideas Bar */}
      <div className="glass-panel flex flex-wrap items-center justify-between gap-2 rounded-2xl px-4.5 py-3.5">
        <div className="flex items-center gap-2 text-[12px] font-semibold text-[#5E6A82] dark:text-slate-300">
          <Sparkles className="h-4 w-4 text-fuchsia-500" aria-hidden="true" />
          <span>Try a starter idea:</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {QUICK_START_EXAMPLES.map((ex) => (
            <button
              key={ex.id}
              type="button"
              onClick={() => fillExample(ex)}
              className="glass-subtle rounded-full px-3.5 py-1 text-[12px] font-medium text-[#131B2E] transition hover:border-indigo-400/70 hover:bg-white/85 dark:text-slate-200"
            >
              {ex.label}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit} noValidate className="glass-panel space-y-6 rounded-3xl p-6 sm:p-7">
        {formError ? (
          <div
            role="alert"
            className="rounded-2xl border border-rose-300 bg-rose-50/90 px-4 py-3 text-[13px] text-rose-800 dark:border-rose-500/35 dark:bg-rose-500/15 dark:text-rose-200"
          >
            {formError}
          </div>
        ) : null}

        {/* Topic */}
        <div>
          <label
            htmlFor="run-topic"
            className="block text-[14px] font-bold text-[#131B2E] dark:text-white"
          >
            What do you want to post about? *
          </label>
          <textarea
            id="run-topic"
            rows={3}
            required
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g., 5 honest lessons I learned after growing my newsletter from zero to 10k readers"
            aria-invalid={Boolean(fieldErrors.topic)}
            aria-describedby={fieldErrors.topic ? 'topic-error' : undefined}
            className={`mt-2 w-full rounded-2xl border bg-white/80 px-4 py-3 text-[14px] text-[#131B2E] backdrop-blur-md transition focus:border-indigo-500 focus:outline-none dark:bg-slate-900/65 dark:text-slate-100 ${
              fieldErrors.topic ? 'border-rose-400' : 'border-[#DCE2EC]/90 dark:border-slate-700'
            }`}
          />
          {fieldErrors.topic ? (
            <p
              id="topic-error"
              role="alert"
              className="mt-1.5 text-[12px] font-semibold text-rose-700 dark:text-rose-300"
            >
              {fieldErrors.topic}
            </p>
          ) : null}
        </div>

        {/* AI Assistant Selector */}
        <div>
          <span className="block text-[14px] font-bold text-[#131B2E] dark:text-white">
            Choose your AI assistant
          </span>
          <div className="mt-2.5">
            <ModelSelector
              models={integrations?.available_models}
              value={selectedModel}
              onChange={setSelectedModel}
              defaultModelLabel={integrations?.llm_model}
            />
          </div>
        </div>

        {/* Platform */}
        <div>
          <span className="block text-[14px] font-bold text-[#131B2E] dark:text-white">
            Where are you posting? *
          </span>
          <div className="mt-2.5 grid gap-3 sm:grid-cols-3">
            {PLATFORM_OPTIONS.map((opt) => {
              const active = platform === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setPlatform(opt.value)}
                  aria-pressed={active}
                  className={`rounded-2xl border p-3.5 text-left transition ${
                    active
                      ? opt.activeClass
                      : 'glass-subtle hover:bg-white/85 dark:hover:bg-slate-800/70'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full bg-gradient-to-br ${opt.dot}`} />
                    <span className="text-[14px] font-semibold text-[#131B2E] dark:text-white">
                      {opt.title}
                    </span>
                  </div>
                  <div className="mt-1 text-[12px] text-[#5E6A82] dark:text-slate-300">
                    {opt.desc}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Goal & Audience */}
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label
              htmlFor="run-goal"
              className="block text-[13px] font-bold text-[#131B2E] dark:text-white"
            >
              What is your main goal?
            </label>
            <select
              id="run-goal"
              value={goalChoice}
              onChange={(e) => setGoalChoice(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/90 bg-white/80 px-3 py-2 text-[14px] dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
            >
              {GOAL_OPTIONS.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
            {goalChoice === 'Custom' ? (
              <input
                type="text"
                aria-label="Custom goal"
                value={customGoal}
                onChange={(e) => setCustomGoal(e.target.value)}
                placeholder="Describe what you want this post to achieve..."
                className="mt-2 w-full rounded-xl border border-[#DCE2EC]/90 bg-white/80 px-3 py-2 text-[14px] dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
              />
            ) : null}
          </div>

          <div>
            <label
              htmlFor="run-audience"
              className="block text-[13px] font-bold text-[#131B2E] dark:text-white"
            >
              Who is reading? (optional)
            </label>
            <input
              id="run-audience"
              type="text"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              placeholder="e.g., Startup founders, students, design lovers"
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/90 bg-white/80 px-3 py-2 text-[14px] dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
            />
          </div>
        </div>

        {/* Length, Language, Project */}
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <span className="block text-[13px] font-bold text-[#131B2E] dark:text-white">
              Post length
            </span>
            <div className="glass-subtle mt-1.5 grid grid-cols-3 rounded-xl p-1">
              {LENGTH_LABELS.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setDepth(item.value)}
                  aria-pressed={depth === item.value}
                  className={`rounded-lg py-1.5 text-[12px] font-semibold transition ${
                    depth === item.value
                      ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white shadow-xs'
                      : 'text-[#5E6A82] dark:text-slate-300'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label
              htmlFor="run-language"
              className="block text-[13px] font-bold text-[#131B2E] dark:text-white"
            >
              Language
            </label>
            <select
              id="run-language"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/90 bg-white/80 px-3 py-2 text-[14px] dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
            >
              <option value="en">English</option>
              <option value="es">Spanish</option>
              <option value="fr">French</option>
              <option value="de">German</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="run-project"
              className="block text-[13px] font-bold text-[#131B2E] dark:text-white"
            >
              Save to folder
            </label>
            <select
              id="run-project"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-[#DCE2EC]/90 bg-white/80 px-3 py-2 text-[14px] dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
            >
              <option value="">No folder</option>
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Voice & Tone */}
        <div>
          <span className="block text-[13px] font-bold text-[#131B2E] dark:text-white">
            Voice &amp; vibe
          </span>
          <div className="mt-2 flex flex-wrap gap-2">
            {TONE_OPTIONS.map((t) => {
              const active = selectedTones.includes(t);
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => toggleTone(t)}
                  aria-pressed={active}
                  className={`rounded-full px-3.5 py-1 text-[13px] font-medium capitalize transition ${
                    active
                      ? 'border border-violet-400 bg-gradient-to-r from-indigo-500/20 to-pink-500/20 text-indigo-800 dark:text-indigo-200'
                      : 'glass-subtle text-[#5E6A82] hover:text-[#131B2E] dark:text-slate-300'
                  }`}
                >
                  {t}
                </button>
              );
            })}
            <input
              type="text"
              aria-label="Custom tone"
              value={customTone}
              onChange={(e) => setCustomTone(e.target.value)}
              placeholder="+ custom vibe"
              className="w-32 rounded-full border border-[#DCE2EC]/80 bg-white/75 px-3 py-1 text-[13px] dark:border-slate-700 dark:bg-slate-900/65 dark:text-slate-100"
            />
          </div>
        </div>

        {/* Optional Key Points, Links & CTA */}
        <div className="glass-subtle rounded-2xl">
          <button
            type="button"
            onClick={() => setShowSourcesAndConstraints((v) => !v)}
            aria-expanded={showSourcesAndConstraints}
            className="flex w-full items-center justify-between px-4 py-3 text-left text-[13px] font-semibold text-[#131B2E] dark:text-slate-100"
          >
            <span className="flex items-center gap-2">
              <LinkIcon className="h-4 w-4 text-teal-500" aria-hidden="true" />
              <span>Must-hit points, links &amp; closing line (optional)</span>
            </span>
            {showSourcesAndConstraints ? (
              <ChevronUp className="h-4 w-4 text-[#5E6A82]" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-4 w-4 text-[#5E6A82]" aria-hidden="true" />
            )}
          </button>

          {showSourcesAndConstraints ? (
            <div className="space-y-4 border-t border-[#DCE2EC]/60 p-4 dark:border-slate-800">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="req-point" className="block text-[12px] font-semibold">
                    Key points to include
                  </label>
                  <div className="mt-1.5 flex gap-2">
                    <input
                      id="req-point"
                      type="text"
                      value={reqInput}
                      onChange={(e) => setReqInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          addRequired();
                        }
                      }}
                      placeholder="Add a key takeaway"
                      className="min-w-0 flex-1 rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-1.5 text-[13px] dark:border-slate-700 dark:bg-slate-900/65"
                    />
                    <button
                      type="button"
                      onClick={addRequired}
                      aria-label="Add key point"
                      className="glass-subtle rounded-xl px-2.5 py-1.5"
                    >
                      <Plus className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {requiredPoints.map((pt) => (
                      <span
                        key={pt}
                        className="inline-flex items-center gap-1 rounded-full bg-teal-500/15 px-2.5 py-0.5 text-[12px] font-medium text-teal-800 dark:text-teal-200"
                      >
                        {pt}
                        <button
                          type="button"
                          aria-label={`Remove required point ${pt}`}
                          onClick={() => setRequiredPoints((p) => p.filter((x) => x !== pt))}
                        >
                          <X className="h-3 w-3" aria-hidden="true" />
                        </button>
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <label htmlFor="proh-point" className="block text-[12px] font-semibold">
                    Things to avoid saying
                  </label>
                  <div className="mt-1.5 flex gap-2">
                    <input
                      id="proh-point"
                      type="text"
                      value={prohInput}
                      onChange={(e) => setProhInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          addProhibited();
                        }
                      }}
                      placeholder="Anything off-limits"
                      className="min-w-0 flex-1 rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-1.5 text-[13px] dark:border-slate-700 dark:bg-slate-900/65"
                    />
                    <button
                      type="button"
                      onClick={addProhibited}
                      aria-label="Add point to avoid"
                      className="glass-subtle rounded-xl px-2.5 py-1.5"
                    >
                      <Plus className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {prohibitedPoints.map((pt) => (
                      <span
                        key={pt}
                        className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2.5 py-0.5 text-[12px] font-medium text-rose-800 dark:text-rose-200"
                      >
                        {pt}
                        <button
                          type="button"
                          aria-label={`Remove prohibited point ${pt}`}
                          onClick={() => setProhibitedPoints((p) => p.filter((x) => x !== pt))}
                        >
                          <X className="h-3 w-3" aria-hidden="true" />
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <label htmlFor="source-url-input" className="block text-[12px] font-semibold">
                  Links you want us to read (https://...)
                </label>
                <div className="mt-1.5 flex gap-2">
                  <input
                    id="source-url-input"
                    type="url"
                    value={urlInput}
                    onChange={(e) => {
                      setUrlInput(e.target.value);
                      if (urlError) setUrlError(null);
                    }}
                    placeholder="https://example.com/article"
                    className="min-w-0 flex-1 rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[13px] dark:border-slate-700 dark:bg-slate-900/65"
                  />
                  <button
                    type="button"
                    onClick={addUrl}
                    className="glass-subtle rounded-xl px-3.5 py-2 text-[13px] font-semibold"
                  >
                    Add link
                  </button>
                </div>
                {urlError ? (
                  <p role="alert" className="mt-1 text-[12px] font-medium text-rose-700 dark:text-rose-300">
                    {urlError}
                  </p>
                ) : null}
                {sourceUrls.length > 0 ? (
                  <ul className="mt-2 space-y-1">
                    {sourceUrls.map((u) => (
                      <li
                        key={u}
                        className="flex items-center justify-between rounded-xl bg-white/70 px-3 py-1.5 text-[12px] dark:bg-slate-800/70"
                      >
                        <span className="truncate">{u}</span>
                        <button
                          type="button"
                          aria-label={`Remove link ${u}`}
                          onClick={() => setSourceUrls((prev) => prev.filter((x) => x !== u))}
                          className="ml-2 text-[#5E6A82] hover:text-rose-600"
                        >
                          <X className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="source-notes" className="block text-[12px] font-medium">
                    Your rough notes
                  </label>
                  <textarea
                    id="source-notes"
                    rows={2}
                    value={sourceNotes}
                    onChange={(e) => setSourceNotes(e.target.value)}
                    placeholder="Drop any personal facts, quotes, or ideas..."
                    className="mt-1 w-full rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[13px] dark:border-slate-700 dark:bg-slate-900/65"
                  />
                </div>
                <div className="space-y-2.5">
                  <div>
                    <label htmlFor="source-pref" className="block text-[12px] font-medium">
                      Trusted websites (optional)
                    </label>
                    <input
                      id="source-pref"
                      type="text"
                      value={sourcePrefs}
                      onChange={(e) => setSourcePrefs(e.target.value)}
                      placeholder="e.g., hbr.org, nature.com"
                      className="mt-1 w-full rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[13px] dark:border-slate-700 dark:bg-slate-900/65"
                    />
                  </div>
                  <div>
                    <label htmlFor="cta-input" className="block text-[12px] font-medium">
                      Closing question or call to action
                    </label>
                    <input
                      id="cta-input"
                      type="text"
                      value={callToAction}
                      onChange={(e) => setCallToAction(e.target.value)}
                      placeholder="e.g., What has worked best for you?"
                      className="mt-1 w-full rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[13px] dark:border-slate-700 dark:bg-slate-900/65"
                    />
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Extra Creative Controls */}
        <div className="glass-subtle rounded-2xl">
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            aria-expanded={showAdvanced}
            className="flex w-full items-center justify-between px-4 py-3 text-left text-[13px] font-semibold text-[#131B2E] dark:text-slate-100"
          >
            <span>More creative options (optional)</span>
            {showAdvanced ? (
              <ChevronUp className="h-4 w-4 text-[#5E6A82]" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-4 w-4 text-[#5E6A82]" aria-hidden="true" />
            )}
          </button>

          {showAdvanced ? (
            <div className="grid gap-4 border-t border-[#DCE2EC]/60 p-4 sm:grid-cols-2 dark:border-slate-800">
              <div>
                <label htmlFor="wf-strategy" className="block text-[12px] font-medium">
                  Writing style mode
                </label>
                <select
                  id="wf-strategy"
                  value={workflowStrategy}
                  onChange={(e) => setWorkflowStrategy(e.target.value as WorkflowStrategyType)}
                  className="mt-1 w-full rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[13px] dark:border-slate-700 dark:bg-slate-900/65"
                >
                  <option value="multi_agent">Full 4-step studio (Research + Write + Polish + Check)</option>
                  <option value="single_agent">Quick 1-pass draft</option>
                </select>
              </div>
              <div>
                <label htmlFor="adv-search-depth" className="block text-[12px] font-medium">
                  Research thoroughness
                </label>
                <select
                  id="adv-search-depth"
                  value={searchDepth}
                  onChange={(e) => setSearchDepth(e.target.value as 'basic' | 'advanced')}
                  className="mt-1 w-full rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[13px] dark:border-slate-700 dark:bg-slate-900/65"
                >
                  <option value="advanced">Thorough (recommended)</option>
                  <option value="basic">Quick lookup</option>
                </select>
              </div>
              <div>
                <label htmlFor="adv-time" className="block text-[12px] font-medium">
                  Source freshness
                </label>
                <select
                  id="adv-time"
                  value={timeScope}
                  onChange={(e) =>
                    setTimeScope(e.target.value as '' | 'day' | 'week' | 'month' | 'year')
                  }
                  className="mt-1 w-full rounded-xl border border-[#DCE2EC] bg-white/80 px-3 py-2 text-[13px] dark:border-slate-700 dark:bg-slate-900/65"
                >
                  <option value="">Any time</option>
                  <option value="day">Last 24 hours</option>
                  <option value="week">Past week</option>
                  <option value="month">Past month</option>
                  <option value="year">Past year</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="adv-temp" className="block text-[12px] font-medium">
                    Creativity ({temperature.toFixed(1)})
                  </label>
                  <input
                    id="adv-temp"
                    type="range"
                    min={0}
                    max={1}
                    step={0.1}
                    value={temperature}
                    onChange={(e) => setTemperature(parseFloat(e.target.value))}
                    className="mt-2 w-full accent-indigo-600"
                  />
                </div>
                <div>
                  <label htmlFor="adv-thresh" className="block text-[12px] font-medium">
                    Polish bar ({editorThreshold}+)
                  </label>
                  <input
                    id="adv-thresh"
                    type="range"
                    min={60}
                    max={95}
                    step={1}
                    value={editorThreshold}
                    onChange={(e) => setEditorThreshold(parseInt(e.target.value, 10))}
                    className="mt-2 w-full accent-teal-600"
                  />
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Demo Mode practice toggle */}
        <div className="glass-subtle flex flex-wrap items-center justify-between gap-3 rounded-2xl px-4 py-3">
          <label className="flex cursor-pointer items-center gap-2.5 text-[13px]">
            <input
              type="checkbox"
              checked={useDemoMode}
              onChange={(e) => setUseDemoMode(e.target.checked)}
              className="h-4 w-4 rounded border-[#DCE2EC] text-indigo-600"
            />
            <span className="font-medium text-[#131B2E] dark:text-slate-200">
              Practice in Demo Mode (uses sample text, no AI credits)
            </span>
          </label>
          <Link
            to="/settings"
            className="text-[12px] font-semibold text-indigo-600 hover:underline dark:text-indigo-300"
          >
            AI setup
          </Link>
        </div>

        {showPreview ? (
          <div className="glass-tint-sky space-y-1.5 rounded-2xl p-4 text-[13px] backdrop-blur-xl">
            <div className="font-semibold text-[#131B2E] dark:text-white">
              Ready to write · {platformLabel(normalizedPreview.platform)}
            </div>
            <p className="text-[#5E6A82] dark:text-slate-300">
              Topic: <strong className="text-[#131B2E] dark:text-white">{normalizedPreview.topic || '—'}</strong> ·
              Tone: <strong className="text-[#131B2E] dark:text-white">{normalizedPreview.tone}</strong>
            </p>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#DCE2EC]/60 pt-4 dark:border-slate-800">
          <button
            type="button"
            onClick={() => setShowPreview((v) => !v)}
            className="glass-subtle inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-[13px] font-medium text-[#131B2E] hover:bg-white/85 dark:text-slate-200"
          >
            <Eye className="h-4 w-4" aria-hidden="true" />
            <span>{showPreview ? 'Hide summary' : 'Check summary'}</span>
          </button>

          <button
            type="submit"
            disabled={createMutation.isPending}
            className="btn-aurora inline-flex items-center gap-2 rounded-full px-6 py-2.5 text-[14px] font-semibold disabled:opacity-60"
          >
            <Send className="h-4 w-4" aria-hidden="true" />
            <span>{createMutation.isPending ? 'Starting...' : 'Start writing'}</span>
          </button>
        </div>
      </form>
    </div>
  );
}

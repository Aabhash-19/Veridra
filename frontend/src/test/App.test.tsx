import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '../app/App';
import { ThemeProvider } from '../components/ThemeProvider';
import { ToastProvider } from '../components/ToastProvider';

function renderApp(initialPath: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[initialPath]}>
            <AppRoutes />
          </MemoryRouter>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

const INTEGRATIONS_DEMO = {
  app_env: 'development',
  llm_provider: 'gemini',
  llm_model: 'gemini-3.6-flash',
  llm_configured: false,
  llm_masked_label: 'No AI API key configured yet',
  search_provider: 'tavily',
  search_configured: false,
  search_masked_label: 'Tavily Search — API key not configured',
  demo_mode_env: false,
  effective_default_mode: 'unconfigured_demo_available',
  database_dialect: 'sqlite',
  langsmith_enabled: false,
  rate_card_version: '2026-11-v1',
  guardrails: {
    max_editor_revisions: 3,
    max_fact_remediations: 2,
    max_research_retries: 1,
    max_graph_steps: 24,
    editor_approval_threshold: 85,
    run_timeout_seconds: 600,
  },
  privacy_note: 'Local SQLite storage.',
};

describe('Veridra Frontend Suite', () => {
  const originalFetch = globalThis.fetch;
  const originalEventSource = globalThis.EventSource;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    globalThis.EventSource = originalEventSource;
  });

  it('renders Dashboard empty state cleanly without fabricated metrics', async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/dashboard/summary')) {
        return new Response(
          JSON.stringify({
            total_runs: 0,
            completed_runs: 0,
            completed_with_warnings_runs: 0,
            failed_runs: 0,
            cancelled_runs: 0,
            active_runs: 0,
            avg_editor_score: null,
            editor_score_sample_size: 0,
            avg_evidence_coverage: null,
            total_unsupported_claims: 0,
            total_contradicted_claims: 0,
            median_duration_ms: null,
            p90_duration_ms: null,
            total_tokens: null,
            total_estimated_cost: null,
            cost_status: 'unavailable',
            avg_editor_revisions: null,
            avg_fact_remediations: null,
            provider_health: { rate_limit: 0, timeout: 0, other_failure: 0 },
          }),
        );
      }
      if (url.includes('/api/v1/runs')) {
        return new Response(JSON.stringify({ items: [], total: 0, limit: 5, offset: 0 }));
      }
      if (url.includes('/api/v1/projects')) {
        return new Response(JSON.stringify({ items: [], total: 0, limit: 4, offset: 0 }));
      }
      if (url.endsWith('/api/v1/settings/integrations')) {
        return new Response(JSON.stringify(INTEGRATIONS_DEMO));
      }
      return new Response('{}', { status: 404 });
    }) as typeof fetch;

    renderApp('/');

    expect(await screen.findByText('No content runs yet')).toBeInTheDocument();
    expect(screen.getAllByText(/Demo Mode available/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/Avg polish score/i)).not.toBeInTheDocument();
  });

  it('renders populated Dashboard metrics and recent runs truthfully', async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/dashboard/summary')) {
        return new Response(
          JSON.stringify({
            total_runs: 2,
            completed_runs: 1,
            completed_with_warnings_runs: 1,
            failed_runs: 0,
            cancelled_runs: 0,
            active_runs: 0,
            avg_editor_score: 89,
            editor_score_sample_size: 2,
            avg_evidence_coverage: 0.92,
            total_unsupported_claims: 0,
            total_contradicted_claims: 0,
            median_duration_ms: 420,
            p90_duration_ms: 600,
            total_tokens: null,
            total_estimated_cost: null,
            cost_status: 'unavailable',
            avg_editor_revisions: 0.5,
            avg_fact_remediations: 0.5,
            provider_health: { rate_limit: 0, timeout: 0, other_failure: 0 },
          }),
        );
      }
      if (url.includes('/api/v1/runs')) {
        return new Response(
          JSON.stringify({
            items: [
              {
                run_id: 'run_icpc_1',
                project_id: null,
                parent_run_id: null,
                status: 'completed',
                execution_mode: 'demo',
                workflow_strategy: 'multi_agent',
                topic: 'How ICPC develops algorithmic problem-solving skills',
                platform: 'linkedin',
                current_node: 'persist_result',
                created_at: '2026-11-25T11:30:00Z',
                started_at: '2026-11-25T11:30:00Z',
                finished_at: '2026-11-25T11:30:01Z',
                duration_ms: 420,
                editor_score: 89,
                fact_status: 'pass',
                evidence_coverage: 1.0,
                total_tokens: null,
                estimated_cost: null,
                cost_status: 'unavailable',
                warning_count: 0,
                terminal_reason: 'COMPLETED',
              },
            ],
            total: 1,
            limit: 5,
            offset: 0,
          }),
        );
      }
      if (url.includes('/api/v1/projects')) {
        return new Response(JSON.stringify({ items: [], total: 0, limit: 4, offset: 0 }));
      }
      if (url.endsWith('/api/v1/settings/integrations')) {
        return new Response(JSON.stringify(INTEGRATIONS_DEMO));
      }
      return new Response('{}', { status: 404 });
    }) as typeof fetch;

    renderApp('/');

    expect(await screen.findByText(/Based on 2 reviewed post/i)).toBeInTheDocument();
    expect(screen.getByText('How ICPC develops algorithmic problem-solving skills')).toBeInTheDocument();
  });

  it('validates Create workflow form inputs and submits valid payload', async () => {
    const user = userEvent.setup();
    const submittedRequests: Record<string, unknown>[] = [];

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/settings/integrations')) {
        return new Response(JSON.stringify(INTEGRATIONS_DEMO));
      }
      if (url.includes('/api/v1/projects')) {
        return new Response(JSON.stringify({ items: [], total: 0, limit: 50, offset: 0 }));
      }
      if (url.endsWith('/api/v1/runs') && init?.method === 'POST') {
        submittedRequests.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return new Response(
          JSON.stringify({
            run_id: 'run_created_1',
            status: 'queued',
            execution_mode: 'demo',
            events_url: '/api/v1/runs/run_created_1/events',
          }),
          { status: 201 },
        );
      }
      if (url.endsWith('/api/v1/runs/run_created_1')) {
        return new Response(
          JSON.stringify({
            run_id: 'run_created_1',
            status: 'queued',
            execution_mode: 'demo',
            workflow_strategy: 'multi_agent',
            platform: 'x',
            current_node: null,
            request: { topic: 'Testing Veridra form validation' },
            warnings: [],
            errors: [],
            prompt_versions: {},
            quality: {
              editor_score: null,
              editor_verdict: null,
              fact_status: null,
              total_material_claims: 0,
              supported_claims: 0,
              partially_supported_claims: 0,
              unsupported_claims: 0,
              contradicted_claims: 0,
              uncertain_claims: 0,
              evidence_coverage: null,
              warning_count: 0,
            },
            metrics: {
              duration_ms: null,
              total_input_tokens: null,
              total_output_tokens: null,
              total_tokens: null,
              token_usage_status: 'unavailable',
              estimated_cost: null,
              cost_status: 'unavailable',
              rate_card_version: null,
              currency: null,
              editor_revision_count: 0,
              fact_remediation_count: 0,
              research_retry_count: 0,
              total_step_count: 0,
            },
            node_metrics: [],
            sources: [],
            evidence_items: [],
            claims: [],
            artifacts: [],
            latest_artifact: null,
            events: [],
            created_at: '2026-11-25T11:30:00Z',
          }),
        );
      }
      return new Response('{}', { status: 404 });
    }) as typeof fetch;

    renderApp('/runs/new');

    // Submit empty topic -> validation error
    const submitBtn = await screen.findByRole('button', { name: /Start writing/i });
    await user.click(submitBtn);
    expect(await screen.findByText(/at least 5 characters/i)).toBeInTheDocument();

    // Verify no dollar amounts are rendered inside model selector cards
    expect(screen.queryByText(/\$0\.|\$1\./)).not.toBeInTheDocument();

    // Unsafe file:// URL rejected inline (open collapsible Constraints & URLs first)
    await user.click(screen.getByRole('button', { name: /Must-hit points, links & closing line/i }));
    const urlField = screen.getByLabelText(/Links you want us to read/i);
    await user.type(urlField, 'file:///etc/passwd');
    await user.click(screen.getByRole('button', { name: 'Add link' }));
    expect(await screen.findByText(/Only http:\/\/ and https:\/\/ links are allowed/i)).toBeInTheDocument();
    await user.clear(urlField);

    // Valid topic + select X thread + ChatGPT model + submit
    await user.type(screen.getByLabelText(/What do you want to post about/i), 'Testing Veridra form validation');
    await user.click(screen.getByRole('button', { name: /X thread/i }));
    await user.click(screen.getByRole('button', { name: /ChatGPT \(GPT-4o mini\)/i }));
    await user.click(submitBtn);

    await waitFor(() => expect(submittedRequests).toHaveLength(1));
    expect(submittedRequests[0].topic).toBe('Testing Veridra form validation');
    expect(submittedRequests[0].platform).toBe('x');
    expect(submittedRequests[0].use_demo_mode).toBe(true);
    expect(submittedRequests[0].advanced).toEqual(
      expect.objectContaining({ model_override: 'gpt-4o-mini' }),
    );
  });

  it('streams SSE events into Live Run timeline and maps retrying/completed statuses', async () => {
    const listeners: Record<string, ((ev: MessageEvent) => void)[]> = {};
    class FakeEventSource {
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor() {
        setTimeout(() => this.onopen?.(), 0);
      }
      addEventListener(type: string, cb: (ev: MessageEvent) => void) {
        listeners[type] = listeners[type] || [];
        listeners[type].push(cb);
      }
      close() {}
    }
    globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/settings/integrations')) {
        return new Response(JSON.stringify(INTEGRATIONS_DEMO));
      }
      if (url.endsWith('/api/v1/runs/run_live_1')) {
        return new Response(
          JSON.stringify({
            run_id: 'run_live_1',
            status: 'running',
            execution_mode: 'demo',
            workflow_strategy: 'multi_agent',
            platform: 'linkedin',
            current_node: 'editor',
            request: { topic: 'ICPC skills' },
            warnings: [],
            errors: [],
            prompt_versions: {},
            quality: {
              editor_score: null,
              editor_verdict: null,
              fact_status: null,
              total_material_claims: 0,
              supported_claims: 0,
              partially_supported_claims: 0,
              unsupported_claims: 0,
              contradicted_claims: 0,
              uncertain_claims: 0,
              evidence_coverage: null,
              warning_count: 0,
            },
            metrics: {
              duration_ms: null,
              total_input_tokens: null,
              total_output_tokens: null,
              total_tokens: null,
              token_usage_status: 'unavailable',
              estimated_cost: null,
              cost_status: 'unavailable',
              rate_card_version: null,
              currency: null,
              editor_revision_count: 1,
              fact_remediation_count: 0,
              research_retry_count: 0,
              total_step_count: 5,
            },
            node_metrics: [],
            sources: [],
            evidence_items: [],
            claims: [],
            artifacts: [],
            latest_artifact: null,
            events: [
              {
                event_id: 'evt_1',
                run_id: 'run_live_1',
                sequence: 1,
                node: 'researcher',
                event_type: 'node.completed',
                status: 'completed',
                message: 'Collected 3 sources.',
                safe_payload: {},
                created_at: '2026-11-25T11:30:00Z',
              },
            ],
            created_at: '2026-11-25T11:30:00Z',
            started_at: '2026-11-25T11:30:00Z',
          }),
        );
      }
      return new Response('{}', { status: 404 });
    }) as typeof fetch;

    renderApp('/runs/run_live_1');

    expect(await screen.findByText('Revision 1 of 3')).toBeInTheDocument();
    expect(screen.getAllByText('Collected 3 sources.').length).toBeGreaterThanOrEqual(1);

    // Push live SSE retrying event
    await act(async () => {
      listeners['agent.progress']?.forEach((fn) =>
        fn(
          new MessageEvent('agent.progress', {
            data: JSON.stringify({
              event_id: 'evt_2',
              run_id: 'run_live_1',
              sequence: 2,
              node: 'editor_router',
              event_type: 'node.retrying',
              status: 'retrying',
              message: 'Routing draft back to Writer for editorial Revision 1 of 3.',
              safe_payload: {},
              created_at: '2026-11-25T11:30:02Z',
            }),
          }),
        ),
      );
    });

    expect(
      (await screen.findAllByText('Routing draft back to Writer for editorial Revision 1 of 3.'))
        .length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Retrying')).toBeInTheDocument();
  });

  it('handles Content Studio tabs, claim evidence navigation, warning gate on copy, and export', async () => {
    const user = userEvent.setup();
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextMock },
      configurable: true,
    });

    const studioRun = {
      run_id: 'run_studio_1',
      status: 'completed_with_warnings',
      execution_mode: 'demo',
      workflow_strategy: 'multi_agent',
      platform: 'linkedin',
      current_node: 'persist_result',
      request: { topic: 'ICPC skills and evidence' },
      research_brief: { open_questions: ['Long-term salary impact is context-dependent.'] },
      editor_result: {
        score: 89,
        score_breakdown: { clarity: 18, depth: 18, audience: 14, structure: 13, platform_fit: 13, specificity: 9, tone: 4 },
        verdict: 'approve',
        critical_issues: [],
        major_issues: [],
        minor_issues: [],
        rewrite_instructions: [],
        summary: 'Strong clarity.',
      },
      fact_check_result: { overall_status: 'pass_with_warnings' },
      warnings: [{ code: 'CLAIM_QUALIFIED', message: 'One claim remains uncertain.', node: 'finalizer' }],
      errors: [],
      prompt_versions: { researcher: 'researcher@1.0.0#abc' },
      quality: {
        editor_score: 89,
        editor_verdict: 'approve',
        fact_status: 'pass_with_warnings',
        total_material_claims: 2,
        supported_claims: 1,
        partially_supported_claims: 0,
        unsupported_claims: 0,
        contradicted_claims: 0,
        uncertain_claims: 1,
        evidence_coverage: 0.5,
        warning_count: 1,
      },
      metrics: {
        duration_ms: 350,
        total_input_tokens: null,
        total_output_tokens: null,
        total_tokens: null,
        token_usage_status: 'unavailable',
        estimated_cost: null,
        cost_status: 'unavailable',
        rate_card_version: null,
        currency: null,
        editor_revision_count: 1,
        fact_remediation_count: 0,
        research_retry_count: 0,
        total_step_count: 8,
      },
      node_metrics: [],
      sources: [
        {
          source_id: 'src_1',
          url: 'https://icpc.global/worldfinals/rules',
          canonical_url: 'https://icpc.global/worldfinals/rules',
          title: 'ICPC Official Rules',
          publisher: 'icpc.global',
          published_at: '2025-09-10',
          accessed_at: '2026-11-25T11:30:00Z',
          snippet: 'Teams of three share one workstation.',
          fetched_text_excerpt: 'Teams of three share one workstation.',
          credibility_score: null,
          relevance_score: 0.94,
          source_type: 'primary',
          status: 'retrieved',
          fetch_error: null,
        },
      ],
      evidence_items: [
        {
          evidence_id: 'ev_1',
          source_id: 'src_1',
          source_url: 'https://icpc.global/worldfinals/rules',
          source_title: 'ICPC Official Rules',
          quote_or_paraphrase: 'Teams of three share one workstation for five hours.',
          location_hint: 'Rules',
          related_claim_ids: ['cl_1'],
          support_type: 'supports',
          confidence: 0.9,
          created_by_node: 'researcher',
        },
      ],
      claims: [
        {
          claim_id: 'cl_1',
          claim_text: 'ICPC teams of three collaborate on one workstation.',
          claim_type: 'factual',
          materiality: 'high',
          status: 'supported',
          confidence: 0.9,
          supporting_evidence_ids: ['ev_1'],
          contradicting_evidence_ids: [],
          explanation: 'Directly supported by ICPC rules.',
          recommended_action: 'keep',
        },
        {
          claim_id: 'cl_2',
          claim_text: 'Contest participation may correlate with faster algorithmic debugging.',
          claim_type: 'factual',
          materiality: 'medium',
          status: 'uncertain',
          confidence: 0.45,
          supporting_evidence_ids: [],
          contradicting_evidence_ids: [],
          explanation: 'Outcome varies across cohorts.',
          recommended_action: 'qualify',
        },
      ],
      artifacts: [
        {
          artifact_id: 'art_1',
          version: 1,
          parent_version_id: null,
          title: 'What ICPC builds beyond rankings',
          platform: 'linkedin',
          word_count: 14,
          char_count: 80,
          created_at: '2026-11-25T11:30:01Z',
          created_by: 'finalizer',
          status: 'approved',
          differs_from_agent_approved: false,
        },
      ],
      latest_artifact: {
        artifact_id: 'art_1',
        run_id: 'run_studio_1',
        version: 1,
        parent_version_id: null,
        title: 'What ICPC builds beyond rankings',
        hook: 'Hook line',
        body_markdown: 'ICPC teams of three collaborate.\n\n## Sources\n[1] https://icpc.global/worldfinals/rules',
        platform: 'linkedin',
        outline: [],
        thread_segments: [],
        word_count: 14,
        char_count: 80,
        created_at: '2026-11-25T11:30:01Z',
        created_by: 'finalizer',
        status: 'approved',
        differs_from_agent_approved: false,
        claims: [],
        sources: [],
        evidence_items: [],
      },
      events: [],
      created_at: '2026-11-25T11:30:00Z',
      started_at: '2026-11-25T11:30:00Z',
      finished_at: '2026-11-25T11:30:01Z',
      terminal_reason: 'COMPLETED_WITH_WARNINGS',
    };

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/settings/integrations')) {
        return new Response(JSON.stringify(INTEGRATIONS_DEMO));
      }
      if (url.endsWith('/api/v1/runs/run_studio_1')) {
        return new Response(JSON.stringify(studioRun));
      }
      if (url.endsWith('/api/v1/artifacts/art_1')) {
        return new Response(JSON.stringify(studioRun.latest_artifact));
      }
      return new Response('{}', { status: 404 });
    }) as typeof fetch;

    renderApp('/runs/run_studio_1/studio');

    expect(await screen.findByDisplayValue('What ICPC builds beyond rankings')).toBeInTheDocument();

    // Clicking Copy with unresolved claims triggers warning dialog first
    await user.click(screen.getByRole('button', { name: 'Copy' }));
    expect(await screen.findByText(/Review unresolved claims before copying/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Copy anyway' }));
    await waitFor(() => expect(writeTextMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Copied to clipboard')).toBeInTheDocument();

    // Navigate to Fact Checks tab and filter to Needs attention
    await user.click(screen.getByRole('tab', { name: /Fact Checks/i }));
    expect(await screen.findByText('Supported by collected evidence')).toBeInTheDocument();
    expect(screen.getByText('Evidence is mixed or inconclusive')).toBeInTheDocument();

    // Clicking linked evidence chip opens Evidence tab and shows source link
    await user.click(screen.getByRole('button', { name: /Supports: ev_1/i }));
    const link = await screen.findByRole('link', { name: 'https://icpc.global/worldfinals/rules' });
    expect(link).toHaveAttribute('target', '_blank');

    // Metrics tab shows honest unavailable label for Demo Mode cost
    await user.click(screen.getByRole('tab', { name: /Metrics/i }));
    expect(await screen.findByText('Demo (N/A)')).toBeInTheDocument();
  });

  it('shows honest failure toast when clipboard access is denied and renders Settings safely', async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('Permission denied')) },
      configurable: true,
    });

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/settings/integrations')) {
        return new Response(JSON.stringify(INTEGRATIONS_DEMO));
      }
      return new Response('{}', { status: 404 });
    }) as typeof fetch;

    renderApp('/settings');
    expect(await screen.findByText(/Connected AI & web search/i)).toBeInTheDocument();
    expect(screen.getByText(/No AI API key configured yet/i)).toBeInTheDocument();

    // Toggle dark mode via header button & Settings Appearance control
    const toggleBtn = screen.getByRole('button', { name: /Switch to dark mode/i });
    await user.click(toggleBtn);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    await user.click(screen.getByRole('button', { name: /Light editorial/i }));
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    await user.click(screen.getByRole('button', { name: /Copy snippet/i }));
    expect(await screen.findByText('Could not copy template')).toBeInTheDocument();
  });
});

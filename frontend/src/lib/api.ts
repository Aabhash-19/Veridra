import type {
  BenchmarkDetail,
  BenchmarkListResponse,
  BenchmarkTopic,
  ContentRequestPayload,
  DashboardSummary,
  DraftArtifact,
  IntegrationsStatus,
  ProjectDefaults,
  ProjectListResponse,
  ProjectRead,
  PublishArtifactResponse,
  RunDetail,
  RunListResponse,
} from './types';

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export class ApiClientError extends Error {
  code: string;
  status: number;
  requestId?: string;
  fieldErrors: { field: string; message: string }[];

  constructor(params: {
    message: string;
    code: string;
    status: number;
    requestId?: string;
    fieldErrors?: { field: string; message: string }[];
  }) {
    super(params.message);
    this.name = 'ApiClientError';
    this.code = params.code;
    this.status = params.status;
    this.requestId = params.requestId;
    this.fieldErrors = params.fieldErrors || [];
  }
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });

  if (!res.ok) {
    let errBody: {
      error?: {
        code?: string;
        message?: string;
        request_id?: string;
        field_errors?: { field: string; message: string }[];
      };
    } | null = null;
    try {
      errBody = await res.json();
    } catch {
      errBody = null;
    }
    throw new ApiClientError({
      message: errBody?.error?.message || `Request failed (${res.status})`,
      code: errBody?.error?.code || 'INTERNAL_ERROR',
      status: res.status,
      requestId: errBody?.error?.request_id,
      fieldErrors: errBody?.error?.field_errors,
    });
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export const api = {
  getDashboardSummary: () => apiRequest<DashboardSummary>('/api/v1/dashboard/summary'),
  getIntegrations: () => apiRequest<IntegrationsStatus>('/api/v1/settings/integrations'),

  // Projects
  listProjects: (limit = 50, offset = 0) =>
    apiRequest<ProjectListResponse>(`/api/v1/projects?limit=${limit}&offset=${offset}`),
  getProject: (id: string) => apiRequest<ProjectRead>(`/api/v1/projects/${id}`),
  createProject: (payload: {
    name: string;
    description?: string | null;
    defaults: ProjectDefaults;
  }) =>
    apiRequest<ProjectRead>('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateProject: (
    id: string,
    payload: { name?: string; description?: string | null; defaults?: ProjectDefaults },
  ) =>
    apiRequest<ProjectRead>(`/api/v1/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteProject: (id: string) =>
    apiRequest<void>(`/api/v1/projects/${id}`, { method: 'DELETE' }),

  // Runs
  createRun: (payload: ContentRequestPayload) =>
    apiRequest<{ run_id: string; status: string; execution_mode: string; events_url: string }>(
      '/api/v1/runs',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
  listRuns: (params?: {
    status?: string;
    platform?: string;
    project_id?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.platform) qs.set('platform', params.platform);
    if (params?.project_id) qs.set('project_id', params.project_id);
    if (params?.search) qs.set('search', params.search);
    qs.set('limit', String(params?.limit ?? 20));
    qs.set('offset', String(params?.offset ?? 0));
    return apiRequest<RunListResponse>(`/api/v1/runs?${qs.toString()}`);
  },
  getRunDetail: (id: string) => apiRequest<RunDetail>(`/api/v1/runs/${id}`),
  cancelRun: (id: string) =>
    apiRequest<{
      run_id: string;
      status: string;
      cancellation_accepted: boolean;
      message: string;
    }>(`/api/v1/runs/${id}/cancel`, { method: 'POST' }),
  retryRun: (id: string) =>
    apiRequest<{
      run_id: string;
      parent_run_id: string;
      status: string;
      execution_mode: string;
      events_url: string;
    }>(`/api/v1/runs/${id}/retry`, { method: 'POST' }),
  deleteRun: (id: string) => apiRequest<void>(`/api/v1/runs/${id}`, { method: 'DELETE' }),

  // Artifacts
  getArtifact: (id: string) => apiRequest<DraftArtifact>(`/api/v1/artifacts/${id}`),
  saveArtifactEdit: (
    id: string,
    payload: { title?: string; body_markdown: string; expected_parent_version_id?: string | null },
  ) =>
    apiRequest<DraftArtifact>(`/api/v1/artifacts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  exportArtifact: async (id: string, format: 'md' | 'txt') => {
    const res = await fetch(`${API_BASE_URL}/api/v1/artifacts/${id}/export?format=${format}`);
    if (!res.ok) {
      throw new ApiClientError({
        message: 'Failed to export artifact.',
        code: 'INTERNAL_ERROR',
        status: res.status,
      });
    }
    const text = await res.text();
    const disp = res.headers.get('content-disposition') || '';
    const match = disp.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : `veridra-artifact.${format}`;
    return { text, filename };
  },

  publishArtifact: (
    id: string,
    payload: { platform: 'linkedin' | 'x' | 'instagram'; text: string },
  ) =>
    apiRequest<PublishArtifactResponse>(`/api/v1/artifacts/${id}/publish`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Benchmarks
  listBenchmarkDataset: () => apiRequest<BenchmarkTopic[]>('/api/v1/benchmarks/dataset'),
  listBenchmarks: (limit = 20, offset = 0) =>
    apiRequest<BenchmarkListResponse>(`/api/v1/benchmarks?limit=${limit}&offset=${offset}`),
  getBenchmark: (id: string) => apiRequest<BenchmarkDetail>(`/api/v1/benchmarks/${id}`),
  createBenchmark: (payload: {
    name: string;
    topic_count: number;
    topic_ids?: string[];
    include_holdout: boolean;
    strategies: string[];
    repeats: number;
    model_override?: string | null;
    use_demo_mode: boolean;
  }) =>
    apiRequest<BenchmarkDetail>('/api/v1/benchmarks', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  rateBenchmarkCase: (
    benchmarkId: string,
    caseId: string,
    payload: { rating: number; notes?: string },
  ) =>
    apiRequest(`/api/v1/benchmarks/${benchmarkId}/cases/${caseId}/rating`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

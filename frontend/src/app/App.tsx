import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './AppShell';
import { ThemeProvider } from '../components/ThemeProvider';
import { ToastProvider } from '../components/ToastProvider';
import { BenchmarkDetailPage } from '../features/benchmarks/BenchmarkDetailPage';
import { BenchmarksPage } from '../features/benchmarks/BenchmarksPage';
import { ContentStudioPage } from '../features/content-studio/ContentStudioPage';
import { CreateRunPage } from '../features/create-run/CreateRunPage';
import { DashboardPage } from '../features/dashboard/DashboardPage';
import { LiveRunPage } from '../features/live-run/LiveRunPage';
import { RunsListPage } from '../features/live-run/RunsListPage';
import { ProjectDetailPage } from '../features/projects/ProjectDetailPage';
import { ProjectsPage } from '../features/projects/ProjectsPage';
import { SettingsPage } from '../features/settings/SettingsPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export function AppRoutes() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="/runs" element={<RunsListPage />} />
        <Route path="/runs/new" element={<CreateRunPage />} />
        <Route path="/runs/:runId" element={<LiveRunPage />} />
        <Route path="/runs/:runId/studio" element={<ContentStudioPage />} />
        <Route path="/benchmarks" element={<BenchmarksPage />} />
        <Route path="/benchmarks/:benchmarkId" element={<BenchmarkDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;

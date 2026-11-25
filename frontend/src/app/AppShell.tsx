import { useQuery } from '@tanstack/react-query';
import {
  BarChart3,
  FileText,
  FolderHeart,
  Home,
  Menu,
  Moon,
  Plus,
  Settings,
  Sparkles,
  Sun,
  X,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { VeridraMark } from '../components/VeridraMark';
import { useTheme } from '../components/themeContext';
import { api } from '../lib/api';

const NAV_ITEMS = [
  {
    to: '/',
    label: 'Home',
    icon: Home,
    end: true,
    accent: 'from-indigo-500 to-violet-500',
  },
  {
    to: '/projects',
    label: 'Projects',
    icon: FolderHeart,
    end: false,
    accent: 'from-amber-400 to-rose-500',
  },
  {
    to: '/runs',
    label: 'My Posts',
    icon: FileText,
    end: false,
    accent: 'from-teal-400 to-emerald-500',
  },
  {
    to: '/benchmarks',
    label: 'Compare',
    icon: BarChart3,
    end: false,
    accent: 'from-pink-500 to-fuchsia-500',
  },
  {
    to: '/settings',
    label: 'Settings',
    icon: Settings,
    end: false,
    accent: 'from-sky-400 to-blue-600',
  },
];

function getBreadcrumbTitle(pathname: string): { section: string; title: string } {
  if (pathname === '/') return { section: 'Creator Studio', title: 'Welcome back' };
  if (pathname.startsWith('/projects/')) return { section: 'Projects', title: 'Project details' };
  if (pathname === '/projects') return { section: 'Projects', title: 'Your content folders' };
  if (pathname === '/runs/new') return { section: 'Create', title: 'Create a new post' };
  if (pathname.endsWith('/studio')) return { section: 'Post Studio', title: 'Edit, preview & export' };
  if (pathname.startsWith('/runs/')) return { section: 'Live Progress', title: 'Crafting your post' };
  if (pathname === '/runs') return { section: 'My Posts', title: 'All drafts & posts' };
  if (pathname.startsWith('/benchmarks/')) return { section: 'Compare', title: 'Style results' };
  if (pathname === '/benchmarks') return { section: 'Compare', title: 'Compare writing styles' };
  if (pathname === '/settings') return { section: 'Settings', title: 'Preferences & AI setup' };
  return { section: 'Veridra', title: 'Creator Studio' };
}

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const location = useLocation();
  const { resolvedTheme, toggleTheme } = useTheme();
  const { section, title } = getBreadcrumbTitle(location.pathname);

  const integrationsQuery = useQuery({
    queryKey: ['integrations'],
    queryFn: api.getIntegrations,
    staleTime: 30_000,
  });

  const integrations = integrationsQuery.data;

  const navContent = (
    <div className="glass-rail flex h-full flex-col justify-between px-4 py-6">
      <div>
        <Link
          to="/"
          onClick={() => setMobileNavOpen(false)}
          className="flex items-center gap-3 rounded-2xl px-2 py-2 transition hover:bg-indigo-500/10 dark:hover:bg-white/10"
        >
          <VeridraMark className="h-9 w-9 shrink-0 drop-shadow-md" />
          <div className="min-w-0">
            <div className="text-[16px] font-bold tracking-tight text-[#131B2E] dark:text-white">
              Veridra
            </div>
            <div className="truncate text-[11px] font-medium text-[#5E6A82] dark:text-slate-300/80">
              Creator Studio
            </div>
          </div>
        </Link>

        <nav aria-label="Primary navigation" className="mt-7 space-y-1.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setMobileNavOpen(false)}
                className={({ isActive }) =>
                  `group flex items-center gap-3 rounded-2xl px-3 py-2.5 text-[14px] font-medium transition-all ${
                    isActive
                      ? 'bg-gradient-to-r from-indigo-500/15 via-violet-500/12 to-pink-500/10 text-[#131B2E] ring-1 ring-indigo-400/40 shadow-xs dark:from-indigo-500/30 dark:via-violet-500/20 dark:to-pink-500/20 dark:text-white dark:ring-indigo-400/40'
                      : 'text-[#5E6A82] hover:bg-white/60 hover:text-[#131B2E] dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${item.accent} text-white shadow-xs transition-transform group-hover:scale-105 ${
                        isActive ? 'opacity-100' : 'opacity-80 group-hover:opacity-100'
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                    </span>
                    <span>{item.label}</span>
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>
      </div>

      <Link
        to="/settings"
        onClick={() => setMobileNavOpen(false)}
        className="glass-subtle mt-6 block rounded-2xl p-3.5 text-left transition hover:-translate-y-0.5 hover:border-indigo-400/50"
      >
        <div className="flex items-center justify-between text-[12px] font-semibold text-[#131B2E] dark:text-slate-200">
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-indigo-500 dark:text-indigo-300" aria-hidden="true" />
            AI Status
          </span>
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              integrations?.llm_configured
                ? 'bg-teal-400 shadow-[0_0_10px_#2dd4bf]'
                : 'bg-amber-400 shadow-[0_0_8px_#fbbf24]'
            }`}
            aria-hidden="true"
          />
        </div>
        <p className="mt-1 truncate text-[12px] text-[#5E6A82] dark:text-slate-300">
          {integrations
            ? integrations.llm_configured
              ? 'Connected · Ready'
              : integrations.demo_mode_env
                ? 'Demo Mode active'
                : 'Demo Mode available'
            : 'Checking...'}
        </p>
      </Link>
    </div>
  );

  return (
    <div className="ambient-backdrop min-h-screen text-[#131B2E] transition-colors dark:text-slate-100">
      <div className="relative z-10">
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-[240px] lg:block">{navContent}</aside>

        {mobileNavOpen ? (
          <div className="fixed inset-0 z-40 flex lg:hidden">
            <div
              className="fixed inset-0 bg-[#060914]/55 backdrop-blur-sm"
              onClick={() => setMobileNavOpen(false)}
              aria-hidden="true"
            />
            <aside className="relative z-50 w-[252px] max-w-[82vw]">{navContent}</aside>
            <button
              type="button"
              onClick={() => setMobileNavOpen(false)}
              aria-label="Close navigation menu"
              className="glass-panel relative z-50 m-3 flex h-9 w-9 items-center justify-center rounded-full text-[#131B2E] dark:text-slate-100"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
        ) : null}

        <div className="lg:pl-[240px]">
          <header className="glass-header sticky top-0 z-20">
            <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3.5 sm:px-6 lg:px-8">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setMobileNavOpen(true)}
                  aria-label="Open navigation menu"
                  className="glass-subtle inline-flex h-9 w-9 items-center justify-center rounded-xl text-[#131B2E] lg:hidden dark:text-slate-200"
                >
                  <Menu className="h-5 w-5" aria-hidden="true" />
                </button>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">
                    {section}
                  </div>
                  <h1 className="text-[18px] font-bold tracking-tight text-[#131B2E] sm:text-[20px] dark:text-white">
                    {title}
                  </h1>
                </div>
              </div>

              <div className="flex items-center gap-2.5">
                {integrations && !integrations.llm_configured ? (
                  <Link
                    to="/settings"
                    className="hidden items-center rounded-full border border-amber-300/80 bg-amber-50/85 px-3 py-1 text-[12px] font-medium text-amber-900 backdrop-blur-md sm:inline-flex dark:border-amber-500/30 dark:bg-amber-500/15 dark:text-amber-200"
                  >
                    Demo Mode available
                  </Link>
                ) : null}

                <button
                  type="button"
                  onClick={toggleTheme}
                  aria-label={
                    resolvedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
                  }
                  title={resolvedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                  className="glass-subtle inline-flex h-9 w-9 items-center justify-center rounded-xl text-[#131B2E] transition hover:scale-105 dark:text-slate-200"
                >
                  {resolvedTheme === 'dark' ? (
                    <Sun className="h-4 w-4 text-amber-300" aria-hidden="true" />
                  ) : (
                    <Moon className="h-4 w-4 text-indigo-600" aria-hidden="true" />
                  )}
                </button>

                <Link
                  to="/runs/new"
                  className="btn-aurora inline-flex items-center gap-1.5 rounded-full px-4.5 py-2 text-[13px] font-semibold"
                >
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  <span>New Post</span>
                </Link>
              </div>
            </div>
          </header>

          <main className="mx-auto max-w-6xl px-4 py-7 sm:px-6 lg:px-8">{children}</main>
        </div>
      </div>
    </div>
  );
}

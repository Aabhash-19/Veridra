import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  HelpCircle,
  Loader2,
  RotateCw,
  ShieldAlert,
  Slash,
  XCircle,
} from 'lucide-react';
import type { ClaimStatusType, RunStatusType, SourceStatusType } from '../lib/types';

export function RunStatusBadge({ status }: { status: RunStatusType | string }) {
  switch (status) {
    case 'completed':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-teal-400/40 bg-gradient-to-r from-teal-500/15 to-emerald-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-teal-800 dark:border-teal-400/35 dark:text-teal-200">
          <CheckCircle2 className="h-3.5 w-3.5 text-teal-600 dark:text-teal-300" aria-hidden="true" />
          Ready
        </span>
      );
    case 'completed_with_warnings':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-400/50 bg-gradient-to-r from-amber-400/15 to-orange-400/15 px-2.5 py-0.5 text-[12px] font-semibold text-amber-900 dark:border-amber-400/40 dark:text-amber-200">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-300" aria-hidden="true" />
          Review notes
        </span>
      );
    case 'running':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-400/45 bg-gradient-to-r from-indigo-500/15 to-violet-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-indigo-700 dark:border-indigo-400/40 dark:text-indigo-200">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-600 dark:text-indigo-300" aria-hidden="true" />
          Writing
        </span>
      );
    case 'queued':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-300/60 bg-sky-500/10 px-2.5 py-0.5 text-[12px] font-semibold text-sky-800 dark:border-sky-400/35 dark:text-sky-200">
          <Clock className="h-3.5 w-3.5 text-sky-600 dark:text-sky-300" aria-hidden="true" />
          Starting
        </span>
      );
    case 'failed':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-400/55 bg-gradient-to-r from-rose-500/15 to-orange-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-rose-800 dark:border-rose-400/40 dark:text-rose-200">
          <XCircle className="h-3.5 w-3.5 text-rose-600 dark:text-rose-300" aria-hidden="true" />
          Paused / Issue
        </span>
      );
    case 'cancelled':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-300/70 bg-slate-500/10 px-2.5 py-0.5 text-[12px] font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
          <Slash className="h-3.5 w-3.5" aria-hidden="true" />
          Stopped
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-300/70 bg-white/70 px-2.5 py-0.5 text-[12px] font-medium text-[#5E6A82] dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
          {status}
        </span>
      );
  }
}

export function ClaimStatusBadge({ status }: { status: ClaimStatusType }) {
  switch (status) {
    case 'supported':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-teal-400/40 bg-teal-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-teal-800 dark:border-teal-400/40 dark:text-teal-200">
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
          Supported by collected evidence
        </span>
      );
    case 'partially_supported':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300/70 bg-amber-400/15 px-2.5 py-0.5 text-[12px] font-semibold text-amber-900 dark:border-amber-500/40 dark:text-amber-200">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          Soften or narrow wording
        </span>
      );
    case 'uncertain':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300/70 bg-amber-400/15 px-2.5 py-0.5 text-[12px] font-semibold text-amber-900 dark:border-amber-500/40 dark:text-amber-200">
          <HelpCircle className="h-3.5 w-3.5" aria-hidden="true" />
          Evidence is mixed or inconclusive
        </span>
      );
    case 'unsupported':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-400/50 bg-rose-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-rose-800 dark:border-rose-400/40 dark:text-rose-200">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          Needs a stronger source
        </span>
      );
    case 'contradicted':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-red-400/60 bg-red-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-red-800 dark:border-red-500/40 dark:text-red-300">
          <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
          Conflicts with sources
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-300/70 bg-white/60 px-2.5 py-0.5 text-[12px] font-medium text-[#5E6A82] dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
          <Clock className="h-3.5 w-3.5" aria-hidden="true" />
          Opinion or general insight
        </span>
      );
  }
}

export function SourceStatusBadge({ status }: { status: SourceStatusType }) {
  if (status === 'retrieved') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-teal-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-teal-800 dark:text-teal-200">
        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
        Verified source
      </span>
    );
  }
  if (status === 'partially_retrieved') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/15 px-2.5 py-0.5 text-[12px] font-semibold text-amber-900 dark:text-amber-200">
        <RotateCw className="h-3 w-3" aria-hidden="true" />
        Partial preview
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2.5 py-0.5 text-[12px] font-semibold text-rose-800 dark:text-rose-200">
      <XCircle className="h-3 w-3" aria-hidden="true" />
      Could not open
    </span>
  );
}

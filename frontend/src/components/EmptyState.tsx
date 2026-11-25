import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export function EmptyState({
  icon,
  title,
  description,
  ctaLabel,
  ctaTo,
  onAction,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  ctaLabel?: string;
  ctaTo?: string;
  onAction?: () => void;
}) {
  return (
    <div className="glass-panel flex flex-col items-center justify-center rounded-3xl px-6 py-12 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500/20 via-violet-500/20 to-teal-400/20 text-indigo-600 ring-1 ring-indigo-400/30 dark:text-indigo-300">
        {icon}
      </div>
      <h3 className="mt-4 text-[16px] font-semibold text-[#131B2E] dark:text-white">{title}</h3>
      <p className="mt-1.5 max-w-sm text-[13px] text-[#5E6A82] dark:text-slate-300">
        {description}
      </p>
      {ctaLabel && ctaTo ? (
        <Link
          to={ctaTo}
          className="btn-aurora mt-5 inline-flex items-center rounded-full px-5 py-2.5 text-[13px] font-semibold"
        >
          {ctaLabel}
        </Link>
      ) : null}
      {ctaLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="btn-aurora mt-5 inline-flex items-center rounded-full px-5 py-2.5 text-[13px] font-semibold"
        >
          {ctaLabel}
        </button>
      ) : null}
    </div>
  );
}

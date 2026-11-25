import { Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';

export function DemoModeBanner({
  compact = false,
  reason,
}: {
  compact?: boolean;
  reason?: string;
}) {
  return (
    <div
      role="status"
      className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-300/75 bg-gradient-to-r from-amber-50/85 via-orange-50/75 to-yellow-50/80 text-amber-950 backdrop-blur-xl dark:border-amber-400/30 dark:from-amber-500/15 dark:via-orange-500/10 dark:to-yellow-500/15 dark:text-amber-100 ${
        compact ? 'px-4 py-2 text-[12px]' : 'px-4.5 py-3 text-[13px]'
      }`}
    >
      <div className="flex items-center gap-2.5">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-white shadow-xs">
          <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
        <span>
          <strong className="font-semibold">Demo Mode:</strong>{' '}
          {reason || 'Practicing with sample results — no live AI or search credits used.'}
        </span>
      </div>
      <Link
        to="/settings"
        className="text-[12px] font-semibold text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-300"
      >
        AI settings
      </Link>
    </div>
  );
}

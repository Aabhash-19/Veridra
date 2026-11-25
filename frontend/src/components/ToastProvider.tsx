import { useCallback, useState, type ReactNode } from 'react';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';
import { ToastContext, type ToastItem } from './toastContext';

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const pushToast = useCallback(
    (toast: Omit<ToastItem, 'id'>) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setToasts((prev) => [...prev.slice(-3), { ...toast, id }]);
      window.setTimeout(() => dismiss(id), 4500);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={{ pushToast }}>
      {children}
      <div
        role="region"
        aria-label="Notifications"
        aria-live="polite"
        className="fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2 px-4 sm:px-0"
      >
        {toasts.map((t) => {
          const icon =
            t.variant === 'success' ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-[#13A89E]" aria-hidden="true" />
            ) : t.variant === 'error' ? (
              <AlertCircle className="h-4 w-4 shrink-0 text-[#C84B31]" aria-hidden="true" />
            ) : (
              <Info className="h-4 w-4 shrink-0 text-[#5B5CE2]" aria-hidden="true" />
            );

          return (
            <div
              key={t.id}
              className="glass-panel flex items-start gap-3 rounded-2xl p-3.5"
            >
              <div className="mt-0.5">{icon}</div>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold text-[#162033] dark:text-slate-100">
                  {t.title}
                </p>
                {t.description ? (
                  <p className="mt-0.5 text-[12px] text-[#657187] dark:text-slate-400">
                    {t.description}
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss notification"
                className="rounded-md p-1 text-[#657187] hover:bg-[#F7F8FB] hover:text-[#162033] dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

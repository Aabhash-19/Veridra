import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from './api';
import type { RunEvent } from './types';

const TERMINAL_STATUSES = new Set(['completed', 'completed_with_warnings', 'failed', 'cancelled']);

export interface UseRunEventsState {
  events: RunEvent[];
  connectionState: 'idle' | 'connecting' | 'streaming' | 'fallback_polling' | 'closed';
}

export function useRunEvents(params: {
  runId: string;
  initialEvents?: RunEvent[];
  runStatus?: string;
  onEvent?: (evt: RunEvent) => void;
  onTerminal?: () => void;
}): UseRunEventsState {
  const { runId, initialEvents = [], runStatus, onEvent, onTerminal } = params;
  const [events, setEvents] = useState<RunEvent[]>(initialEvents);
  const [connectionState, setConnectionState] = useState<UseRunEventsState['connectionState']>('idle');
  const lastSeqRef = useRef<number>(0);
  const onEventRef = useRef(onEvent);
  const onTerminalRef = useRef(onTerminal);
  onEventRef.current = onEvent;
  onTerminalRef.current = onTerminal;

  useEffect(() => {
    if (!initialEvents.length) return;
    setEvents((prev) => {
      const bySeq = new Map<number, RunEvent>();
      for (const e of prev) bySeq.set(e.sequence, e);
      for (const e of initialEvents) {
        bySeq.set(e.sequence, e);
        lastSeqRef.current = Math.max(lastSeqRef.current, e.sequence);
      }
      return Array.from(bySeq.values()).sort((a, b) => a.sequence - b.sequence);
    });
  }, [initialEvents]);

  useEffect(() => {
    if (!runId) return;
    if (runStatus && TERMINAL_STATUSES.has(runStatus)) {
      setConnectionState('closed');
      return;
    }

    if (typeof EventSource === 'undefined') {
      setConnectionState('fallback_polling');
      return;
    }

    let closed = false;
    let source: EventSource | null = null;
    let reconnectTimer: number | null = null;
    let reconnectCount = 0;

    const connect = () => {
      if (closed) return;
      setConnectionState('connecting');
      const afterSeq = lastSeqRef.current;
      const url = `${API_BASE_URL}/api/v1/runs/${runId}/events?after_sequence=${afterSeq}`;
      source = new EventSource(url);

      source.onopen = () => {
        if (!closed) {
          reconnectCount = 0;
          setConnectionState('streaming');
        }
      };

      source.addEventListener('agent.progress', (messageEvent) => {
        try {
          const parsed = JSON.parse((messageEvent as MessageEvent).data) as RunEvent;
          lastSeqRef.current = Math.max(lastSeqRef.current, parsed.sequence);
          setEvents((prev) => {
            if (prev.some((x) => x.sequence === parsed.sequence)) return prev;
            return [...prev, parsed].sort((a, b) => a.sequence - b.sequence);
          });
          onEventRef.current?.(parsed);

          if (
            parsed.event_type === 'run.completed' ||
            parsed.event_type === 'run.failed' ||
            parsed.event_type === 'run.cancelled'
          ) {
            closed = true;
            setConnectionState('closed');
            source?.close();
            onTerminalRef.current?.();
          }
        } catch {
          // Ignore unparseable stream frames safely
        }
      });

      source.onerror = () => {
        source?.close();
        if (closed) return;
        reconnectCount += 1;
        if (reconnectCount <= 3) {
          setConnectionState('connecting');
          reconnectTimer = window.setTimeout(connect, 1000 * reconnectCount);
        } else {
          setConnectionState('fallback_polling');
        }
      };
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      source?.close();
    };
  }, [runId, runStatus]);

  return { events, connectionState };
}

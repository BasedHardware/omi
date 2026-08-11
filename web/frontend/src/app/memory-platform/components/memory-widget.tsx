'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/src/components/ui/input';
import { ScrollArea } from '@/src/components/ui/scroll-area';
import {
  MEMORY_PLATFORM_LIMITS,
  searchMemoryPlatform,
  type PlatformMemoryItem,
} from '@/src/lib/api/memory-platform';
import { useSessionToken } from '../hooks/use-session-token';
import { useEmbedSession } from '../hooks/use-embed-session';

export const WIDGET_READY_EVENT = 'omi.memory.embed.ready';
export const WIDGET_RESIZE_EVENT = 'omi.memory.embed.resize';

const SAMPLE_MEMORIES: PlatformMemoryItem[] = [
  {
    id: 'sample-1',
    content: 'The next launch review is Thursday at 10:00 with the hardware team.',
    category: 'manual',
  },
  {
    id: 'sample-2',
    content: 'Prefers async written updates over standups; reads them in the morning.',
    category: 'core',
  },
  {
    id: 'sample-3',
    content: 'zkr replicas apply only backend-acknowledged records.',
    category: 'system',
  },
];

interface MemoryWidgetProps {
  /**
   * Demo mode renders sample records and performs no network call, so the
   * public preview never requires a session or leaks a real memory.
   */
  demo?: boolean;
}

export default function MemoryWidget({ demo = false }: MemoryWidgetProps) {
  const { user, loading, getToken } = useSessionToken();
  const { framed, awaitingHost, getHostToken } = useEmbedSession();
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<PlatformMemoryItem[]>(demo ? SAMPLE_MEMORIES : []);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Typed, credential-free UI events only. A sandboxed frame has an opaque
  // origin, so the target is '*'; the receiver is responsible for validating
  // event.origin and event.source before acting on the message.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.parent.postMessage({ type: WIDGET_READY_EVENT }, '*');
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const height = rootRef.current?.scrollHeight ?? 0;
    window.parent.postMessage({ type: WIDGET_RESIZE_EVENT, height }, '*');
  }, [items, error, loading]);

  const visible = useMemo(() => {
    if (!demo) return items;
    const needle = query.trim().toLowerCase();
    if (!needle) return SAMPLE_MEMORIES;
    return SAMPLE_MEMORIES.filter((item) =>
      (item.content ?? '').toLowerCase().includes(needle),
    );
  }, [demo, items, query]);

  /**
   * A framed widget cannot reach Firebase: the documented sandbox gives it an
   * opaque origin with no storage access. Its credential comes from the host
   * page over postMessage instead. Top-level, the signed-in Firebase session is
   * still the source of truth.
   */
  const resolveToken = useCallback(async () => {
    if (framed) return getHostToken();
    return getToken();
  }, [framed, getHostToken, getToken]);

  const runSearch = useCallback(async () => {
    if (demo || pending) return;
    setError(null);
    const token = await resolveToken();
    if (!token) {
      setError(
        framed
          ? 'Waiting for the host page to provide a session.'
          : 'Sign in to search your canonical memory.',
      );
      return;
    }
    setPending(true);
    try {
      const response = await searchMemoryPlatform(token, { query, limit: 20 });
      setItems(response?.items ?? []);
    } catch {
      setError('Search is unavailable right now.');
    } finally {
      setPending(false);
    }
  }, [demo, framed, pending, resolveToken, query]);

  return (
    <div
      ref={rootRef}
      className="dark flex h-full flex-col gap-3 bg-[#0a0a0a] p-4 text-neutral-100"
    >
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-500"
            aria-hidden="true"
          />
          <Input
            value={query}
            maxLength={MEMORY_PLATFORM_LIMITS.maxQueryLength}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void runSearch();
            }}
            placeholder="Search memory"
            aria-label="Search memory"
            className="border-white/10 bg-white/[0.03] pl-8 text-neutral-100"
          />
        </div>
        <button
          type="button"
          onClick={() => void runSearch()}
          disabled={pending || demo}
          className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-neutral-300 transition-colors hover:border-white/20 hover:text-white disabled:opacity-40"
        >
          {pending ? 'Searching' : 'Search'}
        </button>
      </div>

      {demo ? (
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-neutral-600">
          Preview · sample records · no network call
        </p>
      ) : null}

      {error ? <p className="text-xs text-[#ff806a]">{error}</p> : null}
      {!demo && framed && awaitingHost ? (
        <p className="text-xs text-neutral-500">
          Waiting for the host page to provide a session.
        </p>
      ) : null}
      {!demo && !framed && !loading && !user ? (
        <p className="text-xs text-neutral-500">
          This widget reads through your own origin in production. Never ship a durable
          API key to the browser.
        </p>
      ) : null}

      <ScrollArea className="min-h-0 flex-1">
        <ul className="flex flex-col gap-2 pr-3">
          {visible.map((item, index) => (
            <li
              key={item.id ?? index}
              className="rounded-lg border border-white/10 bg-white/[0.02] p-3"
            >
              <p className="text-[13px] leading-6 text-neutral-200">{item.content}</p>
              {item.category ? (
                <span className="mt-2 inline-block font-mono text-[10px] uppercase tracking-[0.14em] text-neutral-500">
                  {item.category}
                </span>
              ) : null}
            </li>
          ))}
          {visible.length === 0 ? (
            <li className="rounded-lg border border-dashed border-white/10 p-6 text-center text-xs text-neutral-500">
              No memory matched.
            </li>
          ) : null}
        </ul>
      </ScrollArea>
    </div>
  );
}

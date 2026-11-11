import AsyncStorage from '@react-native-async-storage/async-storage';
import { DEMO_UID, useAuthStore } from '@/state/authStore';
import type { LocalBrainState } from './types';

const KEY_PREFIX = 'local.brain.v1.';
const SCHEMA_VERSION = 1;

function nowMs() {
  return Date.now();
}

function resolveOwnerScope(): string {
  const { uid, isDemo } = useAuthStore.getState();
  if (uid && !isDemo) return `account:${uid}`;
  if (isDemo || uid === DEMO_UID) return 'guest:demo';
  if (uid) return `guest:${uid}`;
  return 'guest:anon';
}

function keyForScope(scope: string): string {
  return `${KEY_PREFIX}${encodeURIComponent(scope)}`;
}

export function emptyBrainState(): LocalBrainState {
  return {
    schemaVersion: SCHEMA_VERSION,
    summaries: {},
    memories: {},
    tasks: {},
    profile: {
      updatedAt: nowMs(),
      traits: [],
      preferences: [],
      style: ['Be clear, reflective, and grounded in evidence from local recordings.'],
      boundaries: ['Do not invent memories or claim certainty without evidence.'],
      routines: [],
      evidence: [],
    },
    graph: { nodes: {}, edges: {} },
    processing: { version: 1, processedConversationIds: {} },
  };
}

function migrate(raw: unknown): LocalBrainState {
  const base = emptyBrainState();
  if (!raw || typeof raw !== 'object') return base;
  const r = raw as Record<string, any>;
  const v = typeof r.schemaVersion === 'number' ? r.schemaVersion : 0;
  const state: LocalBrainState = {
    ...base,
    ...r,
    schemaVersion: SCHEMA_VERSION,
    summaries: r.summaries && typeof r.summaries === 'object' ? r.summaries : {},
    memories: r.memories && typeof r.memories === 'object' ? r.memories : {},
    tasks: r.tasks && typeof r.tasks === 'object' ? r.tasks : {},
    profile: { ...base.profile, ...(r.profile && typeof r.profile === 'object' ? r.profile : {}) },
    graph: {
      nodes: r.graph?.nodes && typeof r.graph.nodes === 'object' ? r.graph.nodes : {},
      edges: r.graph?.edges && typeof r.graph.edges === 'object' ? r.graph.edges : {},
    },
    processing: {
      version: 1,
      processedConversationIds:
        r.processing?.processedConversationIds && typeof r.processing.processedConversationIds === 'object'
          ? r.processing.processedConversationIds
          : {},
      lastRunAt: r.processing?.lastRunAt,
    },
  };
  if (v !== SCHEMA_VERSION) {
    state.schemaVersion = SCHEMA_VERSION;
  }
  return state;
}

type Cache = { scope: string; state: LocalBrainState | null; promise: Promise<LocalBrainState> | null };
let cache: Cache = { scope: '', state: null, promise: null };

export async function loadBrainState(): Promise<LocalBrainState> {
  const scope = resolveOwnerScope();
  if (cache.scope !== scope) {
    cache = { scope, state: null, promise: null };
  }
  if (cache.state) return cache.state;
  if (cache.promise) return cache.promise;
  const scopeAtStart = scope;
  cache.promise = (async () => {
    try {
      const raw = await AsyncStorage.getItem(keyForScope(scopeAtStart));
      const parsed = raw ? JSON.parse(raw) : null;
      const state = migrate(parsed);
      if (cache.scope === scopeAtStart) cache.state = state;
      return state;
    } catch {
      const state = emptyBrainState();
      if (cache.scope === scopeAtStart) cache.state = state;
      return state;
    } finally {
      if (cache.scope === scopeAtStart) cache.promise = null;
    }
  })();
  return cache.promise;
}

export async function saveBrainState(next: LocalBrainState): Promise<void> {
  const scope = resolveOwnerScope();
  cache = { scope, state: next, promise: null };
  try {
    await AsyncStorage.setItem(keyForScope(scope), JSON.stringify(next));
  } catch (e) {
    console.warn('[localBrain] persist failed:', e);
  }
}

export async function updateBrainState(
  updater: (prev: LocalBrainState) => LocalBrainState | void
): Promise<LocalBrainState> {
  const prev = await loadBrainState();
  // shallow-clone top-level containers for safe mutation in updaters
  const draft: LocalBrainState = {
    ...prev,
    summaries: { ...prev.summaries },
    memories: { ...prev.memories },
    tasks: { ...prev.tasks },
    profile: { ...prev.profile },
    graph: { nodes: { ...prev.graph.nodes }, edges: { ...prev.graph.edges } },
    processing: { ...prev.processing, processedConversationIds: { ...prev.processing.processedConversationIds } },
  };
  const result = updater(draft);
  const next = (result ?? draft) as LocalBrainState;
  await saveBrainState(next);
  return next;
}

export function resetBrainCacheForTests(): void {
  cache = { scope: '', state: null, promise: null };
}

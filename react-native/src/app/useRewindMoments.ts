import {useCallback, useEffect, useRef, useState} from 'react';
import {AppState, NativeModules, Platform} from 'react-native';
import {omiBackend} from '../omiNative';
import {
  loadRewindMoments,
  recallFromMoment,
  upsertRewindMoment,
  type RewindMomentRecord,
} from '../rewindMomentsClient';
import {createRewindTimeline} from '../desktop/rewindTimeline';
import type {TimelineRecall} from '../timeline/mixedTimeline';

type Frame = {
  id: string;
  capturedAtMs: number;
  appName: string;
  windowTitle: string;
};

type Rewind = {
  listFrames(input: {
    source: 'shipping' | 'captured';
    query: string;
    cursor: string | null;
    limit: number;
  }): Promise<{frames: Frame[]; nextCursor: string | null}>;
};

export type RewindMomentsState = {
  items: TimelineRecall[];
  status: 'idle' | 'loading' | 'ready' | 'unavailable' | 'error';
  error: string | null;
  sync: 'idle' | 'saving' | 'saved' | 'unavailable' | 'error';
  syncError: string | null;
  refresh: () => void;
};

function localRecall(frame: Frame): TimelineRecall {
  const source = frame.id.startsWith('shipping:') ? 'shipping' : 'captured';
  return {
    kind: 'recall',
    id: frame.id,
    appName: frame.appName || 'Captured screen',
    windowTitle: frame.windowTitle,
    searchableText: `${frame.appName} ${frame.windowTitle}`,
    atMs: frame.capturedAtMs,
    source,
    local: true,
  };
}

function toMoment(frame: Frame): RewindMomentRecord | null {
  if (frame.id.length > 200) {
    return null;
  }
  const source = frame.id.startsWith('shipping:')
    ? 'shipping'
    : frame.id.startsWith('captured:')
    ? 'captured'
    : null;
  if (source === null) {
    return null;
  }
  return {
    frameId: frame.id,
    capturedAtMs: frame.capturedAtMs,
    appName: (frame.appName || 'Captured screen').slice(0, 256),
    windowTitle: frame.windowTitle.slice(0, 1024),
    source,
    ocrPreview: '',
  };
}

export function useRewindMoments(enabled: boolean): RewindMomentsState {
  const [items, setItems] = useState<TimelineRecall[]>([]);
  const [status, setStatus] = useState<RewindMomentsState['status']>('idle');
  const [error, setError] = useState<string | null>(null);
  const [sync, setSync] = useState<RewindMomentsState['sync']>('idle');
  const [syncError, setSyncError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const epoch = useRef(0);
  const paginated = useRef(false);
  const loading = useRef(false);
  const appState = useRef(AppState.currentState);
  const refresh = useCallback(() => setRevision(value => value + 1), []);

  useEffect(() => {
    if (!enabled) {
      epoch.current += 1;
      setItems([]);
      setStatus('idle');
      setError(null);
      setSync('idle');
      setSyncError(null);
      return;
    }
    const current = (epoch.current += 1);
    loading.current = true;
    setStatus(previous => (previous === 'ready' ? previous : 'loading'));
    setError(null);
    const native =
      Platform.OS === 'macos'
        ? (NativeModules.OmiRewind as Rewind | undefined)
        : undefined;
    const backend = omiBackend;
    const load = async () => {
      const local: TimelineRecall[] = [];
      let localError: string | null = null;
      if (native !== undefined) {
        try {
          const timeline = createRewindTimeline(native, '');
          const page = await timeline.next();
          local.push(...page.frames.map(localRecall));
          if (page.warning) {
            localError = page.warning;
          }
        } catch (failure) {
          const code = (failure as {code?: string} | null)?.code;
          localError =
            code === 'OMI_REWIND_UNAVAILABLE'
              ? 'No local Recall history is available on this device.'
              : code === 'OMI_REWIND_AUTH' || code === 'OMI_REWIND_OWNER_CHANGED'
              ? 'Sign in again to open your screen history.'
              : 'Screen history could not be loaded.';
        }
      } else if (Platform.OS === 'macos') {
        localError = 'No local Recall history is available on this device.';
      }

      let remote: TimelineRecall[] = [];
      let remoteError: string | null = null;
      if (backend === undefined || backend === null) {
        remoteError = 'Recall cannot save until this app has a signed-in backend.';
        if (epoch.current === current) {
          setSync('unavailable');
          setSyncError(remoteError);
        }
      } else {
        try {
          const page = await loadRewindMoments(backend);
          remote = page.items.map(recallFromMoment);
        } catch {
          remoteError = 'Saved Recall metadata could not be loaded.';
        }
      }

      if (epoch.current !== current) {
        return;
      }
      const merged = [...local, ...remote];
      setItems(merged);
      if (local.length === 0 && remote.length === 0 && (localError || remoteError)) {
        setStatus('error');
        setError(localError ?? remoteError);
      } else {
        setStatus('ready');
        setError(localError ?? remoteError);
      }

      if (backend && local.length > 0) {
        setSync('saving');
        let failed = 0;
        for (const frame of local) {
          const moment = toMoment({
            id: frame.id,
            capturedAtMs: frame.atMs ?? 0,
            appName: frame.appName,
            windowTitle: frame.windowTitle,
          });
          if (moment === null || moment.capturedAtMs === 0) {
            continue;
          }
          try {
            await upsertRewindMoment(backend, moment);
          } catch {
            failed += 1;
          }
          if (epoch.current !== current) {
            return;
          }
        }
        if (epoch.current !== current) {
          return;
        }
        if (failed > 0) {
          setSync('error');
          setSyncError(
            'Some screen history stayed on this device and was not saved to your account.',
          );
        } else {
          setSync('saved');
          setSyncError(null);
        }
      } else if (backend && local.length === 0 && Platform.OS !== 'macos') {
        setSync(remoteError ? 'error' : 'idle');
      }
    };
    load()
      .catch(() => {
        if (epoch.current === current) {
          setStatus('error');
          setError('Screen history could not be loaded.');
        }
      })
      .finally(() => {
        if (epoch.current === current) {
          loading.current = false;
        }
      });
    return () => {
      epoch.current += 1;
    };
  }, [enabled, revision]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const tick = () => {
      if (
        !loading.current &&
        !paginated.current &&
        appState.current === 'active'
      ) {
        setRevision(value => value + 1);
      }
    };
    const listener = AppState.addEventListener('change', state => {
      appState.current = state;
      if (state === 'active') {
        tick();
      }
    });
    const timer = setInterval(tick, 15000);
    return () => {
      clearInterval(timer);
      listener.remove();
    };
  }, [enabled]);

  return {items, status, error, sync, syncError, refresh};
}

import React, {useEffect, useMemo, useRef, useState} from 'react';
import {NativeModules, Text, View} from 'react-native';
import type {DesktopReadOutcomes} from '../desktopReadClient';
import {omiBackend} from '../omiNative';
import {useOmiStyles} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';

// "At a glance": an AI-composed line from the v5 worker (live Mac context,
// recent topics), with a local "now on your Mac" / fun-fact fallback.
// It exists only on the v5 backend. On the legacy (api.omi.me) backend the
// worker endpoint does not exist, so the card would only ever show its
// fallback; there the Activity page shows no glance at all.

export type BackendContract = 'omi' | 'canonical';

/** Resolves which backend contract the session talks to; null until known. */
export function useBackendContract(): BackendContract | null {
  const [contract, setContract] = useState<BackendContract | null>(null);
  useEffect(() => {
    let cancelled = false;
    const backend = omiBackend;
    if (backend?.getApiContract === undefined) {
      return;
    }
    // Tolerate a bridge that returns a plain value or throws: the glance is
    // optional and must never break Activity.
    Promise.resolve()
      .then(() => backend.getApiContract?.())
      .then(value => {
        if (!cancelled && (value === 'omi' || value === 'canonical')) {
          setContract(value);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return contract;
}

type GlanceFrame = {
  capturedAtMs: number;
  appName: string;
  windowTitle: string;
};

const GLANCE_FRAME_FRESH_MS = 5 * 60 * 1000;
const GLANCE_POLL_MS = 15000;
const GLANCE_REFRESH_MS = 5 * 60 * 1000;

type GlanceLine = {title: string; copy: string};

/**
 * Asks the v5 worker for an AI-composed glance line (live Mac context, recent
 * topics, weather). Any failure — old backend, offline, malformed response —
 * simply leaves the local line in place, so the glance always renders
 * something.
 */
function useRemoteGlanceLine(input: {
  frame: GlanceFrame | null;
  counts: {conversations: number; memories: number; tasks: number};
  topics: string[];
}): GlanceLine | null {
  const [line, setLine] = useState<GlanceLine | null>(null);
  const fetchedAtRef = useRef(0);
  const topicsKey = input.topics.join('\n');
  const contextKey = `${input.frame?.appName ?? ''}|${
    input.counts.conversations
  }|${input.counts.memories}|${input.counts.tasks}|${topicsKey}`;
  useEffect(() => {
    let cancelled = false;
    const fetchLine = async () => {
      const backend = omiBackend;
      if (backend === undefined || backend === null) {
        return;
      }
      if ((await backend.getApiContract?.()) !== 'canonical') {
        return;
      }
      const response = await backend.request({
        id: 'desktop-glance',
        method: 'POST',
        expectedApiContract: 'canonical',
        path: '/v1/desktop/glance',
        body: JSON.stringify({
          frontApp: input.frame?.appName.slice(0, 120) ?? '',
          windowTitle: input.frame?.windowTitle.slice(0, 120) ?? '',
          counts: input.counts,
          topics: input.topics,
          localTimeIso: new Date().toISOString(),
        }),
      });
      if (cancelled || response.status !== 200 || response.body == null) {
        return;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(response.body);
      } catch {
        return;
      }
      if (
        parsed !== null &&
        typeof parsed === 'object' &&
        typeof (parsed as {title?: unknown}).title === 'string' &&
        typeof (parsed as {copy?: unknown}).copy === 'string'
      ) {
        const candidate = parsed as {title: string; copy: string};
        if (candidate.title.length > 0 && candidate.copy.length > 0) {
          setLine({title: candidate.title, copy: candidate.copy});
        }
      }
    };
    const now = Date.now();
    if (now - fetchedAtRef.current >= GLANCE_REFRESH_MS) {
      fetchedAtRef.current = now;
      void fetchLine().catch(() => undefined);
    }
    const timer = setInterval(() => {
      if (
        !cancelled &&
        Date.now() - fetchedAtRef.current >= GLANCE_REFRESH_MS
      ) {
        fetchedAtRef.current = Date.now();
        void fetchLine().catch(() => undefined);
      }
    }, 30000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // contextKey refreshes the line when the user's live context shifts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contextKey]);
  return line;
}

// Local fun-fact fallback for when there is no live frame and the worker line
// has not arrived: the glance is never placeholder filler, it is at least
// genuinely fun. Deterministic rotation by time of day, no network needed.
const GLANCE_FUN_LINES: {title: string; copy: string}[] = [
  {
    title: 'Three hearts',
    copy: 'An octopus has three hearts, and two of them stop beating whenever it swims.',
  },
  {
    title: 'Eternal honey',
    copy: 'Honey found in ancient Egyptian tombs is still considered safe to eat.',
  },
  {
    title: 'Older than trees',
    copy: 'Sharks were already swimming the oceans before trees existed.',
  },
  {
    title: 'Venus days',
    copy: 'A single day on Venus stretches on longer than its whole year around the Sun.',
  },
  {
    title: "Scotland's unicorn",
    copy: 'The unicorn is the official national animal of Scotland.',
  },
  {
    title: 'Shortest war',
    copy: 'The Anglo-Zanzibar War of 1896 lasted around 38 minutes.',
  },
  {
    title: 'Otter handholding',
    copy: 'Sea otters hold hands while they sleep so they do not drift apart.',
  },
  {
    title: 'Berry confusion',
    copy: 'Bananas count as berries, while strawberries famously do not.',
  },
];

/**
 * Reads the newest local Recall frame so At a glance can show live "now on
 * your Mac" activity. Polls cheaply while Home is mounted; any failure or a
 * stale frame simply falls back to the day summary.
 */
function useGlanceFrame(): GlanceFrame | null {
  const [frame, setFrame] = useState<GlanceFrame | null>(null);
  useEffect(() => {
    const bridge = NativeModules.OmiRewind as
      | {
          listFrames(input: {
            source: 'captured';
            query: string;
            cursor: string | null;
            limit: number;
          }): Promise<{frames: GlanceFrame[]}>;
        }
      | undefined;
    if (bridge == null) {
      return;
    }
    let retired = false;
    const read = async () => {
      try {
        const page = await bridge!.listFrames({
          source: 'captured',
          query: '',
          cursor: null,
          limit: 1,
        });
        if (!retired) {
          setFrame(page.frames[0] ?? null);
        }
      } catch {
        // Unavailable, auth, or owner change: Home already reports read
        // health; the glance line just falls back.
        if (!retired) {
          setFrame(null);
        }
      }
    };
    void read();
    const timer = setInterval(read, GLANCE_POLL_MS);
    return () => {
      retired = true;
      clearInterval(timer);
    };
  }, []);
  return frame;
}

function glanceLine({
  frame,
  minuteOfDay,
}: {
  frame: GlanceFrame | null;
  minuteOfDay: number;
}): {title: string; copy: string} {
  if (
    frame != null &&
    Date.now() - frame.capturedAtMs < GLANCE_FRAME_FRESH_MS &&
    frame.appName.length > 0
  ) {
    return {
      title: 'Now on your Mac',
      copy:
        frame.windowTitle.length > 0
          ? `${frame.appName} — ${frame.windowTitle}`
          : frame.appName,
    };
  }
  return GLANCE_FUN_LINES[
    Math.floor(minuteOfDay / 30) % GLANCE_FUN_LINES.length
  ];
}

function GlanceCardContent({outcomes}: {outcomes: DesktopReadOutcomes | null}) {
  const styles = useOmiStyles(createStyles);
  const frame = useGlanceFrame();
  const [minuteOfDay, setMinuteOfDay] = useState(() => {
    const now = new Date();
    return now.getHours() * 60 + now.getMinutes();
  });
  const mounted = useRef(true);
  useEffect(() => {
    const timer = setInterval(() => {
      const now = new Date();
      const next = now.getHours() * 60 + now.getMinutes();
      if (mounted.current) {
        setMinuteOfDay(next);
      }
    }, 20000);
    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, []);
  const conversations =
    outcomes?.conversations?.status === 'success'
      ? outcomes.conversations.value.items.length
      : 0;
  const memories =
    outcomes?.memories?.status === 'success'
      ? outcomes.memories.value.items.length
      : 0;
  const tasks =
    outcomes?.tasks?.status === 'success'
      ? outcomes.tasks.value.items.length
      : 0;
  // Recent conversation titles, then memory titles: trimmed, deduplicated,
  // capped at six, so the worker can tailor the glance to what the user has
  // actually been thinking about.
  const topics = useMemo(() => {
    const titles: string[] = [];
    const push = (title: string) => {
      const trimmed = title.trim();
      if (trimmed.length > 0 && !titles.includes(trimmed)) {
        titles.push(trimmed.slice(0, 80));
      }
    };
    if (outcomes?.conversations?.status === 'success') {
      for (const item of outcomes.conversations.value.items) {
        push(item.title);
      }
    }
    if (outcomes?.memories?.status === 'success') {
      for (const item of outcomes.memories.value.items) {
        push(item.title);
      }
    }
    return titles.slice(0, 6);
  }, [outcomes]);
  const remote = useRemoteGlanceLine({
    counts: {conversations, memories, tasks},
    frame,
    topics,
  });
  const line = remote ?? glanceLine({frame, minuteOfDay});
  return (
    <View accessibilityLabel="At a glance" style={styles.root}>
      <Text accessibilityRole="header" style={styles.title}>
        {line.title}
      </Text>
      <Text style={styles.copy}>{line.copy}</Text>
    </View>
  );
}

/** Renders the glance on the v5 backend only; nothing on the legacy backend. */
export function GlanceCard({outcomes}: {outcomes: DesktopReadOutcomes | null}) {
  const contract = useBackendContract();
  if (contract !== 'canonical') {
    return null;
  }
  return <GlanceCardContent outcomes={outcomes} />;
}

const createStyles = (t: OmiTheme) => ({
  root: {
    gap: t.space.xs,
    paddingTop: t.space.sm,
    paddingBottom: t.space.lg,
    paddingHorizontal: t.space.sm,
  },
  title: {...t.type.title, color: t.color.ink},
  copy: {...t.type.body, color: t.color.inkSecondary},
});

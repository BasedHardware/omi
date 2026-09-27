export type RewindFrame = {
  id: string;
  capturedAtMs: number;
  appName: string;
  windowTitle: string;
};
// Consecutive frames over the same window collapse into one timeline moment.
// The gap bound keeps a capture that paused (sleep, stop/start) from merging
// into the previous session even though app and title match.
export type RewindCaptureGroup = {
  id: string;
  frame: RewindFrame;
  appName: string;
  windowTitle: string;
  capturedAtMs: number;
  firstCapturedAtMs: number;
  count: number;
};
const GROUP_GAP_MS = 12 * 60 * 1000;

export function groupRewindFrames(frames: RewindFrame[]): RewindCaptureGroup[] {
  const groups: RewindCaptureGroup[] = [];
  for (const frame of frames) {
    const previous = groups[groups.length - 1];
    const sameWindow =
      previous !== undefined &&
      previous.appName === frame.appName &&
      previous.windowTitle === frame.windowTitle;
    const contiguous =
      previous !== undefined &&
      previous.firstCapturedAtMs - frame.capturedAtMs <= GROUP_GAP_MS;
    if (sameWindow && contiguous) {
      previous.count += 1;
      previous.firstCapturedAtMs = frame.capturedAtMs;
      continue;
    }
    groups.push({
      id: frame.id,
      frame,
      appName: frame.appName,
      windowTitle: frame.windowTitle,
      capturedAtMs: frame.capturedAtMs,
      firstCapturedAtMs: frame.capturedAtMs,
      count: 1,
    });
  }
  return groups;
}
type Source = 'captured' | 'shipping';
export type RewindTimelineBridge = {
  listFrames(input: {
    source: Source;
    query: string;
    cursor: string | null;
    limit: number;
  }): Promise<{frames: RewindFrame[]; nextCursor: string | null}>;
};
type TimelinePage = {frames: RewindFrame[]; next: boolean; warning?: string};

export function createRewindTimeline(
  bridge: RewindTimelineBridge,
  query: string,
) {
  const sources = (['captured', 'shipping'] as const).map(source => ({
    source,
    frames: [] as RewindFrame[],
    cursor: null as string | null,
    done: false,
    readable: false,
  }));
  let failure: unknown;
  let retired = false;
  let warning: string | undefined;
  let pending: Promise<TimelinePage> | undefined;

  async function refill(source: (typeof sources)[number]) {
    if (source.frames.length || source.done) return;
    try {
      const page = await bridge.listFrames({
        source: source.source,
        query,
        cursor: source.cursor,
        limit: 50,
      });
      source.frames = [...page.frames];
      source.cursor = page.nextCursor;
      source.done = page.nextCursor === null;
      source.readable = true;
    } catch (error) {
      const code = (error as {code?: string} | null)?.code;
      if (code === 'OMI_REWIND_AUTH' || code === 'OMI_REWIND_OWNER_CHANGED') {
        retired = true;
        failure = error;
        throw error;
      }
      source.done = true;
      if (code !== 'OMI_REWIND_UNAVAILABLE') {
        if (!retired) failure = error;
        warning = 'Some screen history could not be loaded.';
      }
    }
  }

  async function read(): Promise<TimelinePage> {
    if (retired) throw failure;
    const frames: RewindFrame[] = [];
    while (frames.length < 50) {
      // Refill both heads before choosing: a source's next page can precede
      // the other source's buffered frames. Equal times prefer captured.
      await Promise.all(sources.map(refill));
      if (retired) throw failure;
      const available = sources.filter(source => source.frames.length);
      if (!available.length) {
        if (sources.some(source => !source.done)) continue;
        break;
      }
      const newest = available.reduce((left, right) =>
        left.frames[0].capturedAtMs >= right.frames[0].capturedAtMs
          ? left
          : right,
      );
      frames.push(newest.frames.shift()!);
    }
    if (warning && !sources.some(source => source.readable)) throw failure;
    return {
      frames,
      next: sources.some(source => source.frames.length > 0 || !source.done),
      ...(warning ? {warning} : {}),
    };
  }

  return {
    next(): Promise<TimelinePage> {
      if (!pending)
        pending = read().finally(() => {
          pending = undefined;
        });
      return pending;
    },
  };
}

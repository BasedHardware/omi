export type RewindFrame = {
  id: string;
  capturedAtMs: number;
  appName: string;
  windowTitle: string;
};
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

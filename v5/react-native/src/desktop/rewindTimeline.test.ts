import {
  createRewindTimeline,
  RewindFrame,
  RewindTimelineBridge,
} from './rewindTimeline';

function frame(id: string, capturedAtMs: number): RewindFrame {
  return {id, capturedAtMs, appName: 'Browser', windowTitle: id};
}

test('merges interleaved source pages without omissions or reordered page boundaries', async () => {
  const captured = Array.from({length: 127}, (_, index) =>
    frame(`captured:${index}`, 1000 - index * 2),
  );
  const shipping = Array.from({length: 117}, (_, index) =>
    frame(`shipping:${index}`, 999 - index * 2),
  );
  const listFrames = jest.fn<
    ReturnType<RewindTimelineBridge['listFrames']>,
    Parameters<RewindTimelineBridge['listFrames']>
  >(async ({source, cursor, limit, query}) => {
    expect(query).toBe('work');
    expect(limit).toBe(50);
    const data = source === 'captured' ? captured : shipping;
    const start = Number(cursor ?? 0);
    return {
      frames: data.slice(start, start + limit),
      nextCursor: start + limit < data.length ? String(start + limit) : null,
    };
  });
  const timeline = createRewindTimeline({listFrames}, 'work');
  const result: RewindFrame[] = [];
  let more = true;
  while (more) {
    const page = await timeline.next();
    expect(page.frames.length).toBeLessThanOrEqual(50);
    result.push(...page.frames);
    more = page.next;
  }
  expect(result).toEqual(
    [...captured, ...shipping].sort((a, b) => b.capturedAtMs - a.capturedAtMs),
  );
  expect(listFrames).toHaveBeenCalledTimes(6);
});

test('keeps deterministic ties across a source page boundary', async () => {
  const captured = Array.from({length: 51}, (_, index) =>
    frame(`captured:${index}`, 10),
  );
  const timeline = createRewindTimeline(
    {
      listFrames: async ({source, cursor}) =>
        source === 'shipping'
          ? {frames: [frame('shipping:1', 10)], nextCursor: null}
          : {
              frames: cursor ? captured.slice(50) : captured.slice(0, 50),
              nextCursor: cursor ? null : 'next',
            },
    },
    '',
  );
  expect((await timeline.next()).frames).toEqual(captured.slice(0, 50));
  expect((await timeline.next()).frames.map(value => value.id)).toEqual([
    'captured:50',
    'shipping:1',
  ]);
});

test('missing history is normal but a failed readable source is reported', async () => {
  for (const code of ['OMI_REWIND_UNAVAILABLE', 'OMI_REWIND_STORAGE']) {
    const timeline = createRewindTimeline(
      {
        listFrames: async ({source}) => {
          if (source === 'shipping') throw {code};
          return {frames: [frame('captured:1', 10)], nextCursor: null};
        },
      },
      '',
    );
    const page = await timeline.next();
    expect(page.frames).toHaveLength(1);
    expect(page.next).toBe(false);
    expect(Boolean(page.warning)).toBe(code !== 'OMI_REWIND_UNAVAILABLE');
  }
});

test('all unreadable failures reject and account failures retire the reader', async () => {
  for (const code of [
    'OMI_REWIND_STORAGE',
    'OMI_REWIND_AUTH',
    'OMI_REWIND_OWNER_CHANGED',
  ]) {
    const error = {code};
    const timeline = createRewindTimeline(
      {
        listFrames: async ({source}) => {
          if (source === 'shipping' || code === 'OMI_REWIND_STORAGE')
            throw error;
          return {frames: [frame('captured:1', 10)], nextCursor: null};
        },
      },
      '',
    );
    await expect(timeline.next()).rejects.toBe(error);
    await expect(timeline.next()).rejects.toBe(error);
  }
});

test('a later source failure retains readable history with a persistent warning', async () => {
  const captured = Array.from({length: 50}, (_, index) =>
    frame(`captured:${index}`, 100 - index),
  );
  const timeline = createRewindTimeline(
    {
      listFrames: async ({source, cursor}) => {
        if (source === 'shipping')
          return {frames: [frame('shipping:1', 0)], nextCursor: null};
        if (cursor) throw {code: 'OMI_REWIND_STORAGE'};
        return {frames: captured, nextCursor: 'next'};
      },
    },
    '',
  );
  expect((await timeline.next()).frames).toEqual(captured);
  const page = await timeline.next();
  expect(page.frames.map(value => value.id)).toEqual(['shipping:1']);
  expect(page.warning).toBe('Some screen history could not be loaded.');
  expect(page.next).toBe(false);
});

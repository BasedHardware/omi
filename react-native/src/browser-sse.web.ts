const DEFAULT_MAX_ATTEMPTS = 4;

type OpenStream = (
  lastEventId: string | null,
  signal: AbortSignal,
) => Promise<Response>;

export type BrowserGenerationStreamOptions = {
  initialLastEventId: string | null;
  open: OpenStream;
  signal: AbortSignal;
  maxAttempts?: number;
};

export type BrowserGenerationStreamResult = {
  body: string | null;
  retryAfterSeconds: number | null;
  status: number;
};

export class BrowserGenerationCancelledError extends Error {
  readonly code = 'OMI_HTTP_CANCELLED';

  constructor() {
    super('Browser generation stream was cancelled');
    this.name = 'BrowserGenerationCancelledError';
  }
}

export class BrowserGenerationRecoveryError extends Error {
  readonly code = 'OMI_HTTP_STREAM_RECOVERY_EXHAUSTED';

  constructor(readonly attempts: number) {
    super(
      `Browser generation stream recovery exhausted after ${attempts} attempts`,
    );
    this.name = 'BrowserGenerationRecoveryError';
  }
}

class BrowserStreamDisconnectedError extends Error {
  constructor(readonly body: string, readonly lastEventId: string | null) {
    super('Browser generation stream disconnected before a terminal event');
    this.name = 'BrowserStreamDisconnectedError';
  }
}

type StreamEvent = {
  data: string;
  id: string | null;
  raw: string;
};

type ConnectionResult = {
  body: string;
  lastEventId: string | null;
};

function retryAfterSeconds(response: Response): number | null {
  const value = Number(response.headers.get('retry-after'));
  return Number.isInteger(value) && value > 0 && value <= 3600 ? value : null;
}

function isTransientStatus(status: number): boolean {
  return (
    status === 408 ||
    status === 429 ||
    status === 500 ||
    status === 502 ||
    status === 503 ||
    status === 504
  );
}

function eventKind(data: string): string | null {
  try {
    const value: unknown = JSON.parse(data);
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
      return null;
    }
    const kind = (value as {kind?: unknown}).kind;
    return typeof kind === 'string' ? kind : null;
  } catch {
    return null;
  }
}

function isTerminalKind(kind: string | null): boolean {
  return kind === 'done' || kind === 'failed' || kind === 'cancelled';
}

function isAbortError(error: unknown, signal: AbortSignal): boolean {
  return (
    signal.aborted ||
    (error instanceof DOMException && error.name === 'AbortError')
  );
}

function retryDelayMs(response: Response | null): number {
  const retryAfter = response === null ? null : retryAfterSeconds(response);
  return retryAfter === null ? 0 : retryAfter * 1000;
}

function waitForRetry(delayMs: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    return Promise.reject(new BrowserGenerationCancelledError());
  }
  if (delayMs === 0) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    let timer: ReturnType<typeof setTimeout>;
    const onAbort = () => {
      clearTimeout(timer);
      reject(new BrowserGenerationCancelledError());
    };
    timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, delayMs);
    signal.addEventListener('abort', onAbort, {once: true});
    if (signal.aborted) {
      onAbort();
    }
  });
}

async function readConnection(
  response: Response,
  signal: AbortSignal,
  seenEventIds: Set<string>,
): Promise<ConnectionResult> {
  if (signal.aborted) {
    throw new BrowserGenerationCancelledError();
  }
  const reader = response.body?.getReader();
  if (reader === undefined) {
    throw new BrowserStreamDisconnectedError('', null);
  }

  const decoder = new TextDecoder();
  let lineBuffer = '';
  let eventId: string | null = null;
  let eventData: string[] = [];
  let eventLines: string[] = [];
  let lastEventId: string | null = null;
  let body = '';
  let terminal = false;

  const dispatch = (): void => {
    if (eventData.length === 0) {
      eventId = null;
      eventLines = [];
      return;
    }
    const event: StreamEvent = {
      data: eventData.join('\n'),
      id: eventId,
      raw: `${eventLines.join('\n')}\n\n`,
    };
    if (event.id !== null) {
      lastEventId = event.id;
    }
    if (event.id === null || !seenEventIds.has(event.id)) {
      if (event.id !== null) {
        seenEventIds.add(event.id);
      }
      body += event.raw;
      terminal = terminal || isTerminalKind(eventKind(event.data));
    }
    eventId = null;
    eventData = [];
    eventLines = [];
  };

  const processLine = (line: string): void => {
    if (line === '') {
      dispatch();
      return;
    }
    if (line.startsWith(':')) {
      return;
    }
    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    const value =
      separator === -1
        ? ''
        : line.charAt(separator + 1) === ' '
        ? line.slice(separator + 2)
        : line.slice(separator + 1);
    if (field === 'id') {
      eventId = value;
      eventLines.push(line);
    } else if (field === 'event') {
      eventLines.push(line);
    } else if (field === 'data') {
      eventData.push(value);
      eventLines.push(line);
    }
  };

  const processText = (text: string): void => {
    lineBuffer += text;
    for (;;) {
      const match = /\r\n|\r|\n/.exec(lineBuffer);
      if (match === null || match.index === undefined) {
        return;
      }
      processLine(lineBuffer.slice(0, match.index));
      lineBuffer = lineBuffer.slice(match.index + match[0].length);
      if (terminal) {
        return;
      }
    }
  };

  try {
    while (!terminal) {
      const result = await reader.read();
      if (result.done) {
        processText(decoder.decode());
        if (lineBuffer !== '') {
          processLine(lineBuffer);
        }
        dispatch();
        break;
      }
      processText(decoder.decode(result.value, {stream: true}));
    }
    if (terminal) {
      await reader.cancel();
      return {body, lastEventId};
    }
    throw new BrowserStreamDisconnectedError(body, lastEventId);
  } catch (error) {
    if (isAbortError(error, signal)) {
      throw new BrowserGenerationCancelledError();
    }
    if (error instanceof BrowserStreamDisconnectedError) {
      throw error;
    }
    throw new BrowserStreamDisconnectedError(body, lastEventId);
  } finally {
    reader.releaseLock();
  }
}

export async function readBrowserGenerationEvents(
  options: BrowserGenerationStreamOptions,
): Promise<BrowserGenerationStreamResult> {
  const maxAttempts = options.maxAttempts ?? DEFAULT_MAX_ATTEMPTS;
  const seenEventIds = new Set<string>();
  let lastEventId = options.initialLastEventId;
  let body = '';
  let lastResponse: Response | null = null;
  if (lastEventId !== null) {
    seenEventIds.add(lastEventId);
  }

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    if (options.signal.aborted) {
      throw new BrowserGenerationCancelledError();
    }
    try {
      const response = await options.open(lastEventId, options.signal);
      lastResponse = response;
      if (response.status !== 200) {
        if (!isTransientStatus(response.status)) {
          const responseBody = await response.text();
          return {
            body: responseBody === '' ? null : responseBody,
            retryAfterSeconds: retryAfterSeconds(response),
            status: response.status,
          };
        }
        await response.text();
        if (attempt === maxAttempts) {
          throw new BrowserGenerationRecoveryError(maxAttempts);
        }
        await waitForRetry(retryDelayMs(response), options.signal);
        continue;
      }

      const connection = await readConnection(
        response,
        options.signal,
        seenEventIds,
      );
      body += connection.body;
      lastEventId = connection.lastEventId ?? lastEventId;
      return {
        body: body === '' ? null : body,
        retryAfterSeconds: null,
        status: 200,
      };
    } catch (error) {
      if (error instanceof BrowserGenerationCancelledError) {
        throw error;
      }
      if (options.signal.aborted) {
        throw new BrowserGenerationCancelledError();
      }
      if (error instanceof BrowserStreamDisconnectedError) {
        body += error.body;
        lastEventId = error.lastEventId ?? lastEventId;
      }
      if (attempt === maxAttempts) {
        throw new BrowserGenerationRecoveryError(maxAttempts);
      }
      await waitForRetry(retryDelayMs(lastResponse), options.signal);
    }
  }

  throw new BrowserGenerationRecoveryError(maxAttempts);
}

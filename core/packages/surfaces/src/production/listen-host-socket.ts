/** Page-side proxy for the shell-owned, authenticated Listen WebSocket. */

import type {
  PlatformListenSocket,
  PlatformListenSocketCloseEvent,
  PlatformListenSocketFactory,
  PlatformListenSocketMessageEvent,
} from "@omi-core/adapters-platform";

const CHANNEL = "omiListenSocket";

type HostMessageChannel = {
  postMessage(message: string): unknown;
};

type ListenHostEvent =
  | { readonly type: "open" }
  | { readonly type: "message"; readonly data: string }
  | { readonly type: "error" }
  | { readonly type: "close"; readonly code: number };

type ListenHostGlobals = {
  readonly omiListenSocket?: HostMessageChannel;
  readonly webkit?: {
    readonly messageHandlers?: {
      readonly omiListenSocket?: HostMessageChannel;
    };
  };
  __omiListenSocketEvent?: (id: string, event: ListenHostEvent | string) => void;
};

type ListenerMap = {
  open: Set<() => void>;
  message: Set<(event: PlatformListenSocketMessageEvent) => void>;
  error: Set<() => void>;
  close: Set<(event: PlatformListenSocketCloseEvent) => void>;
};

function channelFrom(host: ListenHostGlobals): HostMessageChannel {
  const channel = host.omiListenSocket ?? host.webkit?.messageHandlers?.omiListenSocket;
  if (channel === undefined) {
    throw new Error("Listen requires the shell-owned authenticated WebSocket bridge");
  }
  return channel;
}

function parseEvent(event: ListenHostEvent | string): ListenHostEvent | null {
  if (typeof event !== "string") return event;
  try {
    return JSON.parse(event) as ListenHostEvent;
  } catch {
    return null;
  }
}

class PlatformListenHostSocket implements PlatformListenSocket {
  readonly #id: string;
  readonly #post: (message: object) => void;
  readonly #listeners: ListenerMap = {
    open: new Set(),
    message: new Set(),
    error: new Set(),
    close: new Set(),
  };

  constructor(id: string, path: string, post: (message: object) => void) {
    this.#id = id;
    this.#post = post;
    this.#post({ id, action: "open", path });
  }

  addEventListener(type: "open", listener: () => void): void;
  addEventListener(type: "message", listener: (event: PlatformListenSocketMessageEvent) => void): void;
  addEventListener(type: "close", listener: (event: PlatformListenSocketCloseEvent) => void): void;
  addEventListener(type: "error", listener: () => void): void;
  addEventListener(
    type: keyof ListenerMap,
    listener: (() => void) | ((event: PlatformListenSocketMessageEvent | PlatformListenSocketCloseEvent) => void),
  ): void {
    (this.#listeners[type] as Set<typeof listener>).add(listener);
  }

  close(code = 1000, reason = ""): void {
    this.#post({ id: this.#id, action: "close", code, reason });
  }

  accept(event: ListenHostEvent): void {
    switch (event.type) {
      case "open":
        for (const listener of this.#listeners.open) listener();
        return;
      case "message":
        for (const listener of this.#listeners.message) listener({ data: event.data });
        return;
      case "error":
        for (const listener of this.#listeners.error) listener();
        return;
      case "close":
        for (const listener of this.#listeners.close) listener({ code: event.code });
    }
  }
}

/**
 * Compose the production page with the native socket channel present in both
 * shells. The page sends only an origin-relative path; the native host resolves
 * the API authority and attaches its bearer credential.
 */
export function createProductionListenHostSocketFactory(
  host: ListenHostGlobals = globalThis as ListenHostGlobals,
): PlatformListenSocketFactory {
  const channel = channelFrom(host);
  const sockets = new Map<string, PlatformListenHostSocket>();
  let nextId = 0;
  const post = (message: object): void => {
    channel.postMessage(JSON.stringify(message));
  };
  host.__omiListenSocketEvent = (id, rawEvent): void => {
    const event = parseEvent(rawEvent);
    if (event === null) return;
    sockets.get(id)?.accept(event);
    if (event.type === "close") sockets.delete(id);
  };

  return (path) => {
    if (!path.startsWith("/") || path.startsWith("//") || path.includes("://")) {
      throw new Error("Listen WebSocket path must be origin-relative");
    }
    const id = `listen-${++nextId}`;
    const socket = new PlatformListenHostSocket(id, path, post);
    sockets.set(id, socket);
    return socket;
  };
}

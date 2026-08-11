/** Page-side proxy for the shell-owned, authenticated Listen WebSocket. */

import type {
  PlatformListenPreflightProvider,
  PlatformListenPreflightSnapshot,
  PlatformListenPermissionState,
  PlatformListenInputDeviceState,
  PlatformListenSocket,
  PlatformListenSocketCloseEvent,
  PlatformListenSocketFactory,
  PlatformListenSocketMessageEvent,
} from "@omi-core/adapters-platform";
import {
  freezeListenPreflightSnapshot,
  UNAVAILABLE_LISTEN_PREFLIGHT,
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

type ListenPreflightEvent = {
  readonly type: "preflight";
  readonly requestId: string;
  readonly permission: PlatformListenPermissionState;
  readonly deviceState: PlatformListenInputDeviceState;
  readonly deviceLabel?: string | null;
  readonly recovery?: "request-permission" | "open-settings" | null;
};

type ListenHostGlobals = {
  readonly omiListenSocket?: HostMessageChannel;
  readonly webkit?: {
    readonly messageHandlers?: {
      readonly omiListenSocket?: HostMessageChannel;
    };
  };
  __omiListenSocketEvent?: (id: string, event: ListenHostEvent | string) => void;
  __omiListenPreflightEvent?: (requestId: string, event: ListenPreflightEvent | string) => void;
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

function parsePreflightEvent(event: ListenPreflightEvent | string): ListenPreflightEvent | null {
  try {
    const parsed: unknown = typeof event === "string" ? JSON.parse(event) : event;
    if (parsed === null || typeof parsed !== "object") return null;
    const prototype = Object.getPrototypeOf(parsed);
    if (prototype !== Object.prototype && prototype !== null) return null;
    const ownData = (key: string): { present: boolean; value: unknown } => {
      const descriptor = Object.getOwnPropertyDescriptor(parsed, key);
      if (descriptor === undefined) return { present: false, value: undefined };
      if (!("value" in descriptor)) return { present: true, value: undefined };
      return { present: true, value: descriptor.value };
    };
    const type = ownData("type");
    const permission = ownData("permission");
    const deviceState = ownData("deviceState");
    const requestId = ownData("requestId");
    const recovery = ownData("recovery");
    const deviceLabel = ownData("deviceLabel");
    if (type.value !== "preflight" || !requestId.present || typeof requestId.value !== "string") return null;
    if (typeof permission.value !== "string" || !["unknown", "checking", "granted", "denied", "restricted", "unavailable"].includes(permission.value)) return null;
    if (typeof deviceState.value !== "string" || !["unknown", "checking", "available", "unavailable"].includes(deviceState.value)) return null;
    if (recovery.present && recovery.value !== null && recovery.value !== "request-permission" && recovery.value !== "open-settings") return null;
    if (deviceLabel.present && deviceLabel.value !== null && typeof deviceLabel.value !== "string") return null;
    return {
      type: "preflight",
      requestId: requestId.value,
      permission: permission.value as PlatformListenPermissionState,
      deviceState: deviceState.value as PlatformListenInputDeviceState,
      ...(deviceLabel.present ? { deviceLabel: deviceLabel.value as string | null } : {}),
      ...(recovery.present ? { recovery: recovery.value as "request-permission" | "open-settings" | null } : {}),
    };
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

/**
 * Host-only microphone/device preflight. The native side returns state, not
 * hardware identifiers or credentials; a missing response is never treated as
 * granted. Recovery methods exist only when the host advertises them.
 */
export function createProductionListenHostPreflightProvider(
  host: ListenHostGlobals = globalThis as ListenHostGlobals,
): PlatformListenPreflightProvider {
  const channel = channelFrom(host);
  let snapshot: PlatformListenPreflightSnapshot = freezeListenPreflightSnapshot({
    permission: "unknown",
    device: { state: "unknown", label: null },
    recovery: null,
  });
  let nextId = 0;
  const listeners = new Set<() => void>();
  const pending = new Map<string, () => void>();
  const post = (operation: "check" | "request-permission" | "open-settings"): Promise<void> => {
    const requestId = `listen-preflight-${++nextId}`;
    if (operation !== "open-settings") {
      snapshot = freezeListenPreflightSnapshot({
        ...snapshot,
        permission: "checking",
        device: { state: "checking", label: null },
      });
      for (const listener of listeners) listener();
    }
    return new Promise((resolve) => {
      pending.set(requestId, resolve);
      channel.postMessage(JSON.stringify({ id: requestId, action: "preflight", operation }));
    });
  };
  host.__omiListenPreflightEvent = (requestId, rawEvent): void => {
    const event = parsePreflightEvent(rawEvent);
    const settle = pending.get(requestId);
    if (event === null) {
      if (settle !== undefined) {
        snapshot = UNAVAILABLE_LISTEN_PREFLIGHT;
        for (const listener of listeners) listener();
        pending.delete(requestId);
        settle();
      }
      return;
    }
    if (event.requestId !== requestId) return;
    const label = typeof event.deviceLabel === "string" && event.deviceLabel.trim() !== ""
      ? event.deviceLabel.trim().slice(0, 80)
      : null;
    snapshot = freezeListenPreflightSnapshot({
      permission: event.permission,
      device: { state: event.deviceState, label },
      recovery: event.recovery ?? null,
    });
    for (const listener of listeners) listener();
    settle?.();
    pending.delete(requestId);
  };
  return {
    snapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    refresh: () => post("check"),
    requestPermission: () => post("request-permission"),
    openSettings: () => post("open-settings"),
  };
}

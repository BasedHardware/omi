/** Page-side proxy for the shell-owned Screen capture bridge. */

import {
  createUnavailableScreenBridge,
  freezeScreenStatus,
  UNAVAILABLE_SCREEN_STATUS,
  type PlatformScreenBridge,
  type PlatformScreenBridgeAccess,
  type PlatformScreenCaptureEngineState,
  type PlatformScreenExclusions,
  type PlatformScreenFrameImage,
  type PlatformScreenIndexRebuild,
  type PlatformScreenPermissionState,
  type PlatformScreenRetentionSweep,
  type PlatformScreenStatus,
  type ScreenFrameRef,
  type ScreenRetentionDays,
} from "@omi-core/adapters-platform";

const CHANNEL = "omiScreenBridge";

type HostMessageChannel = {
  postMessage(message: string): unknown;
};

type ScreenHostGlobals = {
  readonly omiScreenBridge?: HostMessageChannel;
  readonly webkit?: {
    readonly messageHandlers?: {
      readonly omiScreenBridge?: HostMessageChannel;
    };
  };
  __omiScreenBridgeEvent?: (id: string, event: unknown) => void;
  __omiScreenStatusEvent?: (event: unknown) => void;
};

function channelFrom(host: ScreenHostGlobals): HostMessageChannel | null {
  return host.omiScreenBridge ?? host.webkit?.messageHandlers?.omiScreenBridge ?? null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function ownData(value: unknown, key: string): unknown {
  if (!isRecord(value)) return undefined;
  try {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return descriptor !== undefined && "value" in descriptor ? descriptor.value : undefined;
  } catch {
    return undefined;
  }
}

function parseResult(event: unknown): Record<string, unknown> | null {
  try {
    const parsed: unknown = typeof event === "string" ? JSON.parse(event) : event;
    if (!isRecord(parsed)) return null;
    const clone = globalThis.structuredClone;
    if (typeof clone !== "function") return null;
    clone(parsed);
    return parsed;
  } catch {
    return null;
  }
}

/**
 * Compose the production page with the native screen-bridge channel. Absent
 * on a browser surface — callers must render history without capture controls
 * or frame images rather than inventing a working toggle.
 */
export function createProductionScreenHostBridge(
  host: ScreenHostGlobals = globalThis as ScreenHostGlobals,
): PlatformScreenBridgeAccess {
  const channel = channelFrom(host);
  if (channel === null) return createUnavailableScreenBridge();

  let snapshot: PlatformScreenStatus = UNAVAILABLE_SCREEN_STATUS;
  let nextId = 0;
  const listeners = new Set<() => void>();
  const pending = new Map<string, (value: Record<string, unknown> | null) => void>();
  const notify = (): void => {
    for (const listener of listeners) listener();
  };
  const post = (action: string, params: object): Promise<Record<string, unknown> | null> => {
    const id = `screen-${++nextId}`;
    return new Promise((resolve) => {
      pending.set(id, resolve);
      channel.postMessage(JSON.stringify({ id, action, params }));
    });
  };

  host.__omiScreenBridgeEvent = (id, rawEvent): void => {
    const settle = pending.get(id);
    if (settle === undefined) return;
    pending.delete(id);
    settle(parseResult(rawEvent));
  };
  host.__omiScreenStatusEvent = (rawEvent): void => {
    const parsed = parseResult(rawEvent);
    const status = freezeScreenStatus(parsed);
    if (status === null) return;
    snapshot = status;
    notify();
  };

  const bridge: PlatformScreenBridge = {
    available: true,
    snapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    async refresh() {
      const result = await post("screen.status", {});
      const status = freezeScreenStatus(result);
      if (status !== null) {
        snapshot = status;
        notify();
      }
    },
    async start() {
      const result = await post("screen.start", {});
      const sessionId = ownData(result, "sessionId");
      const state = ownData(result, "state");
      return {
        sessionId: typeof sessionId === "string" ? sessionId : "",
        state: (typeof state === "string" ? state : "recording") as PlatformScreenCaptureEngineState,
      };
    },
    async stop() {
      const result = await post("screen.stop", {});
      const state = ownData(result, "state");
      return { state: (typeof state === "string" ? state : "idle") as PlatformScreenCaptureEngineState };
    },
    async frameImage(input: { frameRef: ScreenFrameRef; maxLongEdge?: number }) {
      // The shell contract is a string handle. Production timeline rows carry
      // the HTTP FrameRef object; unwrap it here rather than posting a shape
      // JSONDecoder will reject as an unreadable envelope.
      const frameRef = input.frameRef.kind === "opaque" ? input.frameRef.ref : input.frameRef.path;
      const result = await post("screen.frameImage", {
        frameRef,
        ...(input.maxLongEdge === undefined ? {} : { maxLongEdge: input.maxLongEdge }),
      });
      const pngBase64 = ownData(result, "pngBase64");
      const width = ownData(result, "width");
      const height = ownData(result, "height");
      if (typeof pngBase64 !== "string" || typeof width !== "number" || typeof height !== "number") {
        throw new Error("screen.frameImage returned an unreadable image");
      }
      return { pngBase64, width, height } satisfies PlatformScreenFrameImage;
    },
    async exclusionsList() {
      const result = await post("screen.exclusionsList", {});
      const bundleIds = ownData(result, "bundleIds");
      return { bundleIds: Array.isArray(bundleIds) ? bundleIds.filter((id): id is string => typeof id === "string") : [] };
    },
    async exclusionsSet(bundleIds) {
      const result = await post("screen.exclusionsSet", { bundleIds });
      const next = ownData(result, "bundleIds");
      const retired = ownData(result, "retiredFrameRefs");
      return {
        bundleIds: Array.isArray(next) ? next.filter((id): id is string => typeof id === "string") : [...bundleIds],
        ...(Array.isArray(retired) ? { retiredFrameRefs: retired.filter((id): id is string => typeof id === "string") } : {}),
      } satisfies PlatformScreenExclusions;
    },
    async retentionSet(days: ScreenRetentionDays) {
      const result = await post("screen.retentionSet", { days });
      const next = ownData(result, "days");
      const retired = ownData(result, "retiredFrameRefs");
      return {
        days: (typeof next === "number" ? next : days) as ScreenRetentionDays,
        retiredFrameRefs: Array.isArray(retired) ? retired.filter((id): id is string => typeof id === "string") : [],
      } satisfies PlatformScreenRetentionSweep;
    },
    async rebuildIndex() {
      const result = await post("screen.rebuildIndex", {});
      const frames = ownData(result, "frames");
      const chunks = ownData(result, "chunks");
      return {
        frames: typeof frames === "number" ? frames : 0,
        chunks: typeof chunks === "number" ? chunks : 0,
      } satisfies PlatformScreenIndexRebuild;
    },
    async requestPermission() {
      const result = await post("screen.requestPermission", {});
      const permission = ownData(result, "permission");
      return { permission: (typeof permission === "string" ? permission : "undetermined") as PlatformScreenPermissionState };
    },
    async openSettings() {
      const result = await post("screen.openSettings", {});
      return { opened: ownData(result, "opened") === true };
    },
  };
  return bridge;
}

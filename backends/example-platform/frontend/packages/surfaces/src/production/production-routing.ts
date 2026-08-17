/**
 * Which production surface the bootstrap renders.
 *
 * Extracted from `main.tsx` and kept pure so it can be executed by tests.
 * An unnamed launch now opens Activity (`conversations`). Explicit `route=`
 * and fixture selectors still win, including leftover `route=home` search
 * and `route=chat` for Chat-as-Home.
 *
 * Self-contained by design (no relative imports) so `node --test` runs it directly.
 */

export type ProductionRouteName =
  | "home"
  | "memories"
  | "conversations"
  | "folders"
  | "tasks"
  | "rewind"
  | "apps"
  | "brain-map"
  | "listen"
  | "chat"
  | "settings"
  | "unsupported";
export type MemoriesGeneration = "legacy" | "platform";
export type SettingsReturnRoute = Exclude<ProductionRouteName, "settings" | "unsupported">;

export type ProductionRouteInput = {
  /** `?route=` — the host naming a destination explicitly. */
  readonly requestedRoute: string | null;
  /** `?qa=` — a fixture selector, which also names a destination. */
  readonly requestedQa: string | null;
  /** The already-resolved selection for the memories domain. */
  readonly memoriesGeneration: MemoriesGeneration;
};

/**
 * Precedence, and every clause is load-bearing:
 *
 *  1. An EXPLICIT route or fixture selector always wins. Overriding it because a
 *     generation was selected would be the same bug mirrored — a host that asked for Home
 *     and silently got Memories.
 *  2. With no route named at all, the app opens on Activity — the hub that
 *     holds conversations, memories, folders, and brain map. Conversations is
 *     that hub's front door (Swift's switcher order starts there). An explicit
 *     `route=` or fixture selector still wins, including `route=home` for the
 *     leftover search surface and `route=chat` for Chat-as-Home.
 */
/** Activity hub front door. David named this the default landing page. */
export const DEFAULT_PRODUCTION_ROUTE = "conversations" as const satisfies ProductionRouteName;

export const ACTIVITY_HUB_ROUTES = ["conversations", "memories", "folders", "brain-map"] as const;

export function isActivityHubRoute(route: string): boolean {
  return (ACTIVITY_HUB_ROUTES as readonly string[]).includes(route);
}

/** Chat is the Home screen. `route=home` remains the leftover search surface. */
export function isHomeScreenRoute(route: string): boolean {
  return route === "chat" || route === "home";
}

export function resolveProductionRoute(input: ProductionRouteInput): ProductionRouteName {
  const { requestedRoute, requestedQa } = input;

  if (requestedRoute !== null) {
    if (requestedRoute === "screen") return "rewind";
    switch (requestedRoute) {
      case "home":
      case "memories":
      case "conversations":
      case "folders":
      case "tasks":
      case "rewind":
      case "apps":
      case "brain-map":
      case "listen":
      case "chat":
      case "settings":
        return requestedRoute;
      default:
        return "unsupported";
    }
  }

  if (requestedQa === "tasks") return "tasks";
  if (
    requestedQa === "conversations"
    || requestedQa === "conversation-detail"
  ) return "conversations";
  if (
    requestedQa === "memories"
    || requestedQa === "memories-platform"
  ) return "memories";

  return DEFAULT_PRODUCTION_ROUTE;
}

/** A Settings sheet may return only to a real, non-Settings destination. */
export function resolveSettingsReturnRoute(requestedRoute: string | null): SettingsReturnRoute {
  if (requestedRoute === "screen") return "rewind";
  switch (requestedRoute) {
    case "home":
    case "memories":
    case "conversations":
    case "folders":
    case "tasks":
    case "rewind":
    case "apps":
    case "brain-map":
    case "listen":
    case "chat":
      return requestedRoute;
    default:
      return "home";
  }
}

/**
 * Whether what actually rendered contradicts what the host asked for.
 *
 * This is the alarm that was missing. A rejected selection and a silently-legacy render
 * were indistinguishable from outside the app, which is how a zero served count coexists
 * with a screenshot that looks correct.
 */
export function generationMismatch(
  selected: MemoriesGeneration,
  rendered: MemoriesGeneration | null,
): boolean {
  // `null` means the rendered surface does not consume that domain. A
  // per-domain platform selection says nothing about a store this surface
  // did not open.
  return selected === "platform" && rendered === "legacy";
}

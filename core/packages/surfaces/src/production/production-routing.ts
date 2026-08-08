/**
 * Which production surface the bootstrap renders.
 *
 * Extracted from `main.tsx` and kept pure so it can be executed by tests, because this
 * decision is where the night's headline result was lost: the documented launcher passes
 * `generation=platform` and **no route**, the route defaulted to `home`, the platform
 * branch was gated on `route === "memories"`, and the app rendered legacy memories with a
 * served count of zero and nothing on screen or in the logs to say so.
 *
 * Self-contained by design (no relative imports) so `node --test` runs it directly.
 */

export type ProductionRouteName = "home" | "memories" | "conversations" | "tasks";
export type MemoriesGeneration = "legacy" | "platform";

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
 *  2. With no route named at all, a platform memories selection lands on the surface that
 *     actually reads it. Otherwise the selection is inert: the app looks perfect and the
 *     new backend serves nothing.
 *  3. Otherwise Home, the unchanged default.
 */
export function resolveProductionRoute(input: ProductionRouteInput): ProductionRouteName {
  const { requestedRoute, requestedQa, memoriesGeneration } = input;

  if (requestedRoute === "tasks" || requestedQa === "tasks") return "tasks";
  if (
    requestedRoute === "conversations"
    || requestedQa === "conversations"
    || requestedQa === "conversation-detail"
  ) return "conversations";
  if (
    requestedRoute === "memories"
    || requestedQa === "memories"
    || requestedQa === "memories-platform"
  ) return "memories";

  const hostNamedSomething = requestedRoute !== null || requestedQa !== null;
  if (!hostNamedSomething && memoriesGeneration === "platform") return "memories";
  return "home";
}

/**
 * Whether what actually rendered contradicts what the host asked for.
 *
 * This is the alarm that was missing. A rejected selection and a silently-legacy render
 * were indistinguishable from outside the app, which is how a zero served count coexists
 * with a screenshot that looks correct.
 */
export function generationMismatch(
  selectedMemories: MemoriesGeneration,
  renderedMemories: MemoriesGeneration,
): boolean {
  return selectedMemories === "platform" && renderedMemories === "legacy";
}

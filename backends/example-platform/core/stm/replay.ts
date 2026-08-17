import { compareStmOrder, StmStore, type StmItem } from "./index";

export interface ReplaySwitches { grounding: boolean; dream: boolean; }
export interface ReplaySession { session_id: string; item: StmItem; }
/** Capability handed to replay work: it can only read strictly-before state. */
export interface ReplayAsOfRepository { read(item_id: string): StmItem | undefined; }
export const assertNoLookahead = (current: StmItem, visible: readonly StmItem[]): void => {
  if (visible.some((item) => compareStmOrder(item, current) >= 0)) throw new Error("replay lookahead invariant violated");
};
/** Drives replay from a one-way source; handlers receive only an as-of capability. */
export const replayFromSource = <T>(source: Iterator<ReplaySession>, allItems: readonly StmItem[], handler: (session: ReplaySession, visible: readonly StmItem[], switches: ReplaySwitches, repository: ReplayAsOfRepository) => T, switches: ReplaySwitches = { grounding: false, dream: false }): readonly T[] => {
  const store = new StmStore(), result: T[] = [];
  const byId = new Map(allItems.map((item) => [item.id, item]));
  for (let next = source.next(); !next.done; next = source.next()) {
    const session = next.value, visible = store.all();
    assertNoLookahead(session.item, visible);
    const repository: ReplayAsOfRepository = { read: (item_id) => {
      const item = byId.get(item_id);
      if (item && compareStmOrder(item, session.item) >= 0) throw new Error("replay lookahead invariant violated");
      return item;
    } };
    const value = handler(session, visible, switches, repository);
    // Legacy callbacks may close over the submitted session array.  Reject a
    // leaked future id at the boundary as well; this guard is independent of
    // `assertNoLookahead`, so removing that assertion cannot make E6 green.
    if (typeof value === "string") {
      const referenced = byId.get(value);
      if (referenced && compareStmOrder(referenced, session.item) > 0) throw new Error("replay lookahead invariant violated");
    }
    result.push(value); store.put(session.item);
  }
  return result;
};

/** Replays a total order. The input is immediately converted to a one-way source. */
export const replaySessions = <T>(sessions: readonly ReplaySession[], handler: (session: ReplaySession, visible: readonly StmItem[], switches: ReplaySwitches, repository: ReplayAsOfRepository) => T, switches: ReplaySwitches = { grounding: false, dream: false }): readonly T[] => {
  const ordered = [...sessions].sort((a, b) => compareStmOrder(a.item, b.item));
  return replayFromSource(ordered.values(), ordered.map((session) => session.item), handler, switches);
};

/** Pure trigger over persisted STM counters and settled event-time boundaries. */
export interface ConsolidationWatermarks {
  stm_tokens: number;
  last_trigger_stm_tokens: number;
  high_watermark_tokens: number;
  low_watermark_tokens: number;
  previous_settled_window_id: string | null;
  previous_settled_event_time: string | null;
  settled_window_id: string;
  settled_event_time: string;
  idle_gap_ms: number;
}
export type ConsolidationTrigger = { fire: true; kind: "volume" | "idle"; reason: string } | { fire: false; kind: "none"; reason: string };

/** No wall clock and no queue arrival order: replaying persisted windows produces the same cycles. */
export const shouldConsolidate = (state: ConsolidationWatermarks): ConsolidationTrigger => {
  if (state.high_watermark_tokens <= state.low_watermark_tokens || state.low_watermark_tokens < 0) throw new Error("consolidation watermarks require high > low >= 0");
  if (!state.settled_window_id || !state.settled_event_time) throw new Error("consolidation requires a settled event-time boundary");
  if (state.stm_tokens >= state.high_watermark_tokens && state.last_trigger_stm_tokens <= state.low_watermark_tokens) return { fire: true, kind: "volume", reason: `serialized STM tokens ${state.stm_tokens} crossed high watermark ${state.high_watermark_tokens} after low-water reset` };
  if (state.previous_settled_window_id !== null && state.previous_settled_window_id !== state.settled_window_id && state.previous_settled_event_time !== null) {
    const gap = Date.parse(state.settled_event_time) - Date.parse(state.previous_settled_event_time);
    if (Number.isFinite(gap) && gap >= state.idle_gap_ms) return { fire: true, kind: "idle", reason: `settled event-time capture gap ${gap}ms reached idle threshold ${state.idle_gap_ms}ms` };
  }
  return { fire: false, kind: "none", reason: "no persisted volume or settled event-time idle trigger" };
};

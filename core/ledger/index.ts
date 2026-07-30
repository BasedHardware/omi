/** T9 boundary only: persistence and atomic commit are intentionally unimplemented in M-skeleton T0-T7. */
export interface LedgerPort { appendTransitionPlan(plan: unknown): Promise<{ commit_id: string }>; }
export interface LedgerSnapshot { owner_account_id: string; graph_generation: number; }

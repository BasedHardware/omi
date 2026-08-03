export type ConsolidationJobState = "pending" | "leased" | "succeeded" | "retryable_failed" | "dead_letter";
export interface ConsolidationJob { job_id: string; owner_account_id: string; state: ConsolidationJobState; attempt: number; max_attempts: number; lease_fence: number; lease_expires_event_time: number | null; worker_id: string | null; model_output: unknown | null; last_error: string | null; }
export interface ConsolidationStatePort {
  lease(owner: string, worker: string, event_time: number, limit: number): readonly ConsolidationJob[];
  recordModelOutput(jobId: string, fence: number, output: unknown, event_time: number): void;
  consume(jobId: string, fence: number, event_time: number): void;
  release(jobId: string, fence: number, error: string, event_time: number): void;
  outbox(owner: string): readonly { outbox_id: string; job_id: string; payload: string }[];
}

/** Fence comparison is deliberately centralized so stale workers cannot consume or release. */
export const ownsLease = (job: ConsolidationJob, fence: number, eventTime: number): boolean =>
  job.state === "leased" && job.lease_fence === fence && job.lease_expires_event_time !== null && job.lease_expires_event_time >= eventTime;

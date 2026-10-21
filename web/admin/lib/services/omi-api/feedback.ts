/**
 * Server-only client for the backend's feedback-report admin API.
 *
 * The daily thumbs-down report cannot be read straight out of Firestore the
 * way CSAT stats are, because the conversation text it points at is encrypted
 * per user with a key the admin app does not hold (`ENCRYPTION_SECRET` lives
 * only in the backend). So this dashboard reads pointers and asks the backend
 * to decrypt one event's window at a time.
 *
 * Both hops are authorized: the route handler checks the browser's Firebase
 * token against `adminData/{uid}` first, then this module adds `X-Admin-Key`,
 * which only exists in Cloud Run's runtime secrets. Neither key ever reaches
 * the browser.
 */

const OMI_API_BASE_URL = process.env.NEXT_PUBLIC_OMI_API_URL;

export class FeedbackApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "FeedbackApiError";
  }
}

async function feedbackApi<T>(
  endpoint: string,
  adminUid: string,
  init: RequestInit = {}
): Promise<T> {
  const adminKey = process.env.OMI_API_SECRET_KEY;
  if (!adminKey) {
    throw new FeedbackApiError("OMI_API_SECRET_KEY is not configured", 500);
  }
  if (!OMI_API_BASE_URL) {
    throw new FeedbackApiError(
      "NEXT_PUBLIC_OMI_API_URL is not configured",
      500
    );
  }

  const response = await fetch(`${OMI_API_BASE_URL}${endpoint}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Key": adminKey,
      // Who is asking. The key is shared across the deployment, so it alone
      // cannot tell the backend's audit log which admin read a user's chat.
      // This uid has already been checked against `adminData/{uid}` by the
      // route handler; it travels server-side only.
      "X-Admin-User": adminUid,
      ...init.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // Non-JSON error body; the status line is all we have.
    }
    throw new FeedbackApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export type FeedbackEvent = {
  id: string;
  uid: string;
  surface: string;
  target_kind: string;
  target_id: string;
  value: number;
  created_at: string;
  reason?: string | null;
  comment?: string | null;
  platform?: string | null;
  app_version?: string | null;
  app_id?: string | null;
  chat_session_id?: string | null;
  prompt_name?: string | null;
  prompt_commit?: string | null;
};

export type FeedbackContextTurn = {
  message_id: string;
  sender: string;
  created_at: string;
  position: "before" | "rated" | "after";
  seconds_from_rated: number;
};

export type FeedbackContextPointer = {
  event_id: string;
  uid: string;
  target_kind: string;
  target_id: string;
  turns: FeedbackContextTurn[];
  follow_up_count: number;
  follow_up_window_seconds: number;
  truncated_before: boolean;
  truncated_after: boolean;
  resolution_error?: string | null;
};

export type FeedbackReportEntry = {
  event: FeedbackEvent;
  context: FeedbackContextPointer;
};

export type FeedbackReport = {
  date: string;
  generated_at: string;
  total_negative: number;
  counts_by_surface: Record<string, number>;
  counts_by_reason: Record<string, number>;
  counts_by_platform: Record<string, number>;
  entries: FeedbackReportEntry[];
  truncated: boolean;
};

export type FeedbackContextHydratedTurn = FeedbackContextTurn & {
  text: string;
};

export type FeedbackContextHydrated = {
  event_id: string;
  target_kind: string;
  target_id: string;
  turns: FeedbackContextHydratedTurn[];
  unavailable: string[];
};

export function listReportDates(
  adminUid: string,
  limit = 30
): Promise<{ dates: string[] }> {
  return feedbackApi(`/v1/admin/feedback/reports?limit=${limit}`, adminUid);
}

export function getReport(
  adminUid: string,
  date: string
): Promise<FeedbackReport> {
  return feedbackApi(
    `/v1/admin/feedback/reports/${encodeURIComponent(date)}`,
    adminUid
  );
}

export function generateReport(
  adminUid: string,
  date: string
): Promise<{ date: string; total_negative: number; truncated: boolean }> {
  return feedbackApi(
    `/v1/admin/feedback/reports/${encodeURIComponent(date)}/generate`,
    adminUid,
    { method: "POST" }
  );
}

export function getEventContext(
  adminUid: string,
  eventId: string,
  reportDate?: string
): Promise<FeedbackContextHydrated> {
  const query = reportDate
    ? `?report_date=${encodeURIComponent(reportDate)}`
    : "";
  return feedbackApi(
    `/v1/admin/feedback/events/${encodeURIComponent(eventId)}/context${query}`,
    adminUid
  );
}

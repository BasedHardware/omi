/**
 * Meeting-note screenshot ("screen frame") wire types.
 *
 * HAND-WRITTEN — deliberately NOT in `@/lib/omiApi.generated.ts`. This feature
 * (screen-frame-egress) is being built concurrently across backend/desktop/web
 * against the shared contract (`data/reports/meeting-screenshots/DESIGN-sol.md`
 * §2 and the accompanying CONTRACT.md), and the OpenAPI spec has not been
 * regenerated to include these routes yet. These interfaces mirror the
 * Pydantic models `ConversationScreenFrame` / `ConversationScreenFrameSet`
 * field-for-field.
 *
 * TODO(screen-frames) #12155: once `docs/api-reference/app-client-openapi.json` is
 * regenerated with the `/v1/conversations/{id}/screenshots` routes, delete
 * this file and re-export the generated types from `@/types/conversation.ts`
 * instead — the house rule is to not hand-duplicate backend field sets, this
 * file is a stopgap until generation catches up.
 */

/** All fields normalized 0..1 relative to the frame's own width/height. */
export interface NormalizedRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type ScreenFrameSourceBadge =
  'code' | 'browser' | 'document' | 'slides' | 'product';

/**
 * Two-stop gradient ground extracted server-side from the canonical frame
 * bytes (see `backend/utils/screen_frames/palette.py`). Both macOS and web
 * render the banner from this — neither client samples pixels itself.
 */
export interface ScreenFrameGround {
  /** Exactly 2 stops, each "#RRGGBB". */
  stops: [string, string];
  is_neutral: boolean;
}

export interface ConversationScreenFrame {
  id: string;
  captured_at: string;
  role: 'banner' | 'strip';
  rank: number;
  caption: string;
  labels: string[];
  source_badge: ScreenFrameSourceBadge | null;
  focal_region: NormalizedRect | null;
  width: number;
  height: number;
  /** Signed, 60 min. */
  content_url: string;
  /** Signed, 60 min. */
  thumbnail_url: string;
  url_expires_at: string;
  /** Absent on older records — callers fall back to the neutral ground. */
  ground?: ScreenFrameGround;
}

export interface ConversationScreenFrameSet {
  revision: number;
  /** The best surviving frame for the header treatment, or null — render nothing. */
  banner: ConversationScreenFrame | null;
  /** Up to 6, sorted by capture order (rank 0..5). */
  strip: ConversationScreenFrame[];
}

/** Body for `PATCH /v1/conversations/{id}/screenshot-sharing`. */
export interface ScreenFrameSharingPatchRequest {
  enabled: boolean;
}

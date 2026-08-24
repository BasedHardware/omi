'use client';

import Image from '@tschk/moonshine-next/image';
import { Code2, FileText, Globe, Package, Presentation } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ConversationScreenFrame } from '@/types/conversation';

/**
 * Presentational-only label/icon union for the source badge. There is no
 * generated equivalent — the OpenAPI schema only types `source_badge` as an
 * inline string-literal union on `ConversationScreenFrame`, not a standalone
 * schema — so this is derived from that field rather than hand-duplicated.
 */
type ScreenFrameSourceBadge = NonNullable<ConversationScreenFrame['source_badge']>;

interface ConversationScreenFrameBannerProps {
  /** The approved banner frame, or null. Renders nothing when null — see contract §9. */
  frame: ConversationScreenFrame | null;
  title: string;
  /** Already-formatted date string (reuse the panel's own `formatDate`). */
  dateLabel?: string;
  /** Opens the banner in the lightbox. Omit to render a non-interactive banner. */
  onClick?: () => void;
  className?: string;
}

/**
 * The neutral ground `palette.py`'s `_neutral_ground()` produces (hue 0.62,
 * sat/val 0.12/0.40 and 0.16/0.24) — kept in sync with the backend by value,
 * not computed, since this is a display fallback, not a re-derivation. `ground`
 * itself is always present on a `ConversationScreenFrame`, but the generated
 * `ScreenFrameGround.stops` is typed as a general `string[]` (not a fixed
 * 2-tuple), so each stop is still defaulted independently below in case a
 * malformed record ever has fewer than 2.
 */
const NEUTRAL_GROUND_STOPS: [string, string] = ['#5A5D66', '#33363D'];

const SOURCE_BADGE_META: Record<
  ScreenFrameSourceBadge,
  { label: string; icon: typeof Code2 }
> = {
  code: { label: 'Code', icon: Code2 },
  browser: { label: 'Browser', icon: Globe },
  document: { label: 'Document', icon: FileText },
  slides: { label: 'Slides', icon: Presentation },
  product: { label: 'Product', icon: Package },
};

/**
 * The header banner for a conversation with an approved meeting-note
 * screenshot. Deliberately NOT a full-bleed screenshot: a designed header
 * with real text (title + date) and the approved frame as a small inset,
 * stacked below the title in a narrow layout.
 *
 * The ground behind the title is a two-stop linear gradient built from
 * `frame.ground.stops`, computed once server-side from the canonical frame
 * bytes (`backend/utils/screen_frames/palette.py`) and persisted — it is NOT
 * pixel-sampled by this component. Neither client samples pixels: signed GCS
 * URLs are cross-origin without guaranteed CORS headers, so
 * `canvas.getImageData` would be unreliable here, and independent
 * extractions on macOS (Swift) and web (JS) would drift from each other
 * anyway. Rendering the server's stops directly is what makes "the same DTO
 * produces the same composition on macOS and web" true. The stops are
 * already contrast-checked server-side for white text, so no scrim is added
 * on top — that would undo the tuning.
 */
export function ConversationScreenFrameBanner({
  frame,
  title,
  dateLabel,
  onClick,
  className,
}: ConversationScreenFrameBannerProps) {
  if (!frame) return null;

  const badge = frame.source_badge ? SOURCE_BADGE_META[frame.source_badge] : null;
  const BadgeIcon = badge?.icon;
  const stopA = frame.ground.stops[0] ?? NEUTRAL_GROUND_STOPS[0];
  const stopB = frame.ground.stops[1] ?? NEUTRAL_GROUND_STOPS[1];

  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      className={cn(
        'relative overflow-hidden rounded-card border border-stroke',
        onClick && 'cursor-pointer',
        className,
      )}
    >
      {/* Two-stop ground gradient from the server, top-left to bottom-right. */}
      <div
        className="absolute inset-0"
        aria-hidden="true"
        style={{
          backgroundImage: `linear-gradient(to bottom right, ${stopA}, ${stopB})`,
        }}
      />

      <div className="relative flex flex-col gap-4 p-5">
        <div className="min-w-0">
          <h2 className="line-clamp-2 font-display text-lg font-semibold text-white">
            {title}
          </h2>
          {dateLabel && <p className="mt-1 text-sm text-white/70">{dateLabel}</p>}
        </div>

        <div className="flex items-end justify-between gap-3">
          {/* The inset: ~25-35% of the banner width, small, framed. */}
          <div className="relative aspect-video w-[30%] min-w-[96px] max-w-[220px] flex-shrink-0 overflow-hidden rounded-element border border-stroke shadow-medium">
            <Image
              src={frame.thumbnail_url}
              alt={frame.caption}
              fill
              className="object-cover"
            />
          </div>

          {badge && BadgeIcon && (
            <span className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-badge border border-stroke bg-bg-tertiary/80 px-2.5 py-1 text-xs font-medium text-text-secondary backdrop-blur-sm">
              <BadgeIcon className="h-3.5 w-3.5" />
              {badge.label}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

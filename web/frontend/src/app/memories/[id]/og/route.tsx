import { ImageResponse } from 'next/og';
import envConfig from '@/src/constants/envConfig';
import { DEFAULT_TITLE_MEMORY } from '@/src/constants/memory';
import { sharedApiUrl } from '@/src/lib/shared-api-url.mjs';
import {
  durationMinutes,
  formatDuration,
  meetingTypeLabel,
  previewBullets,
} from '@/src/lib/shared-note.mjs';

const WIDTH = 1200;
const HEIGHT = 630;

interface SharedNote {
  started_at?: string;
  finished_at?: string;
  structured?: {
    title?: string;
    overview?: string;
    meeting_type?: string;
    sections?: unknown;
    action_items?: unknown[];
  };
}

async function fetchSharedNote(id: string): Promise<SharedNote | null> {
  try {
    const response = await fetch(
      sharedApiUrl(envConfig.API_URL, 'v1', 'conversations', id, 'shared'),
      { next: { revalidate: 300 }, signal: AbortSignal.timeout(5000) },
    );
    if (!response.ok) return null;
    return (await response.json()) as SharedNote;
  } catch {
    return null;
  }
}

/**
 * Google Fonts serves TTF to a client that sends no browser user agent,
 * which is what the image renderer needs. `text` subsets the file to the
 * glyphs actually drawn. Failure falls back to the renderer's built-in font.
 */
async function loadFont(family: string, weight: number, text: string) {
  try {
    const css = await (
      await fetch(
        `https://fonts.googleapis.com/css2?family=${family}:wght@${weight}&text=${encodeURIComponent(
          text,
        )}`,
        { signal: AbortSignal.timeout(3000) },
      )
    ).text();
    const src = css.match(/src: url\((.+?)\) format\('(?:opentype|truetype)'\)/);
    if (!src) return null;
    const font = await fetch(src[1], { signal: AbortSignal.timeout(3000) });
    return font.ok ? await font.arrayBuffer() : null;
  } catch {
    return null;
  }
}

export async function GET(_request: Request, props: { params: Promise<{ id: string }> }) {
  const { id } = await props.params;
  const note = await fetchSharedNote(id);

  const title = note ? note.structured?.title || DEFAULT_TITLE_MEMORY : 'Notes from Omi';
  const points = note ? previewBullets(note.structured) : [];
  const minutes = note ? durationMinutes(note.started_at, note.finished_at) : null;
  const kind = meetingTypeLabel(note?.structured?.meeting_type) || 'Conversation notes';
  const meta = [kind, minutes && minutes > 0 ? formatDuration(minutes) : '']
    .filter(Boolean)
    .join(' · ');
  const actionCount = Array.isArray(note?.structured?.action_items)
    ? note.structured.action_items.length
    : 0;
  const footer = actionCount
    ? `${actionCount} action item${actionCount === 1 ? '' : 's'} · Shared from Omi`
    : 'Shared from Omi';
  const titleSize = title.length > 60 ? 56 : title.length > 36 ? 64 : 76;

  const drawn = `omi${title}${meta}${footer}${points.join('')}—`;
  const [display, body] = await Promise.all([
    loadFont('Plus+Jakarta+Sans', 700, drawn),
    loadFont('DM+Sans', 400, drawn),
  ]);
  const fonts = [
    display && { name: 'Display', data: display, weight: 700 as const },
    body && { name: 'Body', data: body, weight: 400 as const },
  ].filter((font): font is NonNullable<typeof font> => Boolean(font));

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: '68px 80px',
          background: '#0f0f0f',
          color: '#ffffff',
          fontFamily: 'Body',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div
            style={{
              fontFamily: 'Display',
              fontSize: 44,
              fontWeight: 700,
              letterSpacing: '-0.04em',
            }}
          >
            omi
          </div>
          <div style={{ fontSize: 24, color: '#8f8f8f' }}>{meta}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div
            style={{
              fontFamily: 'Display',
              fontSize: titleSize,
              fontWeight: 700,
              lineHeight: 1.08,
              letterSpacing: '-0.03em',
              display: 'block',
              lineClamp: 2,
            }}
          >
            {title}
          </div>
          {points.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', marginTop: 28 }}>
              {points.map((point: string, index: number) => (
                <div
                  key={index}
                  style={{
                    display: 'flex',
                    fontSize: 28,
                    lineHeight: 1.35,
                    color: '#b0b0b0',
                    marginTop: index === 0 ? 0 : 10,
                  }}
                >
                  <span style={{ color: '#5a5a5e', marginRight: 16 }}>—</span>
                  <span>{point}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <div style={{ fontSize: 22, color: '#6b6b6b' }}>{footer}</div>
      </div>
    ),
    {
      width: WIDTH,
      height: HEIGHT,
      fonts: fonts.length ? fonts : undefined,
      headers: {
        // A note can be made private later; don't let caches keep it for a year.
        'Cache-Control': note
          ? 'public, max-age=3600, s-maxage=3600'
          : 'public, max-age=300, s-maxage=300',
      },
    },
  );
}

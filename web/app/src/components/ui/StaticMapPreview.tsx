'use client';

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import {
  fetchStaticMap,
  normalizeStaticMapPins,
  staticMapAxisPx,
  staticMapPath,
  staticMapPinsParam,
  type MapPin,
} from '@/lib/staticMap';

const CANVAS_COLOR = '#1A1A1A';
const RESIZE_DEBOUNCE_MS = 150;
const DOT_PADDING_PX = 20;
const DOT_RADIUS_PX = 4;

interface Size {
  width: number;
  height: number;
}

interface StaticMapPreviewProps {
  pins: readonly MapPin[];
  /** Accessible description; pass an empty string when a wrapping control already names the map. */
  alt: string;
  className?: string;
}

/**
 * The web counterpart of the mobile app's `OmiMapPreview`: a dark static map
 * rendered by the backend (`GET /v1/static-map`) over a deterministic pin-dot
 * canvas that doubles as the loading, signed-out, and error render. It never
 * shows a broken state and is non-interactive; wrap it in a link to hand off to
 * a real map.
 */
export function StaticMapPreview({ pins, alt, className }: StaticMapPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<Size | null>(null);
  const [image, setImage] = useState<{ url: string; pinsParam: string } | null>(null);
  const renderedPins = normalizeStaticMapPins(pins);
  const pinsParam = staticMapPinsParam(renderedPins);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let measured = false;
    const apply = (width: number, height: number) => {
      if (width <= 0 || height <= 0) return;
      measured = true;
      setSize((previous) =>
        previous && previous.width === width && previous.height === height
          ? previous
          : { width, height },
      );
    };
    const measure = (width: number, height: number) => {
      clearTimeout(timer);
      if (!measured) {
        apply(width, height);
        return;
      }
      timer = setTimeout(() => apply(width, height), RESIZE_DEBOUNCE_MS);
    };

    const rect = element.getBoundingClientRect();
    measure(rect.width, rect.height);
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box) measure(box.width, box.height);
    });
    observer.observe(element);
    return () => {
      clearTimeout(timer);
      observer.disconnect();
    };
  }, []);

  const requestWidth = size ? staticMapAxisPx(size.width) : 0;
  const requestHeight = size ? staticMapAxisPx(size.height) : 0;

  useEffect(() => {
    if (!pinsParam || requestWidth === 0) return;
    const controller = new AbortController();
    void fetchStaticMap(
      staticMapPath(pinsParam, requestWidth, requestHeight),
      controller.signal,
    ).then((blob) => {
      if (!blob || controller.signal.aborted) return;
      setImage({ url: URL.createObjectURL(blob), pinsParam });
    });
    return () => controller.abort();
  }, [pinsParam, requestWidth, requestHeight]);

  useEffect(() => {
    if (!image) return;
    return () => URL.revokeObjectURL(image.url);
  }, [image]);

  return (
    <div
      ref={containerRef}
      role={alt ? 'img' : undefined}
      aria-label={alt || undefined}
      className={cn('relative h-full w-full overflow-hidden', className)}
      style={{ backgroundColor: CANVAS_COLOR }}
    >
      {size && <PinDots pins={renderedPins} width={size.width} height={size.height} />}
      {image && image.pinsParam === pinsParam && (
        <img
          data-testid="static-map-image"
          src={image.url}
          alt=""
          draggable={false}
          className="absolute inset-0 h-full w-full object-cover"
        />
      )}
    </div>
  );
}

function PinDots({
  pins,
  width,
  height,
}: {
  pins: readonly MapPin[];
  width: number;
  height: number;
}) {
  const [first] = pins;
  if (!first) return null;

  let minLat = first.latitude;
  let maxLat = first.latitude;
  let minLng = first.longitude;
  let maxLng = first.longitude;
  for (const pin of pins) {
    minLat = Math.min(minLat, pin.latitude);
    maxLat = Math.max(maxLat, pin.latitude);
    minLng = Math.min(minLng, pin.longitude);
    maxLng = Math.max(maxLng, pin.longitude);
  }

  const usableWidth = Math.max(width - 2 * DOT_PADDING_PX, 1);
  const usableHeight = Math.max(height - 2 * DOT_PADDING_PX, 1);
  const centerLat = (minLat + maxLat) / 2;
  const centerLng = (minLng + maxLng) / 2;
  // Equirectangular placement is enough for dot positions at city scale; the
  // static image carries the real projection.
  const latCos = Math.max(Math.abs(Math.cos((centerLat * Math.PI) / 180)), 0.01);
  const latSpan = maxLat - minLat;
  const lngSpan = (maxLng - minLng) * latCos;

  let scale = 0;
  if (latSpan > 0 && lngSpan > 0) {
    scale = Math.min(usableWidth / lngSpan, usableHeight / latSpan);
  } else if (latSpan > 0) {
    scale = usableHeight / latSpan;
  } else if (lngSpan > 0) {
    scale = usableWidth / lngSpan;
  }

  return (
    <svg
      data-testid="static-map-fallback"
      aria-hidden="true"
      className="absolute inset-0"
      width={width}
      height={height}
    >
      {pins.map((pin, index) => (
        <circle
          key={index}
          cx={width / 2 + (pin.longitude - centerLng) * latCos * scale}
          cy={height / 2 - (pin.latitude - centerLat) * scale}
          r={DOT_RADIUS_PX}
          fill="white"
          stroke="black"
          strokeWidth={1.5}
        />
      ))}
    </svg>
  );
}

"use client";

import { Children, cloneElement, isValidElement, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

/**
 * Drop-in replacement for recharts' <ResponsiveContainer>.
 *
 * recharts' own ResponsiveContainer renders nothing in our Next.js production
 * build (its internal sizing path yields a 0×0 size once the bundle is built —
 * charts render under `next dev` but are blank after `next build`). This
 * component measures its own box with a plain ResizeObserver and passes the
 * resolved pixel width/height straight to the single recharts chart child, so
 * there is no dependency on recharts' internal sizing path.
 *
 * Mirrors the subset of the ResponsiveContainer API the dashboard uses
 * (width/height "100%", optional minHeight/minWidth) so existing call sites
 * need no changes.
 */
export function ResponsiveContainer({
  width = "100%",
  height = "100%",
  minHeight,
  minWidth,
  children,
}: {
  width?: number | string;
  height?: number | string;
  minHeight?: number | string;
  minWidth?: number | string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const r = el.getBoundingClientRect();
      const w = Math.floor(r.width);
      const h = Math.floor(r.height);
      setSize((prev) => (prev.w === w && prev.h === h ? prev : { w, h }));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    // Flexbox heights can resolve a frame after mount; re-measure once.
    const raf = requestAnimationFrame(measure);
    return () => {
      ro.disconnect();
      cancelAnimationFrame(raf);
    };
  }, []);

  const child = children != null ? Children.only(children) : null;

  return (
    <div ref={ref} style={{ width, height, minHeight, minWidth, position: "relative" }}>
      {size.w > 0 && size.h > 0 && isValidElement(child)
        ? cloneElement(child as React.ReactElement<{ width?: number; height?: number }>, {
            width: size.w,
            height: size.h,
          })
        : null}
    </div>
  );
}

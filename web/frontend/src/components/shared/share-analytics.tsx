'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import {
  attributedCtaHref,
  ctaTarget,
  deviceClass,
  shareId,
  shareSource,
  shareSurface,
} from '@/src/lib/share-analytics.mjs';

const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const host = process.env.NEXT_PUBLIC_POSTHOG_HOST || 'https://us.i.posthog.com';

/** One ephemeral browser identity per page load; no cookies, storage, autocapture or person profile. */
export function ShareAnalytics() {
  const pathname = usePathname();
  useEffect(() => {
    const surface = shareSurface(pathname);
    if (!surface || !key) return;

    const params = new URLSearchParams(window.location.search);
    const device = deviceClass(navigator.userAgent);
    const common = {
      surface,
      share_id: shareId(params.get('sid')),
      s: shareSource(params.get('s')),
      device_class: device,
      is_preview_bot: device === 'bot',
    };
    const distinctId = crypto.randomUUID();
    const capture = (event: string, properties: Record<string, unknown> = {}) => {
      const body = JSON.stringify({
        api_key: key,
        event,
        distinct_id: distinctId,
        properties: {
          ...common,
          ...properties,
          $process_person_profile: false,
          $geoip_disable: true,
        },
      });
      void fetch(`${host}/capture/`, {
        method: 'POST',
        body,
        headers: { 'Content-Type': 'application/json' },
        keepalive: true,
        referrerPolicy: 'no-referrer',
      }).catch(() => undefined);
    };
    const theme = () =>
      document.documentElement.getAttribute('data-share-theme') ||
      (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    capture('Share Page Viewed', { theme: theme() });

    const onClick = (event: MouseEvent) => {
      const element = event.target instanceof Element ? event.target : null;
      const tab = element?.closest('[role="tab"]');
      if (tab) {
        const label = tab.textContent?.trim();
        const tabName =
          label === 'Notes'
            ? 'notes'
            : label === 'Transcript'
            ? 'transcript'
            : label === 'Ask Omi'
            ? 'ask_omi'
            : null;
        if (tabName) capture('Share Page Tab Switched', { tab: tabName });
      }
      const anchor = element?.closest('a[href]');
      if (anchor) {
        const href = anchor.getAttribute('href');
        const target = ctaTarget(href);
        if (target) {
          capture('Share CTA Clicked', { target });
          // Update before the anchor's default navigation, including target=_blank.
          anchor.setAttribute(
            'href',
            attributedCtaHref(href, surface, common.s, common.share_id),
          );
        }
      }
    };
    const onCopy = () => capture('Share Link Re-copied');
    const seen = new Set<number>();
    const onScroll = () => {
      const height = document.documentElement.scrollHeight - window.innerHeight;
      if (height <= 0) return;
      const percent = (window.scrollY / height) * 100;
      for (const milestone of [25, 50, 75, 100]) {
        if (percent >= milestone && !seen.has(milestone)) {
          seen.add(milestone);
          capture('Share Page Scrolled', { depth_percent: milestone });
        }
      }
    };
    document.addEventListener('click', onClick);
    document.addEventListener('omi:share-link-copied', onCopy);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      document.removeEventListener('click', onClick);
      document.removeEventListener('omi:share-link-copied', onCopy);
      window.removeEventListener('scroll', onScroll);
    };
  }, [pathname]);
  return null;
}

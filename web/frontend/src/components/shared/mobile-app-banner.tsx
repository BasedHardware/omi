'use client';

import Image from 'next/image';
import { useEffect, useMemo, useState } from 'react';

type Platform = 'ios' | 'android' | null;

const PLAY_STORE_URL = 'https://play.google.com/store/apps/details?id=com.friend.ios';
const APP_STORE_URL =
  'https://apps.apple.com/us/app/omi-ai-smart-meeting-notes/id6502156163';
const DEEP_LINK = 'omi://';
const DISMISS_KEY = 'omi_app_banner_dismissed_at';
const DISMISS_TTL_DAYS = 7; // show again after a week

function getPlatform(ua: string): Platform {
  if (/android/i.test(ua)) return 'android';
  if (/iphone|ipad|ipod/i.test(ua)) return 'ios';
  return null;
}

function shouldShowFromStorage(): boolean {
  try {
    const ts = localStorage.getItem(DISMISS_KEY);
    if (!ts) return true;
    const ageDays = (Date.now() - Number(ts)) / (1000 * 60 * 60 * 24);
    return ageDays > DISMISS_TTL_DAYS;
  } catch {
    return true;
  }
}

export default function MobileAppBanner() {
  const [platform, setPlatform] = useState<Platform>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const ua = navigator.userAgent || '';
    const p = getPlatform(ua);
    setPlatform(p);

    const inStandalone = (window.navigator as any).standalone === true; // iOS PWA
    const isAndroidPWA =
      (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
      false;

    if (p && !inStandalone && !isAndroidPWA && shouldShowFromStorage()) {
      setVisible(true);
    }
  }, []);

  const storeUrl = useMemo(
    () =>
      platform === 'ios' ? APP_STORE_URL : platform === 'android' ? PLAY_STORE_URL : '#',
    [platform],
  );

  const openApp = () => {
    if (!platform) return;
    const start = Date.now();
    // Attempt deep link
    window.location.href = DEEP_LINK;
    // Fallback to store if app not installed / deep link fails
    setTimeout(() => {
      const elapsed = Date.now() - start;
      if (elapsed < 1800) {
        window.location.href = storeUrl;
      }
    }, 1500);
  };

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
    } catch {
      console.error('Failed to store dismiss timestamp');
    }
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed inset-x-0 top-0 z-[60] w-full border-b border-white/10 bg-[#0B0F17]">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 text-white">
        <Image
          src="/omi-white.webp"
          alt="Omi"
          width={146}
          height={64}
          className="h-auto w-[50px]"
        />
        <div className="flex-1">
          <div className="text-sm font-semibold">Omi</div>
          <div className="text-xs text-gray-300">Open in the Omi app</div>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={storeUrl}
            className="hidden rounded-lg border border-white/20 px-3 py-1.5 text-sm font-medium text-white hover:bg-white/10 sm:block"
            aria-label={platform === 'ios' ? 'Open App Store' : 'Open Play Store'}
            target="_blank"
            rel="noopener noreferrer"
          >
            {platform === 'ios' ? 'App Store' : 'Play Store'}
          </a>
          <button
            onClick={openApp}
            className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white shadow hover:bg-blue-500"
            aria-label="Open app"
          >
            Open
          </button>
        </div>
        <button
          onClick={dismiss}
          className="ml-2 rounded p-1 text-gray-400 hover:text-white"
          aria-label="Dismiss banner"
        >
          <svg
            className="h-5 w-5"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M6 6L18 18M6 18L18 6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>
    </div>
  );
}

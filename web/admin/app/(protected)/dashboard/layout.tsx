"use client";

import React, { useEffect, useRef } from "react";
import { useAuth } from "@/components/auth-provider";
import { useRouter, usePathname } from "next/navigation";
import { DashboardSidebar } from "@/components/dashboard/sidebar";
import { DashboardHeader } from "@/components/dashboard/header";
import { useAdminAccess } from "@/hooks/useAdminAccess";
import { SCOPE_LABELS, pageScope, pageWriteScope } from "@/lib/admin-access";

/** Shown instead of a page whose scope the viewer's role does not include. */
function NoAccess({ scope }: { scope: keyof typeof SCOPE_LABELS }) {
  return (
    <div className="mx-auto mt-16 max-w-md rounded-lg border p-6 text-center">
      <h2 className="text-lg font-semibold">
        Your role does not include this page
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        It needs <code>{scope}</code> ({SCOPE_LABELS[scope]}). Ask an owner or a
        deputy to change your role on the Team page.
      </p>
    </div>
  );
}

/** The page is readable, but its edit actions need a scope the role lacks. */
function ReadOnlyNotice({ scope }: { scope: keyof typeof SCOPE_LABELS }) {
  return (
    <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200">
      Read-only for your role: changes here need <code>{scope}</code> (
      {SCOPE_LABELS[scope]}) and will be refused.
    </div>
  );
}

// Simple loading component (Consider moving to a shared UI folder)
const LoadingScreen = () => (
  <div className="flex min-h-screen items-center justify-center">
    <div>Loading...</div>
  </div>
);

const SCROLL_STORAGE_PREFIX = "omi-admin-scroll:";

function useScrollRestoration(
  mainRef: React.RefObject<HTMLElement>,
  enabled: boolean
) {
  const pathname = usePathname();
  const storageKey = `${SCROLL_STORAGE_PREFIX}${pathname ?? "/"}`;

  // Restore scroll position on mount / route change. We poll briefly
  // because the page content mounts and grows as SWR data arrives, so
  // the target scrollTop may not be reachable on the first frame.
  useEffect(() => {
    if (!enabled) return;
    const el = mainRef.current;
    if (!el) return;

    let saved: number | null = null;
    try {
      const raw = window.sessionStorage.getItem(storageKey);
      if (raw != null) saved = parseInt(raw, 10);
    } catch {
      /* noop */
    }
    if (saved == null || Number.isNaN(saved)) return;

    let tries = 0;
    const maxTries = 40; // ~2s at 50ms cadence
    const tick = () => {
      const node = mainRef.current;
      if (!node) return;
      node.scrollTop = saved!;
      if (Math.abs(node.scrollTop - saved!) > 2 && tries++ < maxTries) {
        setTimeout(tick, 50);
      }
    };
    tick();
  }, [enabled, mainRef, storageKey]);

  // Save scroll position as the user scrolls. Throttled via rAF.
  useEffect(() => {
    if (!enabled) return;
    const el = mainRef.current;
    if (!el) return;

    let pending = false;
    const onScroll = () => {
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => {
        pending = false;
        try {
          window.sessionStorage.setItem(storageKey, String(el.scrollTop));
        } catch {
          /* noop */
        }
      });
    };

    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [enabled, mainRef, storageKey]);
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isAdmin, loading } = useAuth();
  const router = useRouter();
  const mainRef = useRef<HTMLElement>(null);
  const pathname = usePathname();
  const { access } = useAdminAccess();
  const authenticated = !!(user && isAdmin && !loading);
  const requiredScope = pageScope(pathname ?? "");
  const blockedScope =
    access && requiredScope && !access.scopes.includes(requiredScope)
      ? requiredScope
      : null;
  const writeScope = pageWriteScope(pathname ?? "");
  const readOnlyScope =
    access && writeScope && !access.scopes.includes(writeScope)
      ? writeScope
      : null;
  useScrollRestoration(mainRef, authenticated);

  useEffect(() => {
    if (loading) {
      return; // Wait until loading is complete
    }
    if (!user || !isAdmin) {
      // Redirect non-admins or non-logged-in users to login
      router.push("/login?error=unauthorized");
    }
  }, [user, isAdmin, loading, router]);

  // Show loading screen while checking auth
  if (loading) {
    return <LoadingScreen />;
  }

  // If user is authenticated and is an admin, render the dashboard layout
  if (user && isAdmin) {
    return (
      <div className="flex min-h-screen bg-background">
        <DashboardSidebar />
        <div className="flex min-h-screen flex-1 flex-col">
          <DashboardHeader />
          <main ref={mainRef} className="flex-1 overflow-y-auto p-4 md:p-6">
            {blockedScope ? (
              <NoAccess scope={blockedScope} />
            ) : (
              <>
                {readOnlyScope ? (
                  <ReadOnlyNotice scope={readOnlyScope} />
                ) : null}
                {children}
              </>
            )}
          </main>
        </div>
      </div>
    );
  }

  // Fallback while redirecting
  return <LoadingScreen />;
}

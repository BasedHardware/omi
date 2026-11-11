'use client';

import { createElement, type ComponentType, type ReactNode } from 'react';
import { createMoonshineRouter, MoonshineRouter } from '@tschk/moonshine/router';
import AuthenticatedLayout from '@/app/(authenticated)/layout';
import PublicLayout from '@/app/(public)/layout';
import RootLayout from '@/app/layout';

type RouteKind = 'root' | 'authenticated' | 'public';

type ClientRoute = {
  path: string;
  component: ComponentType;
  kind: RouteKind;
};

const clientRoutes = new Map<string, ClientRoute>();
let mountScheduled = false;

function RouteView({ route }: { route: ClientRoute }): ReactNode {
  let content = createElement(route.component);
  if (route.kind === 'authenticated') {
    content = createElement(AuthenticatedLayout, null, content);
  } else if (route.kind === 'public') {
    content = createElement(PublicLayout, null, content);
  }
  return content;
}

async function mountClientRoutes(): Promise<void> {
  if (typeof document === 'undefined') return;
  const host = document.getElementById('moonshine-app');
  if (!host) return;
  const { createRoot } = await import('react-dom/client');
  // The query is part of the initial location, not decoration: a deep link to
  // `/conversations?recap=…`, `/settings?section=…` or an OAuth callback opens
  // on the default view if the router starts from the pathname alone.
  const runtime = createMoonshineRouter(
    window.location.pathname + window.location.search,
  );
  const routes = [...clientRoutes.values()].map((route) => ({
    id: route.path,
    path: route.path,
    element: createElement(RouteView, { route }),
  }));
  createRoot(host).render(
    createElement(RootLayout, null, createElement(MoonshineRouter, { routes, runtime })),
  );
}

export function registerMoonshineRoute(
  path: string,
  component: ComponentType,
  kind: RouteKind,
): void {
  clientRoutes.set(path, { path, component, kind });
  if (typeof document === 'undefined' || mountScheduled) return;
  mountScheduled = true;
  queueMicrotask(() => void mountClientRoutes());
}

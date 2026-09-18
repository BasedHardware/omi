import { describe, expect, it, vi } from 'vitest';
import type { MoonshineRouterInstance } from '@tschk/moonshine/router';

vi.mock('@/app/(authenticated)/layout', () => ({ default: () => null }));
vi.mock('@/app/(public)/layout', () => ({ default: () => null }));
vi.mock('@/app/layout', () => ({ default: () => null }));

const rendered: { element: unknown } = { element: null };
vi.mock('react-dom/client', () => ({
  createRoot: () => ({
    render: (element: unknown) => {
      rendered.element = element;
    },
  }),
}));

const { registerMoonshineRoute } = await import('@/moonshine/register-client-route');

function mountedRuntime(): MoonshineRouterInstance {
  const root = rendered.element as {
    props: { children: { props: { runtime: MoonshineRouterInstance } } };
  };
  return root.props.children.props.runtime;
}

describe('client route mounting', () => {
  it('starts the router at the deep link, query state included', async () => {
    const host = document.createElement('div');
    host.id = 'moonshine-app';
    document.body.appendChild(host);
    window.history.replaceState({}, '', '/conversations?recap=recap-7');

    registerMoonshineRoute('/conversations', () => null, 'authenticated');
    // The mount is scheduled on a microtask, and loads react-dom/client.
    await vi.waitFor(() => expect(rendered.element).not.toBeNull());

    // Dropping the query here is what makes a notification or shared link open
    // the default view instead of the thing it pointed at.
    expect(mountedRuntime().getLocation()).toBe('/conversations?recap=recap-7');
  });
});

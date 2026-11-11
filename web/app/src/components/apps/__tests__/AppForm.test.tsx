import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppForm } from '@/components/apps/AppForm';
import type { App } from '@/types/apps';

const api = vi.hoisted(() => ({
  getAppCategories: vi.fn(async () => [{ id: 'productivity', title: 'Productivity' }]),
  getAppCapabilities: vi.fn(async () => [{ id: 'chat', title: 'Chat' }]),
  getNotificationScopes: vi.fn(async () => []),
  getPaymentPlans: vi.fn(async () => []),
  createApp: vi.fn(async () => ({ app_id: 'app-2' })),
  updateApp: vi.fn(async () => {}),
  uploadAppThumbnail: vi.fn(async () => ({
    thumbnail_url: 'https://cdn.test/new.jpg',
    thumbnail_id: 'thumb-new',
  })),
  generateAppDescription: vi.fn(async () => ''),
  deleteApp: vi.fn(async () => {}),
}));

vi.mock('@/lib/api', () => api);
vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) => <img {...props} alt="" />,
}));

const app = {
  id: 'app-1',
  name: 'My App',
  description: 'Does a thing',
  category: 'productivity',
  capabilities: ['chat'],
  chat_prompt: 'be helpful',
  private: false,
  thumbnails: ['thumb-old'],
  thumbnail_urls: ['https://cdn.test/old.jpg'],
} as unknown as App;

async function uploadScreenshot(container: HTMLElement) {
  await screen.findByText('Screenshots');
  const inputs = container.querySelectorAll('input[type="file"]');
  const screenshotInput = inputs[inputs.length - 1] as HTMLInputElement;
  fireEvent.change(screenshotInput, {
    target: { files: [new File(['x'], 'shot.png', { type: 'image/png' })] },
  });
  await waitFor(() => expect(api.uploadAppThumbnail).toHaveBeenCalled());
}

describe('AppForm screenshots', () => {
  beforeEach(() => {
    api.updateApp.mockClear();
    api.uploadAppThumbnail.mockClear();
  });

  it('saves an uploaded screenshot with the app', async () => {
    const { container } = render(<AppForm mode="edit" app={app} />);

    await uploadScreenshot(container);
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() =>
      expect(api.updateApp).toHaveBeenCalledWith(
        'app-1',
        expect.objectContaining({ thumbnails: ['thumb-old', 'thumb-new'] }),
        undefined,
      ),
    );
  });
});

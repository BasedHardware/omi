import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  process.env.NEXT_PUBLIC_OMI_API_URL = 'https://backend.test';
  process.env.OMI_API_SECRET_KEY = 'secret';
  process.env.ENCRYPTION_SECRET = 'enc-secret';
  return {
    docIds: [] as string[],
    fetchUrls: [] as string[],
    revokeTvLink: vi.fn(),
    invalidateEnforcementCache: vi.fn(),
    getUser: vi.fn(),
  };
});

function makeFirestoreNode() {
  const node: Record<string, unknown> = {};
  node.doc = vi.fn((id: string) => {
    mocks.docIds.push(id);
    return node;
  });
  node.collection = vi.fn(() => node);
  node.orderBy = vi.fn(() => node);
  node.limit = vi.fn(() => node);
  node.where = vi.fn(() => node);
  node.get = vi.fn().mockResolvedValue({ exists: false, docs: [], data: () => ({}) });
  node.set = vi.fn().mockResolvedValue(undefined);
  node.update = vi.fn().mockResolvedValue(undefined);
  node.delete = vi.fn().mockResolvedValue(undefined);
  return node;
}

vi.mock('@/lib/auth', () => ({
  verifyAdmin: vi.fn().mockResolvedValue({ uid: 'admin-uid' }),
}));
vi.mock('@/lib/firebase/admin', () => ({
  default: { firestore: { Timestamp: { now: () => ({}) } } },
  getDb: () => ({ collection: vi.fn(() => makeFirestoreNode()) }),
  getAdminAuth: () => ({ getUser: mocks.getUser }),
}));
vi.mock('@/lib/stripe', () => ({ getStripe: vi.fn() }));
vi.mock('@/lib/utils/user-subscription', () => ({
  updateUserSubscriptionDetails: vi.fn(),
}));
vi.mock('@/lib/redis', () => ({
  invalidateEnforcementCache: mocks.invalidateEnforcementCache,
}));
vi.mock('@/lib/tv-links', () => ({ revokeTvLink: mocks.revokeTvLink }));

import { GET as fairUseGET } from '../omi/fair-use/user/[uid]/route';
import { POST as resolveEventPOST } from '../omi/fair-use/user/[uid]/resolve-event/[eventId]/route';
import {
  DELETE as promptDELETE,
  PATCH as promptPATCH,
} from '../omi/desktop-prompts/[id]/route';
import { GET as announceGET } from '../omi/announcements/[id]/route';
import { POST as appUpdatePOST } from '../omi/apps/[app_id]/update/route';
import { DELETE as tvLinkDELETE } from '../omi/tv-links/[id]/route';
import { PUT as distributorPUT } from '../distributors/route';
import { PATCH as orgPATCH } from '../organizations/[id]/route';
import { GET as userNotifGET } from '../omi/notifications/user-notifications/route';

const fakeRequest = { json: vi.fn(), url: 'https://admin.test/x' } as never;

function paramsOf<T extends Record<string, string>>(value: T) {
  return { params: Promise.resolve(value) } as never;
}

describe('admin API routes reject decoded ids that split Firestore paths', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.docIds.length = 0;
    mocks.fetchUrls.length = 0;
    mocks.revokeTvLink.mockResolvedValue(null);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        mocks.fetchUrls.push(String(input));
        return new Response('{}', { status: 200 });
      }),
    );
  });

  it('fair-use user GET rejects a uid containing a slash', async () => {
    const res = await fairUseGET(fakeRequest, paramsOf({ uid: 'a/b' }));
    expect(res.status).toBe(400);
    expect(mocks.docIds).toEqual([]);
  });

  it('fair-use user GET accepts uids with non-slash special characters', async () => {
    // Firebase custom-auth uids may contain ':' or '@'; the stored doc id must
    // match the raw uid, so these must reach doc() unmodified.
    const res = await fairUseGET(fakeRequest, paramsOf({ uid: 'google:abc@x' }));
    expect(res.status).toBe(200);
    expect(mocks.docIds).toContain('google:abc@x');
  });

  it('fair-use resolve-event rejects a slash in either param', async () => {
    const req = { json: vi.fn(), url: 'https://admin.test/x?notes=n' } as never;
    const res = await resolveEventPOST(req, paramsOf({ uid: 'u/1', eventId: 'e/2' }));
    expect(res.status).toBe(400);
    expect(mocks.docIds).toEqual([]);
  });

  it('desktop-prompts DELETE rejects a slash-bearing prompt id', async () => {
    const res = await promptDELETE(fakeRequest, paramsOf({ id: 'p/1' }));
    expect(res.status).toBe(400);
    expect(mocks.docIds).toEqual([]);
  });

  it('desktop-prompts PATCH rejects a slash-bearing prompt id', async () => {
    const req = {
      json: vi.fn().mockResolvedValue({ active: true }),
      url: 'https://admin.test/x',
    } as never;
    const res = await promptPATCH(req, paramsOf({ id: 'p/1' }));
    expect(res.status).toBe(400);
    expect(mocks.docIds).toEqual([]);
  });

  it('announcements GET encodes id in the upstream URL', async () => {
    await announceGET(fakeRequest, paramsOf({ id: 'ann/1' }));
    expect(mocks.fetchUrls[0]).toContain('/v1/announcements/ann%2F1');
    expect(mocks.fetchUrls[0]).not.toContain('/v1/announcements/ann/1');
  });

  it('tv-links DELETE rejects a slash-bearing link id', async () => {
    const res = await tvLinkDELETE(fakeRequest, paramsOf({ id: 'l/1' }));
    expect(res.status).toBe(400);
    expect(mocks.revokeTvLink).not.toHaveBeenCalled();
  });

  it('distributors PUT rejects a body id containing a slash', async () => {
    const req = { json: vi.fn().mockResolvedValue({ id: 'dist/1', name: 'x' }) } as never;
    const res = await distributorPUT(req);
    expect(res.status).toBe(400);
    expect(mocks.docIds).toEqual([]);
  });

  it('organizations PATCH rejects an org id containing a slash', async () => {
    const req = { json: vi.fn().mockResolvedValue({ is_active: true }) } as never;
    const res = await orgPATCH(req, paramsOf({ id: 'org/1' }));
    expect(res.status).toBe(400);
    expect(mocks.docIds).toEqual([]);
  });

  it('user-notifications GET rejects a uid query param containing a slash', async () => {
    const req = {
      nextUrl: { searchParams: new URLSearchParams('uid=aaaaaaaaaa%2Fb') },
    } as never;
    const res = await userNotifGET(req);
    expect(res.status).toBe(400);
    expect(mocks.docIds).toEqual([]);
  });

  it('app update POST rejects a body app_id that mismatches the path param', async () => {
    const form = new FormData();
    form.append('app_id', 'other-app');
    form.append('uid', 'user-1');
    const req = { formData: vi.fn().mockResolvedValue(form) } as never;
    const res = await appUpdatePOST(req, paramsOf({ app_id: 'my-app' }));
    expect(res.status).toBe(400);
    expect(mocks.fetchUrls.length).toBe(0);
  });

  it('app update POST forwards a normal app_id unchanged in the URL', async () => {
    const form = new FormData();
    form.append('app_id', 'my-app');
    form.append('uid', 'user-1');
    const req = { formData: vi.fn().mockResolvedValue(form) } as never;
    const res = await appUpdatePOST(req, paramsOf({ app_id: 'my-app' }));
    expect(res.status).not.toBe(400);
    expect(mocks.fetchUrls[0]).toContain('/v1/apps/my-app');
  });

  it('app update POST encodes a special-char app_id in the upstream URL only', async () => {
    // Mismatch check compares raw values; the id is encoded only where it is
    // interpolated into the upstream path.
    const form = new FormData();
    form.append('uid', 'user-1');
    const req = { formData: vi.fn().mockResolvedValue(form) } as never;
    const res = await appUpdatePOST(req, paramsOf({ app_id: 'a/b' }));
    expect(res.status).not.toBe(400);
    expect(mocks.fetchUrls[0]).toContain('/v1/apps/a%2Fb');
    expect(mocks.fetchUrls[0]).not.toContain('/v1/apps/a/b');
  });
});

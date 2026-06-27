import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
export const dynamic = 'force-dynamic';

const GOAFFPRO_BASE = 'https://api.goaffpro.com/v1';
const GOAFFPRO_TOKEN = process.env.GOAFFPRO_ACCESS_TOKEN || '';

async function goaffproGet(path: string) {
  const res = await fetch(`${GOAFFPRO_BASE}${path}`, {
    headers: {
      'x-goaffpro-access-token': GOAFFPRO_TOKEN,
      'Content-Type': 'application/json',
    },
  });
  if (!res.ok) {
    throw new Error(`GoAffPro error ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

const LIST_FIELDS = [
  'id',
  'name',
  'first_name',
  'last_name',
  'email',
  'ref_code',
  'coupon',
  'status',
  'phone',
  'country',
  'city',
  'website',
  'payment_method',
  'created_at',
  'updated_at',
  'group_id',
].join(',');

// GoAffPro returns empty objects when filtering by id without an explicit
// fields list. Pass the full set of fields we want to render in the detail
// dialog.
const DETAIL_FIELDS = [
  ...LIST_FIELDS.split(','),
  'facebook',
  'twitter',
  'instagram',
  'address_1',
  'state',
  'zip_code',
  'payment_details',
  'comments',
  'personal_message',
  'registration_ip',
].join(',');

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);
    const action = searchParams.get('action') || 'list';

    if (action === 'list') {
      const limit = Math.min(parseInt(searchParams.get('limit') || '50', 10) || 50, 250);
      const offset = parseInt(searchParams.get('offset') || '0', 10) || 0;
      const status = searchParams.get('status') || '';
      const search = searchParams.get('search')?.trim() || '';

      // Search uses a different endpoint that supports keyword matching across
      // columns. Its response wraps the list under `result.affiliates`, not at
      // the top level like the regular list endpoint.
      if (search) {
        const params = new URLSearchParams({
          keyword: search,
          in: 'name,email,ref_code,coupon',
          fields: LIST_FIELDS,
          limit: String(limit),
          operator: 'contains',
        });
        const res = await goaffproGet(`/admin/affiliates/search?${params.toString()}`);
        return NextResponse.json({
          affiliates: res.result?.affiliates || [],
          has_more: false, // search endpoint doesn't paginate
          offset: 0,
          limit,
        });
      }

      const params = new URLSearchParams({
        fields: LIST_FIELDS,
        limit: String(limit),
        offset: String(offset),
      });
      if (status) params.set('status', status);

      const res = await goaffproGet(`/admin/affiliates?${params.toString()}`);
      const affiliates = res.affiliates || [];
      return NextResponse.json({
        affiliates,
        has_more: affiliates.length === limit,
        offset,
        limit,
      });
    }

    if (action === 'detail') {
      const id = searchParams.get('id');
      if (!id || !/^\d+$/.test(id)) {
        return NextResponse.json({ error: 'id is required' }, { status: 400 });
      }

      // GoAffPro doesn't have a singular GET /admin/affiliates/{id}, so use the
      // list endpoint with id filter. The fields parameter is required — without
      // it the API returns an empty object for filtered queries.
      const res = await goaffproGet(
        `/admin/affiliates?id=${id}&limit=1&fields=${DETAIL_FIELDS}`
      );
      const affiliate = (res.affiliates || [])[0];
      if (!affiliate) {
        return NextResponse.json({ error: 'Affiliate not found' }, { status: 404 });
      }

      // Pull aggregate stats and pending balance in parallel
      const [statsRes, pendingRes] = await Promise.allSettled([
        goaffproGet(`/admin/orders?affiliate_id=${id}&status=approved&fields=id&limit=1`),
        goaffproGet(`/admin/payments/pending?affiliate_id=${id}`),
      ]);

      const total_orders =
        statsRes.status === 'fulfilled' ? statsRes.value.total_results || 0 : 0;

      const pendingEntry =
        pendingRes.status === 'fulfilled' ? (pendingRes.value.pending || [])[0] : null;

      return NextResponse.json({
        affiliate,
        stats: {
          total_orders,
          pending_amount: pendingEntry?.pending || 0,
          total_earned: pendingEntry?.total_earned || 0,
          total_paid: pendingEntry?.total_paid || 0,
        },
      });
    }

    return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
  } catch (error) {
    console.error('Affiliates API error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to fetch data' },
      { status: 500 }
    );
  }
}

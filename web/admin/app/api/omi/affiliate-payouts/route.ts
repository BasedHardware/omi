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

async function goaffproPost(path: string, body: unknown) {
  const res = await fetch(`${GOAFFPRO_BASE}${path}`, {
    method: 'POST',
    headers: {
      'x-goaffpro-access-token': GOAFFPRO_TOKEN,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`GoAffPro error ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

function parseTrafficSource(landingPage: string): { source: string; isAd: boolean } {
  if (!landingPage) return { source: 'direct', isAd: false };
  try {
    const url = new URL(landingPage);
    const params = url.searchParams;
    if (params.get('gad_source') || params.get('gclid') || params.get('gad_campaignid')) {
      return { source: 'Google Ads', isAd: true };
    }
    if (params.get('fbclid') || params.get('fb_action_ids')) {
      return { source: 'Facebook Ads', isAd: true };
    }
    if (params.get('utm_source')) {
      const medium = params.get('utm_medium') || '';
      const isAd = ['cpc', 'ppc', 'paid', 'ad', 'ads'].includes(medium.toLowerCase());
      return { source: params.get('utm_source')!, isAd };
    }
  } catch {
    // Invalid URL
  }
  return { source: 'organic', isAd: false };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);
    const action = searchParams.get('action') || 'pending';

    if (action === 'pending') {
      // Get pending payouts with affiliate details
      // upto = last day of 2 months ago (30-day cooldown + payout at start of month)
      // e.g. In May → March 31, In April → Feb 28, In July → May 31
      const now = new Date();
      const lastDayTwoMonthsAgo = new Date(now.getFullYear(), now.getMonth() - 1, 0);
      const upto = lastDayTwoMonthsAgo.toISOString().split('T')[0];

      const pendingRes = await goaffproGet(`/admin/payments/pending?upto=${upto}`);
      const pending = pendingRes.pending || [];

      // Get order details for affiliates with pending amounts
      const enriched = await Promise.all(
        pending
          .filter((p: { pending: number }) => p.pending >= 10) // minimum payout
          .map(async (p: {
            affiliate_id: number;
            name: string;
            email: string;
            pending: number;
            total_earned: number;
            total_paid: number;
            payment_method: string;
            payment_details_data: string;
            ref_code: string;
            amounts: { sales_commission: number; mlm_reward: number };
          }) => {
            // Get orders for this affiliate to analyze traffic sources
            let totalOrderCount = 0;
            let adOrders = 0;
            let organicOrders = 0;
            try {
              const ordersRes = await goaffproGet(
                `/admin/orders?affiliate_id=${p.affiliate_id}&status=approved&fields=id,conversion_details&limit=50`
              );
              const orders = ordersRes.orders || [];
              totalOrderCount = ordersRes.total_results || orders.length;
              for (const o of orders) {
                const { isAd } = parseTrafficSource(o.conversion_details?.landing_page || '');
                if (isAd) adOrders++;
                else organicOrders++;
              }
            } catch {
              // Orders fetch failed — non-fatal
            }

            // Check if affiliate has a valid Stripe account on our platform
            let stripeAccountId: string | null = null;
            let stripeVerified = false;
            try {
              const details = typeof p.payment_details_data === 'string'
                ? JSON.parse(p.payment_details_data)
                : p.payment_details_data || {};
              for (const val of Object.values(details)) {
                if (typeof val === 'string' && val.startsWith('acct_')) {
                  stripeAccountId = val;
                  break;
                }
              }
            } catch {
              // Parse failed
            }

            // Verify the account actually exists on our Stripe platform
            if (stripeAccountId) {
              try {
                const stripe = (await import('@/lib/stripe')).getStripe();
                const account = await stripe.accounts.retrieve(stripeAccountId);
                stripeVerified = !!(account.charges_enabled && account.details_submitted);
                if (!stripeVerified) {
                  stripeAccountId = null; // Account exists but onboarding incomplete
                }
              } catch {
                stripeAccountId = null; // Account doesn't exist on our platform
              }
            }

            return {
              affiliate_id: p.affiliate_id,
              name: p.name,
              email: p.email,
              ref_code: p.ref_code,
              pending_amount: p.pending,
              total_earned: p.total_earned,
              total_paid: p.total_paid,
              payment_method: p.payment_method,
              stripe_account_id: stripeAccountId,
              total_orders: totalOrderCount,
              ad_orders: adOrders,
              organic_orders: organicOrders,
              sales_commission: p.amounts?.sales_commission || 0,
            };
          })
      );

      // Sort by pending amount descending
      enriched.sort((a: { pending_amount: number }, b: { pending_amount: number }) => b.pending_amount - a.pending_amount);

      return NextResponse.json({ affiliates: enriched });
    }

    if (action === 'history') {
      const historyRes = await goaffproGet('/admin/payments?limit=50');
      return NextResponse.json(historyRes);
    }

    return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
  } catch (error) {
    console.error('Affiliate payouts error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to fetch data' },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const body = await request.json();
    const { action } = body;

    if (action === 'transfer') {
      const { affiliate_id } = body;

      if (!affiliate_id) {
        return NextResponse.json(
          { error: 'affiliate_id is required' },
          { status: 400 }
        );
      }

      // Same 2-month-ago cutoff as the GET handler
      const now = new Date();
      const lastDayTwoMonthsAgo = new Date(now.getFullYear(), now.getMonth() - 1, 0);
      const upto = lastDayTwoMonthsAgo.toISOString().split('T')[0];

      // Re-fetch pending amount and Stripe account server-side (never trust client)
      const pendingRes = await goaffproGet(
        `/admin/payments/pending?affiliate_id=${affiliate_id}&upto=${upto}`
      );
      const pendingEntry = (pendingRes.pending || [])[0];
      if (!pendingEntry || pendingEntry.pending < 10) {
        return NextResponse.json(
          { error: 'No pending amount above minimum threshold' },
          { status: 400 }
        );
      }

      const amount = pendingEntry.pending;

      // Extract Stripe account ID from affiliate's payment details
      let stripeAccountId: string | null = null;
      try {
        const details = typeof pendingEntry.payment_details_data === 'string'
          ? JSON.parse(pendingEntry.payment_details_data)
          : pendingEntry.payment_details_data || {};
        for (const val of Object.values(details)) {
          if (typeof val === 'string' && (val as string).startsWith('acct_')) {
            stripeAccountId = val as string;
            break;
          }
        }
      } catch {
        // Parse failed
      }

      if (!stripeAccountId) {
        return NextResponse.json(
          { error: 'Affiliate has no Stripe account connected' },
          { status: 400 }
        );
      }

      // Verify the account exists and is onboarded on our Stripe platform
      const stripe = (await import('@/lib/stripe')).getStripe();
      try {
        const account = await stripe.accounts.retrieve(stripeAccountId);
        if (!account.charges_enabled || !account.details_submitted) {
          return NextResponse.json(
            { error: 'Stripe account exists but onboarding is incomplete' },
            { status: 400 }
          );
        }
      } catch {
        return NextResponse.json(
          { error: 'Stripe account does not exist on this platform' },
          { status: 400 }
        );
      }

      // 1. Send Stripe Transfer with idempotency key to prevent duplicate payments
      const todayUtc = new Date().toISOString().slice(0, 10);
      const idempotencyKey = `affiliate_payout_${affiliate_id}_${Math.round(amount * 100)}_${todayUtc}`;
      const transfer = await stripe.transfers.create(
        {
          amount: Math.round(amount * 100), // cents
          currency: 'usd',
          destination: stripeAccountId,
          metadata: { affiliate_id: String(affiliate_id) },
        },
        { idempotencyKey }
      );

      // 2. Fetch unpaid transaction IDs, then mark as paid in GoAffPro
      // If this fails, return partial success with transfer_id so admin can reconcile
      try {
        const unpaidRes = await goaffproGet(
          `/admin/payments/transactions/unpaid?affiliate_id=${affiliate_id}&upto=${upto}`
        );
        const txIds = (unpaidRes.transactions || [])
          .map((t: { tx_id: number }) => t.tx_id)
          .filter(Boolean);

        if (txIds.length === 0) {
          return NextResponse.json({
            success: true,
            partial: true,
            transfer_id: transfer.id,
            warning: 'Transfer sent but no unpaid transactions found to mark as paid in GoAffPro. Transfer ID: ' + transfer.id,
          });
        }

        await goaffproPost('/admin/payments/transactions/pay', {
          items: [
            {
              affiliate_id: Number(affiliate_id),
              amount,
              tx_ids: txIds,
              payment_method: 'stripe',
              payment_note: `Stripe transfer ${transfer.id}`,
            },
          ],
        });
      } catch (markError) {
        console.error('Stripe transfer succeeded but GoAffPro mark-as-paid failed:', markError);
        return NextResponse.json({
          success: true,
          partial: true,
          transfer_id: transfer.id,
          warning: 'Transfer sent but failed to mark as paid in GoAffPro. Transfer ID: ' + transfer.id,
        });
      }

      return NextResponse.json({
        success: true,
        transfer_id: transfer.id,
      });
    }

    return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
  } catch (error) {
    console.error('Affiliate payout transfer error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Transfer failed' },
      { status: 500 }
    );
  }
}

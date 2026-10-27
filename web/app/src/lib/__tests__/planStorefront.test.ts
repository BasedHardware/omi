import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  budgetExhausted,
  initialInterval,
  offeredPrice,
  parseStorefront,
  partitionTiers,
  shouldGate,
  showBudgetNudge,
  storefrontActionLabel,
  storefrontCheckoutDecision,
  type PlanStorefront,
} from '@/lib/planStorefront';

// The backend goldens are the shared fixtures; mobile pins the same bytes.
const GOLDEN_DIR = resolve(process.cwd(), '../../backend/tests/fixtures/storefront_v2');

function raw(name: string): Record<string, unknown> {
  return JSON.parse(readFileSync(resolve(GOLDEN_DIR, `${name}.json`), 'utf8'));
}

function golden(name: string): PlanStorefront {
  return parseStorefront(raw(name));
}

/** Button label each card draws for the given interval, keyed by plan id. */
function buttons(data: PlanStorefront, interval = initialInterval(data)) {
  const out: Record<string, string | null> = {};
  for (const tier of data.tiers) {
    const price = offeredPrice(tier, interval);
    const decision = price ? storefrontCheckoutDecision(data, tier, price) : 'refuse';
    out[tier.planId] = price ? storefrontActionLabel(tier, price, decision) : null;
  }
  return out;
}

describe('storefront goldens', () => {
  const names = readdirSync(GOLDEN_DIR)
    .filter((file) => file.endsWith('.json'))
    .map((file) => file.replace(/\.json$/, ''));

  it('decodes every golden without losing a tier', () => {
    expect(names.length).toBeGreaterThanOrEqual(15);
    for (const name of names) {
      const data = golden(name);
      expect(data.tiers.length, name).toBe((raw(name).tiers as unknown[]).length);
      expect(data.header, name).toBeTruthy();
    }
  });

  it('Free sees backend CTAs on every higher tier and none on its own card', () => {
    expect(buttons(golden('free_settings'))).toEqual({
      plus: 'Get Plus',
      basic: null,
      operator: 'Get Pro',
      architect: 'Get Architect',
    });
  });

  it('monthly Plus switches to yearly only through the price label', () => {
    const data = golden('plus_monthly_yearly_toggle');
    expect(buttons(data, 'month')).toEqual({
      operator: 'Upgrade to Pro',
      plus: 'Switch to yearly · save $39.98',
      architect: 'Upgrade to Architect',
    });
    const plus = data.tiers.find((t) => t.isCurrent)!;
    // The single yearly price shows on the Monthly chip with the monthly headline.
    expect(offeredPrice(plus, 'month')?.headline).toBe('$19.99/month');
  });

  it('annual Plus starts on the yearly chip and never offers monthly', () => {
    const data = golden('plus_annual_current');
    expect(initialInterval(data)).toBe('year');
    expect(buttons(data).plus).toBeNull();
  });

  it('Pro at 100% upsells Architect; Plus stays inert', () => {
    const data = golden('pro_budget_cap');
    expect(budgetExhausted(data)).toBe(true);
    expect(showBudgetNudge(data)).toBe(false);
    expect(buttons(data, 'month')).toEqual({
      architect: 'Upgrade to Architect',
      plus: null,
      operator: 'Switch to yearly · save $99.98',
    });
    expect(partitionTiers(data).primary.map((t) => t.planId)).toEqual([
      'architect',
      'operator',
    ]);
  });

  it('Pro settings never lists Architect', () => {
    expect(golden('pro_settings').tiers.map((t) => t.planId)).not.toContain('architect');
  });

  it('80% budget shows the nudge for Free and Plus', () => {
    for (const name of ['free_budget80', 'plus_budget80']) {
      const data = golden(name);
      expect(showBudgetNudge(data), name).toBe(data.usage.nudgeLine !== null);
      expect(budgetExhausted(data), name).toBe(false);
      expect(data.usage.meterLine, name).toContain('80% used');
    }
  });

  it('cancel-scheduled resubscribes only on the current price and lists every tier', () => {
    for (const name of ['cancel_scheduled_plus', 'cancel_scheduled_pro']) {
      const data = golden(name);
      const labels = buttons(data);
      const current = data.tiers.find((t) => t.isCurrent)!;
      expect(labels[current.planId], name).toBe('Resubscribe');
      const price = current.prices[0];
      expect(storefrontCheckoutDecision(data, current, price), name).toBe('resubscribe');
      for (const tier of data.tiers.filter((t) => !t.isCurrent)) {
        expect(labels[tier.planId], `${name}:${tier.planId}`).toBeNull();
        expect(tier.blockedLine).toBe('Resubscribe first to change plans');
      }
      const { primary, rest } = partitionTiers(data);
      expect(primary[0].isCurrent).toBe(true);
      expect(primary.map((t) => t.planId)).toContain('basic');
      expect(rest).toEqual([]);
    }
  });

  it('legacy plans never check out', () => {
    for (const name of ['legacy_neo', 'legacy_unlimited']) {
      const data = golden(name);
      expect(data.current?.legacy).toBe(true);
      expect(data.current?.legacyNote).toBeTruthy();
      expect(
        Object.values(buttons(data)).every((label) => label === null),
        name,
      ).toBe(true);
    }
  });

  it('Pro gates apply below Pro only when the backend lists them', () => {
    const free = golden('free_pro_gate_proactive');
    expect(shouldGate(free, 'proactive_agent')).toBe(
      free.usage.proGates.includes('proactive_agent'),
    );
    expect(shouldGate(golden('pro_budget_cap'), 'proactive_agent')).toBe(false);
    expect(shouldGate(golden('legacy_neo'), 'proactive_agent')).toBe(false);
  });

  it('Omi Pro clears every Pro gate', () => {
    const free = golden('free_pro_gate_proactive');
    const gated = { ...free, usage: { ...free.usage, proGates: ['proactive_agent'] } };
    expect(shouldGate(gated, 'proactive_agent')).toBe(true);
    const omiPro = { ...gated, current: { ...gated.current!, planId: 'unlimited_v2' } };
    expect(shouldGate(omiPro, 'proactive_agent')).toBe(false);
    expect(shouldGate(gated, 'proactive_agent', 'unlimited_v2')).toBe(false);
  });
});

describe('defensive decode', () => {
  it('rejects other schema versions', () => {
    expect(() =>
      parseStorefront({ ...raw('free_settings'), schema_version: 3 }),
    ).toThrow();
    expect(() => parseStorefront(null)).toThrow();
  });

  it('ignores unknown fields and degrades unknown actions, intervals and kinds', () => {
    const payload = raw('free_settings') as {
      tiers: Array<Record<string, unknown>>;
      usage: Record<string, unknown>;
    };
    payload.tiers[0] = {
      ...payload.tiers[0],
      action: 'trial',
      future_field: { nested: true },
    };
    payload.tiers[2] = {
      ...payload.tiers[2],
      prices: [
        ...(payload.tiers[2].prices as unknown[]),
        { interval: 'week', amount_minor: 1, currency: 'usd', headline: '$1/week' },
      ],
    };
    payload.usage = { ...payload.usage, kind: 'tokens' };
    const data = parseStorefront({ ...payload, brand_new: 1 });
    expect(data.tiers[0].action).toBe('none');
    expect(data.tiers[2].prices.map((p) => p.interval)).toEqual(['month', 'year']);
    expect(data.usage.kind).toBe('unavailable');
    expect(buttons(data).plus).toBeNull();
  });

  it('renders an unknown plan id but never sells it', () => {
    const payload = raw('free_settings') as { tiers: Array<Record<string, unknown>> };
    payload.tiers.push({
      ...payload.tiers[3],
      tier_id: 'galaxy:ladder_v2',
      plan_id: 'galaxy',
      name: 'Galaxy',
    });
    const data = parseStorefront(payload);
    expect(data.tiers.map((t) => t.planId)).toContain('galaxy');
    expect(buttons(data).galaxy).toBeNull();
  });

  it('drops duplicate tiers and malformed rows instead of failing the sheet', () => {
    const payload = raw('free_settings') as { tiers: unknown[] };
    payload.tiers.push(payload.tiers[0], { plan_id: 7 });
    expect(parseStorefront(payload).tiers.length).toBe(4);
  });

  it('refuses a monthly downgrade from an annual subscription', () => {
    const data = golden('plus_annual_current');
    const pro = data.tiers.find((t) => t.planId === 'operator')!;
    const month = pro.prices.find((p) => p.interval === 'month')!;
    // Upgrading tiers is allowed in either interval; the same-tier monthly price is not offered.
    expect(storefrontCheckoutDecision(data, pro, month)).toBe('checkout');
    const plus = data.tiers.find((t) => t.isCurrent)!;
    const forged = {
      ...plus,
      action: 'checkout' as const,
      prices: [{ ...month, id: 'price_plus_month' }],
    };
    expect(storefrontCheckoutDecision(data, forged, forged.prices[0])).toBe('refuse');
  });
});

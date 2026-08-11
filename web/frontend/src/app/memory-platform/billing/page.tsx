import type { Metadata } from 'next';
import PlatformShell from '../components/platform-shell';
import BillingPanel from '../components/billing-panel';
import { buildPlatformMetadata } from '../utils/metadata';

export async function generateMetadata(): Promise<Metadata> {
  return buildPlatformMetadata({
    title: 'Memory Platform billing',
    description:
      'Your Omi plan, platform-API quota, usage, and upgrade path for the memory platform.',
    path: '/memory-platform/billing',
    noIndex: true,
  });
}

export default function MemoryPlatformBillingPage() {
  return (
    <PlatformShell active="/memory-platform/billing">
      <div className="max-w-3xl">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#b9f36b]">
          Plan &amp; usage
        </p>
        <h1 className="mt-5 text-4xl font-semibold tracking-tight text-white md:text-5xl">
          Billing.
        </h1>
        <p className="mt-5 text-[17px] leading-8 text-neutral-400">
          Platform API access follows your Omi subscription. Usage and overage are
          reported by the backend; checkout and plan management run through Stripe.
        </p>
      </div>

      <div className="mt-10">
        <BillingPanel />
      </div>
    </PlatformShell>
  );
}

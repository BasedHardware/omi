'use client';

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AllAffiliatesTab } from './_components/all-affiliates-tab';
import { PendingPayoutsTab } from './_components/pending-payouts-tab';
import { AffiliateDetailDialog } from './_components/affiliate-detail-dialog';
import { Affiliate } from '@/hooks/useAffiliates';

export default function AffiliatesPage() {
  const [selected, setSelected] = useState<Affiliate | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Affiliates</h1>
        <p className="text-muted-foreground">
          Browse all affiliates and manage commission payouts
        </p>
      </div>

      <Tabs defaultValue="all" className="space-y-4">
        <TabsList>
          <TabsTrigger value="all">All Affiliates</TabsTrigger>
          <TabsTrigger value="payouts">Pending Payouts</TabsTrigger>
        </TabsList>

        <TabsContent value="all">
          <AllAffiliatesTab onSelect={setSelected} />
        </TabsContent>

        <TabsContent value="payouts">
          <PendingPayoutsTab />
        </TabsContent>
      </Tabs>

      <AffiliateDetailDialog
        affiliateId={selected?.id ?? null}
        open={!!selected}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </div>
  );
}

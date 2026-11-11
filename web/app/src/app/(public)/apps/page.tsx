'use client';

import { useEffect, useState } from 'react';
import { getAllAppsV2, getAppsV2, transformToPlugin } from '@/lib/api/public';
import AppList from '@/components/marketplace/AppList';
import { PromoCard } from '@/components/marketplace/PromoCard';
import { CollectionPageJsonLd } from '@/components/seo/JsonLd';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function AppsMarketplacePage() {
  const [plugins, setPlugins] = useState<ReturnType<typeof transformToPlugin>[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    getAppsV2(true)
      .then((response) => {
        if (!active) return;
        const initialApps = Array.from(
          new Map(
            response.groups.flatMap((group) => group.data).map((app) => [app.id, app]),
          ).values(),
        );
        setPlugins(initialApps.map(transformToPlugin));
        setLoaded(true);
        return getAllAppsV2(true);
      })
      .then((allApps) => {
        if (!active || !allApps?.length) return;
        setPlugins(allApps.map(transformToPlugin));
      });
    return () => {
      active = false;
    };
  }, []);

  if (!loaded) {
    return <div className="min-h-screen bg-[#0B0F17]" />;
  }

  // Fetch ALL v2 apps by paginating through all capability groups
  // This makes multiple requests during build time but ensures all 600+ apps are available

  return (
    <div className="min-h-screen bg-[#0B0F17]">
      <CollectionPageJsonLd
        name="Omi App Store"
        description="Explore and install AI-powered apps for Omi. Enhance your experience with productivity tools, conversation insights, and more."
        url="/apps"
      />
      <AppList initialPlugins={plugins} initialStats={[]} />
      <PromoCard />
    </div>
  );
}

registerMoonshineRoute('/apps', AppsMarketplacePage, 'public');

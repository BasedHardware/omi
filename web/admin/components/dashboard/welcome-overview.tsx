"use client";

import { DashboardStats } from "@/components/dashboard/stats";
import { PopularApps } from "@/components/dashboard/popular-apps";
import { AppsList } from "@/components/dashboard/apps-list";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useApps } from "@/hooks/useApps";
import { useState } from "react";

const Spinner = () => (
  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto my-8"></div>
);

export function WelcomeOverview() {
  const { apps, isLoading, error } = useApps();
  const [selectedAppIds, setSelectedAppIds] = useState<Set<string>>(new Set());

  const errorMessage =
    error && (error as any)?.message ? (error as any).message : null;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Welcome back!</h1>
          <p className="text-muted-foreground mt-1">System overview and key metrics</p>
        </div>
      </div>

      <DashboardStats />

      <Card>
        <CardContent className="pt-6">
          <PopularApps />
        </CardContent>
      </Card>

      <div className="rounded-xl border bg-card">
        <div className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Latest Apps</h2>
            <Button variant="ghost" asChild>
              <Link href="/dashboard/apps" className="gap-2">
                View All Apps <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
          {isLoading ? (
            <div className="flex items-center justify-center min-h-[200px]">
              <Spinner />
            </div>
          ) : errorMessage ? (
            <p className="text-destructive text-center py-4">{errorMessage}</p>
          ) : !apps || apps.length === 0 ? (
            <p>No apps found.</p>
          ) : (
            <AppsList
              apps={apps}
              limit={5}
              minimal
              selectedAppIds={selectedAppIds}
              onSelectedAppIdsChange={setSelectedAppIds}
            />
          )}
        </div>
      </div>
    </div>
  );
}

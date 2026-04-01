'use client'; // Make this a Client Component

import { DashboardStats } from "@/components/dashboard/stats";
import { PopularApps } from "@/components/dashboard/popular-apps";
import { AppsList } from "@/components/dashboard/apps-list";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Plus, ArrowRight } from "lucide-react";
import Link from "next/link";
import { useApps } from '@/hooks/useApps'; // Import the new hook
import { useState } from 'react';

// Simple spinner placeholder (consider moving to shared UI)
const Spinner = () => (
  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto my-8"></div>
);

// Remove async from component definition
export default function DashboardPage() {
  const { apps, isLoading, error } = useApps(); // Use the hook
  const [selectedAppIds, setSelectedAppIds] = useState<Set<string>>(new Set());

  // Can show a general loading state while auth is resolving - isLoading from useApps includes auth loading
  if (isLoading) {
    return <div className="flex items-center justify-center min-h-[300px]"><Spinner /></div>;
  }

  // Handle error state from the hook
  if (error) {
    // Simplest check: if error exists, try getting message, otherwise fallback
    const errorMessage = (error as any)?.message || 'An unknown error occurred';
    return <div className="text-red-500 text-center py-10">Error loading apps: {errorMessage}</div>;
  }

  const handleSelectedAppIdsChange = (newSelectedAppIds: Set<string>) => {
    setSelectedAppIds(newSelectedAppIds);
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Welcome back!</h1>
          <p className="text-muted-foreground mt-1">
            System overview and key metrics
          </p>
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
             <div className="flex items-center justify-center min-h-[200px]"><Spinner /></div>
          ) : error ? (
            // Simplest check again, casting to any to bypass linter quirk
            <p className="text-destructive text-center py-4">{(error as any)?.message || 'An unknown error occurred'}</p>
          ) : !apps || apps.length === 0 ? (
            <p>No apps found.</p>
          ) : (
            // Pass the fetched apps data to AppsList
            <AppsList 
              apps={apps} 
              limit={5} 
              minimal 
              selectedAppIds={selectedAppIds} 
              onSelectedAppIdsChange={handleSelectedAppIdsChange}
            />
          )}
        </div>
      </div>
    </div>
  );
}
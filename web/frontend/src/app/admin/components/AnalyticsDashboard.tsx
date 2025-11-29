'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/src/components/ui/card';
import { Button } from '@/src/components/ui/button';
import { useToast } from '@/src/hooks/use-toast';
import { Toaster } from '@/src/components/ui/toaster';
import {
  Users,
  MessageSquare,
  Brain,
  Package,
  Loader2,
  Activity,
} from 'lucide-react';
import { getPlatformAnalytics, PlatformAnalytics } from '@/src/lib/api/admin';

interface AnalyticsDashboardProps {
  adminKey: string;
}

export default function AnalyticsDashboard({ adminKey }: AnalyticsDashboardProps) {
  const { toast } = useToast();
  const [analytics, setAnalytics] = useState<PlatformAnalytics | null>(null);
  const [loading, setLoading] = useState(false);

  const loadAnalytics = async () => {
    setLoading(true);
    try {
      const data = await getPlatformAnalytics(adminKey);
      setAnalytics(data);
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to load analytics',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAnalytics();
  }, []);

  return (
    <>
      <div>
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold">Platform Analytics</h2>
            <p className="mt-1 text-sm text-neutral-500">
              Overview of platform-wide statistics
            </p>
          </div>
          <Button onClick={loadAnalytics} disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Loading...
              </>
            ) : (
              <>
                <Activity className="mr-2 h-4 w-4" />
                Refresh
              </>
            )}
          </Button>
        </div>

        {/* Stats Cards */}
        {analytics ? (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {/* Total Users */}
            <Card className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-neutral-500">Total Users</p>
                  <p className="mt-2 text-3xl font-bold">{analytics.users_count.toLocaleString()}</p>
                  <p className="mt-1 text-xs text-neutral-400">Registered accounts</p>
                </div>
                <div className="rounded-full bg-blue-100 p-3">
                  <Users className="h-6 w-6 text-blue-600" />
                </div>
              </div>
            </Card>

            {/* Total Memories */}
            <Card className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-neutral-500">Total Memories</p>
                  <p className="mt-2 text-3xl font-bold">{analytics.memories_count.toLocaleString()}</p>
                  <p className="mt-1 text-xs text-neutral-400">Across all users</p>
                </div>
                <div className="rounded-full bg-purple-100 p-3">
                  <Brain className="h-6 w-6 text-purple-600" />
                </div>
              </div>
            </Card>

            {/* Total Conversations */}
            <Card className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-neutral-500">Total Conversations</p>
                  <p className="mt-2 text-3xl font-bold">{analytics.conversations_count.toLocaleString()}</p>
                  <p className="mt-1 text-xs text-neutral-400">All recorded chats</p>
                </div>
                <div className="rounded-full bg-green-100 p-3">
                  <MessageSquare className="h-6 w-6 text-green-600" />
                </div>
              </div>
            </Card>

            {/* Total Apps */}
            <Card className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-neutral-500">Total Apps</p>
                  <p className="mt-2 text-3xl font-bold">{analytics.apps_count.toLocaleString()}</p>
                  <p className="mt-1 text-xs text-neutral-400">Published apps</p>
                </div>
                <div className="rounded-full bg-amber-100 p-3">
                  <Package className="h-6 w-6 text-amber-600" />
                </div>
              </div>
            </Card>
          </div>
        ) : (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <Card key={i} className="p-6">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="h-4 w-24 animate-pulse rounded bg-neutral-200"></div>
                    <div className="mt-2 h-8 w-16 animate-pulse rounded bg-neutral-200"></div>
                    <div className="mt-1 h-3 w-20 animate-pulse rounded bg-neutral-200"></div>
                  </div>
                  <div className="h-12 w-12 animate-pulse rounded-full bg-neutral-200"></div>
                </div>
              </Card>
            ))}
          </div>
        )}

        {/* Additional Stats */}
        {analytics && (
          <div className="mt-6 grid gap-6 md:grid-cols-3">
            {/* Average Memories per User */}
            <Card className="p-6">
              <div>
                <p className="text-sm font-medium text-neutral-500">Avg Memories per User</p>
                <p className="mt-2 text-2xl font-bold">
                  {analytics.users_count > 0
                    ? (analytics.memories_count / analytics.users_count).toFixed(1)
                    : '0'}
                </p>
              </div>
            </Card>

            {/* Average Conversations per User */}
            <Card className="p-6">
              <div>
                <p className="text-sm font-medium text-neutral-500">Avg Conversations per User</p>
                <p className="mt-2 text-2xl font-bold">
                  {analytics.users_count > 0
                    ? (analytics.conversations_count / analytics.users_count).toFixed(1)
                    : '0'}
                </p>
              </div>
            </Card>

            {/* Apps per User */}
            <Card className="p-6">
              <div>
                <p className="text-sm font-medium text-neutral-500">Apps per User</p>
                <p className="mt-2 text-2xl font-bold">
                  {analytics.users_count > 0
                    ? (analytics.apps_count / analytics.users_count).toFixed(2)
                    : '0'}
                </p>
              </div>
            </Card>
          </div>
        )}

        <Toaster />
      </div>
    </>
  );
}

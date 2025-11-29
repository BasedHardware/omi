'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/src/components/ui/card';
import { Button } from '@/src/components/ui/button';
import { useToast } from '@/src/hooks/use-toast';
import { Loader2, RefreshCw, BarChart3 } from 'lucide-react';
import {
  getConversationCategoriesAnalytics,
  ConversationCategoriesAnalytics,
} from '@/src/lib/api/admin';

interface ConversationCategoriesChartProps {
  adminKey: string;
}

const CATEGORY_COLORS: Record<string, string> = {
  personal: 'bg-blue-500',
  education: 'bg-green-500',
  health: 'bg-red-500',
  finance: 'bg-yellow-500',
  legal: 'bg-purple-500',
  philosophy: 'bg-indigo-500',
  spiritual: 'bg-pink-500',
  science: 'bg-cyan-500',
  entrepreneurship: 'bg-orange-500',
  parenting: 'bg-rose-500',
  romantic: 'bg-fuchsia-500',
  travel: 'bg-teal-500',
  inspiration: 'bg-amber-500',
  technology: 'bg-violet-500',
  business: 'bg-emerald-500',
  social: 'bg-sky-500',
  work: 'bg-slate-500',
  sports: 'bg-lime-500',
  politics: 'bg-red-600',
  literature: 'bg-amber-600',
  history: 'bg-stone-500',
  architecture: 'bg-zinc-500',
  music: 'bg-purple-600',
  weather: 'bg-blue-400',
  news: 'bg-gray-500',
  entertainment: 'bg-pink-600',
  psychology: 'bg-indigo-600',
  real: 'bg-green-600',
  design: 'bg-fuchsia-600',
  family: 'bg-rose-600',
  economics: 'bg-yellow-600',
  environment: 'bg-emerald-600',
  other: 'bg-neutral-500',
};

function formatCategoryName(category: string): string {
  return category
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export default function ConversationCategoriesChart({
  adminKey,
}: ConversationCategoriesChartProps) {
  const { toast } = useToast();
  const [data, setData] = useState<ConversationCategoriesAnalytics | null>(null);
  const [loading, setLoading] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const result = await getConversationCategoriesAnalytics(adminKey);
      setData(result);
    } catch (error) {
      toast({
        title: 'Error',
        description:
          error instanceof Error ? error.message : 'Failed to load conversation categories',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const maxCount = data?.categories[0]?.count || 1;

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Conversation Categories</h2>
          <p className="mt-1 text-sm text-neutral-500">
            Distribution of conversations by category
          </p>
        </div>
        <Button onClick={loadData} disabled={loading}>
          {loading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Loading...
            </>
          ) : (
            <>
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
            </>
          )}
        </Button>
      </div>

      {/* Summary Card */}
      {data && (
        <Card className="mb-6 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-neutral-500">Total Conversations</p>
              <p className="mt-2 text-3xl font-bold">{data.total.toLocaleString()}</p>
              <p className="mt-1 text-xs text-neutral-400">
                Across {data.categories.length} categories
              </p>
            </div>
            <div className="rounded-full bg-indigo-100 p-3">
              <BarChart3 className="h-6 w-6 text-indigo-600" />
            </div>
          </div>
        </Card>
      )}

      {/* Chart */}
      {data ? (
        <Card className="p-6">
          <h3 className="mb-4 text-lg font-semibold">Categories Breakdown</h3>
          <div className="space-y-3">
            {data.categories.map((item) => {
              const percentage = ((item.count / data.total) * 100).toFixed(1);
              const barWidth = (item.count / maxCount) * 100;
              const colorClass = CATEGORY_COLORS[item.category] || 'bg-neutral-500';

              return (
                <div key={item.category} className="group">
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-medium">{formatCategoryName(item.category)}</span>
                    <span className="text-neutral-500">
                      {item.count.toLocaleString()} ({percentage}%)
                    </span>
                  </div>
                  <div className="h-6 w-full overflow-hidden rounded-full bg-neutral-100">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${colorClass}`}
                      style={{ width: `${barWidth}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      ) : (
        <Card className="p-6">
          <div className="space-y-4">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i}>
                <div className="mb-1 flex items-center justify-between">
                  <div className="h-4 w-24 animate-pulse rounded bg-neutral-200"></div>
                  <div className="h-4 w-16 animate-pulse rounded bg-neutral-200"></div>
                </div>
                <div className="h-6 w-full animate-pulse rounded-full bg-neutral-200"></div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

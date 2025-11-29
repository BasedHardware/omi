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
import {
  ResponsiveContainer,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Cell,
} from 'recharts';

interface ConversationCategoriesChartProps {
  adminKey: string;
}

const COLORS = [
  '#3B82F6', // blue
  '#EF4444', // red
  '#10B981', // green
  '#F59E0B', // amber
  '#8B5CF6', // purple
  '#EC4899', // pink
  '#06B6D4', // cyan
  '#F97316', // orange
  '#6366F1', // indigo
  '#14B8A6', // teal
  '#84CC16', // lime
  '#A855F7', // violet
  '#22C55E', // emerald
  '#0EA5E9', // sky
  '#64748B', // slate
  '#78716C', // stone
  '#71717A', // zinc
  '#737373', // neutral
];

function formatCategoryName(category: string): string {
  return category
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: {
      name: string;
      value: number;
      percentage: string;
    };
  }>;
}

const CustomTooltip = ({ active, payload }: CustomTooltipProps) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="rounded-lg border bg-white p-3 shadow-lg">
        <p className="font-semibold">{data.name}</p>
        <p className="text-sm text-neutral-600">
          Count: <span className="font-medium">{data.value.toLocaleString()}</span>
        </p>
        <p className="text-sm text-neutral-600">
          Percentage: <span className="font-medium">{data.percentage}%</span>
        </p>
      </div>
    );
  }
  return null;
};


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

  const chartData = data?.categories.map((item, index) => ({
    name: formatCategoryName(item.category),
    value: item.count,
    percentage: ((item.count / (data?.total || 1)) * 100).toFixed(1),
    fill: COLORS[index % COLORS.length],
  })) || [];

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
          <h3 className="mb-6 text-lg font-semibold">Categories Breakdown</h3>

          {/* Horizontal Bar Chart */}
          <div style={{ height: `${Math.max(400, chartData.length * 40)}px` }} className="w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} />
                <XAxis type="number" />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={90}
                  tick={{ fontSize: 12 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      ) : (
        <Card className="p-6">
          <div className="flex h-[400px] items-center justify-center">
            <div className="text-center">
              <Loader2 className="mx-auto h-8 w-8 animate-spin text-neutral-400" />
              <p className="mt-2 text-sm text-neutral-500">Loading chart data...</p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

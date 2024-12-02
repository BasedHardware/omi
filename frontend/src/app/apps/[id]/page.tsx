import envConfig from '@/src/constants/envConfig';
import {
  Star,
  Download,
  ArrowLeft,
  Brain,
  Cpu,
  Bell,
  Plug2,
  MessageSquare,
  Info,
} from 'lucide-react';
import { Card, CardContent } from '@/src/components/ui/card';
import { Button } from '@/src/components/ui/button';
import { Plugin, PluginStat } from '../components/types';
import { headers } from 'next/headers';
import Link from 'next/link';
import { cn } from '@/src/lib/utils';

// Helper functions from PluginCard
const getCapabilityColor = (capability: string): string => {
  const colors: Record<string, string> = {
    'ai-powered': 'bg-indigo-500/15 text-indigo-300',
    memories: 'bg-rose-500/15 text-rose-300',
    notification: 'bg-emerald-500/15 text-emerald-300',
    integration: 'bg-sky-500/15 text-sky-300',
    chat: 'bg-violet-500/15 text-violet-300',
  };
  return colors[capability.toLowerCase()] ?? 'bg-gray-700/20 text-gray-300';
};

const formatCapabilityName = (capability: string): string => {
  const nameMap: Record<string, string> = {
    memories: 'memories',
    external_integration: 'integration',
    proactive_notification: 'notification',
    chat: 'chat',
  };
  return nameMap[capability.toLowerCase()] ?? capability;
};

const getCapabilityIcon = (capability: string) => {
  const icons: Record<string, React.ElementType> = {
    'ai-powered': Brain,
    memories: Cpu,
    notification: Bell,
    integration: Plug2,
    chat: MessageSquare,
  };
  return icons[capability.toLowerCase()] ?? Info;
};

// Helper function to format category name
const formatCategoryName = (category: string): string => {
  return category
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

// Helper function to determine platform and get appropriate link
function getPlatformLink(userAgent: string) {
  const isAndroid = /android/i.test(userAgent);
  const isIOS = /iphone|ipad|ipod/i.test(userAgent);

  return isAndroid
    ? 'https://play.google.com/store/apps/details?id=com.friend.ios'
    : isIOS
    ? 'https://apps.apple.com/us/app/friend-ai-wearable/id6502156163'
    : 'https://omi.me';
}

export default async function PluginDetailView({ params }: { params: { id: string } }) {
  const response = await fetch(
    `${envConfig.API_URL}/v1/approved-apps?include_reviews=true`,
  );
  const plugins = (await response.json()) as Plugin[];
  const { id } = params;
  const plugin = plugins.find((p) => p.id === id);

  if (!plugin) {
    throw new Error('App not found');
  }

  const statsResponse = await fetch(
    'https://raw.githubusercontent.com/BasedHardware/omi/refs/heads/main/community-plugin-stats.json',
  );
  const stats = (await statsResponse.json()) as PluginStat[];
  const stat = stats.find((p) => p.id === id);

  const userAgent = headers().get('user-agent') || '';
  const link = getPlatformLink(userAgent);

  // Get related apps based on category
  const relatedApps = plugins
    .filter((p) => p.category === plugin.category && p.id !== plugin.id)
    .slice(0, 6);

  const categoryName = formatCategoryName(plugin.category);

  return (
    <div className="min-h-screen bg-[#0B0F17]">
      {/* Banner */}
      <div className="bg-[#1A1F2E] px-4 py-3 text-center text-sm text-white">
        Submit your own App by November 30th and get a free trip to OMI HQ in San
        Francisco
        <Link href="/hackathon" className="text-[#6C8EEF] hover:underline">
          Join Hackathon
        </Link>
      </div>

      {/* Main Content */}
      <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 sm:py-6 lg:px-8 lg:py-8">
        {/* Navigation */}
        <nav className="mb-4 flex items-center justify-between sm:mb-6 lg:mb-8">
          <Link
            href="/apps"
            className="group inline-flex items-center text-gray-400 transition-all duration-300 hover:text-white"
          >
            <ArrowLeft className="mr-2 h-4 w-4 transition-transform duration-300 group-hover:-translate-x-1 sm:h-5 sm:w-5" />
            <span className="text-sm font-medium">Back to Apps</span>
          </Link>
          <div className="flex items-center space-x-2 text-xs text-gray-400 sm:text-sm">
            <Link href="/apps" className="text-[#6C8EEF] hover:underline">
              Apps
            </Link>
            <span>/</span>
            <span>{categoryName}</span>
          </div>
        </nav>

        {/* App Header */}
        <div className="mb-12">
          <div className="flex items-start justify-between">
            <div className="flex items-start space-x-8">
              <div className="relative">
                <div className="absolute -inset-4 rounded-2xl bg-white/5 opacity-0 transition-all duration-300 group-hover:opacity-100" />
                <img
                  src={plugin.image}
                  alt={plugin.name}
                  className="relative h-32 w-32 rounded-2xl object-cover shadow-xl"
                />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-white">{plugin.name}</h1>
                <p className="mt-2 text-gray-400">by {plugin.author}</p>

                {/* Capability Pills */}
                <div className="flex flex-wrap gap-1.5 sm:mt-4 sm:gap-2">
                  {Array.from(plugin.capabilities).map((cap) => {
                    const formattedCap = formatCapabilityName(cap);
                    const Icon = getCapabilityIcon(formattedCap);
                    return (
                      <span
                        key={cap}
                        className={cn(
                          'inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-medium sm:px-3 sm:py-1.5 sm:text-sm',
                          getCapabilityColor(formattedCap),
                        )}
                      >
                        <Icon className="h-3 w-3 sm:h-4 sm:w-4" />
                        {formattedCap}
                      </span>
                    );
                  })}
                </div>

                <p className="max-w-3xl text-sm leading-relaxed text-gray-300 sm:mt-6 sm:text-base lg:text-lg">
                  {plugin.description}
                </p>

                {/* Stats */}
                <div className="flex items-center space-x-3 text-gray-400 sm:mt-4 sm:space-x-4">
                  <div className="flex items-center">
                    <Star className="mr-1 h-3 w-3 text-yellow-400 sm:h-4 sm:w-4" />
                    <span className="text-sm sm:text-base">
                      {(plugin.rating_avg ?? 0).toFixed(1)} ({plugin.rating_count})
                    </span>
                  </div>
                  <span>•</span>
                  <div className="flex items-center">
                    <Download className="mr-1 h-3 w-3 sm:h-4 sm:w-4" />
                    <span className="text-sm sm:text-base">
                      {plugin.installs.toLocaleString()} installs
                    </span>
                  </div>
                </div>

                {/* Action Button */}
                <div className="mt-6 sm:mt-8">
                  <Button
                    className="inline-flex items-center space-x-2 bg-[#6C8EEF] py-2.5 text-sm font-medium text-white transition-all hover:bg-[#5A7DE8] hover:shadow-lg sm:px-6 sm:py-3 sm:text-base lg:px-8 lg:py-4 lg:text-lg"
                    asChild
                  >
                    <Link href={link}>
                      <span>Try it</span>
                      <ArrowLeft className="ml-2 h-4 w-4 rotate-180 sm:h-5 sm:w-5" />
                    </Link>
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Related Apps Section */}
        <div>
          <h2 className="mb-3 text-base font-semibold text-white sm:mb-4 sm:text-lg">
            More {categoryName} Apps
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
            {relatedApps.map((app) => (
              <Link key={app.id} href={`/apps/${app.id}`}>
                <Card className="h-[100px] border-none bg-[#1A1F2E] transition-all duration-300 hover:bg-[#242938] hover:shadow-xl sm:h-[120px]">
                  <CardContent className="p-2 sm:p-3">
                    <div className="flex space-x-2 sm:space-x-3">
                      <img
                        src={app.image}
                        alt={app.name}
                        className="h-10 w-10 rounded-lg object-cover sm:h-12 sm:w-12"
                      />
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate text-sm font-medium text-white sm:text-base">
                          {app.name}
                        </h3>
                        <p className="mt-0.5 line-clamp-2 text-xs text-gray-400 sm:mt-1">
                          {app.description}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

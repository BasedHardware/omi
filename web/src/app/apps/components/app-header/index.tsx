/* eslint-disable prettier/prettier */
import { Brain, Cpu, Bell, Plug2, MessageSquare, Info } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import type { Plugin } from '../types';

interface AppHeaderProps {
  plugin: Plugin;
}

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

export function AppHeader({ plugin }: AppHeaderProps) {
  return (
    <div className="flex items-start justify-between">
      <div className="flex items-start space-x-8">
        <div className="group relative">
          <div className="absolute -inset-4 rounded-2xl bg-white/5 opacity-0 transition-all duration-300 group-hover:opacity-100" />
          <img
            src={plugin.image}
            alt={plugin.name}
            className="relative h-32 w-32 rounded-2xl object-cover shadow-xl transition-transform duration-300 group-hover:scale-105"
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

          {/* Store Buttons */}
          <div className="mt-6 flex items-center gap-4">
            <a
              href="https://apps.apple.com/app/id123456789"
              target="_blank"
              rel="noopener noreferrer"
              className="flex h-10 items-center gap-2 rounded-lg bg-[#1A1F2E] px-4 py-2 text-sm font-medium text-white transition-all hover:bg-[#242938]"
            >
              <img src="/app-store.svg" alt="App Store" className="h-5 w-5" />
              <span>App Store</span>
            </a>
            <a
              href="https://play.google.com/store/apps/details?id=com.omi.app"
              target="_blank"
              rel="noopener noreferrer"
              className="flex h-10 items-center gap-2 rounded-lg bg-[#1A1F2E] px-4 py-2 text-sm font-medium text-white transition-all hover:bg-[#242938]"
            >
              <img src="/play-store.svg" alt="Play Store" className="h-5 w-5" />
              <span>Play Store</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
} 
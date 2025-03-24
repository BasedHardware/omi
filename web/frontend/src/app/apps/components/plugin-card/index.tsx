'use client';

import {
  Star,
  Download,
  Brain,
  Cpu,
  Bell,
  Plug2,
  MessageSquare,
  Info,
} from 'lucide-react';
import type { Plugin, PluginStat } from '../types';

export interface PluginCardProps {
  plugin: Plugin;
  stat?: PluginStat;
}

const formatInstalls = (num: number) => {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
};

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

export function PluginCard({ plugin, stat }: PluginCardProps) {
  const handleClick = () => {
    window.location.href = `/apps/${plugin.id}`;
  };

  return (
    <button
      onClick={handleClick}
      className="group relative flex h-full w-full flex-col overflow-hidden rounded-xl bg-[#1A1F2E] text-left shadow-lg transition-all duration-300 hover:translate-y-[-4px] hover:scale-[1.02] hover:bg-[#242938] hover:shadow-2xl hover:shadow-black/30"
    >
      <div className="absolute inset-0 bg-gradient-to-br from-transparent to-black/5 transition-opacity duration-300 group-hover:opacity-70" />

      <div className="z-10 flex flex-1 flex-col p-6">
        <div className="mb-6">
          <div className="flex items-start space-x-4">
            <img
              src={plugin.image || 'https://via.placeholder.com/80'}
              alt={plugin.name}
              className="h-14 w-14 rounded-xl object-cover shadow-lg transition-transform duration-300 group-hover:scale-110 group-hover:shadow-xl"
            />
            <div className="flex-1">
              <h2 className="line-clamp-2 text-lg font-bold leading-tight text-white">
                {plugin.name}
              </h2>
              <p className="mt-2 line-clamp-2 text-sm text-gray-400 group-hover:text-gray-300">
                {plugin.description}
              </p>
            </div>
          </div>
        </div>

        <div className="mb-4 border-t border-gray-800/50 transition-colors duration-300 group-hover:border-gray-700/70" />

        <div className="mb-6 flex h-[2.5rem] flex-wrap items-start gap-1.5">
          {Array.from(plugin.capabilities).map((cap) => {
            const formattedCap = formatCapabilityName(cap);
            const Icon = getCapabilityIcon(formattedCap);
            return (
              <span
                key={cap}
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-all duration-300 group-hover:scale-105 ${getCapabilityColor(
                  formattedCap,
                )}`}
              >
                <Icon className="h-3 w-3" />
                {formattedCap}
              </span>
            );
          })}
        </div>

        <div className="mt-auto">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="flex items-center">
                <Star className="mr-1 h-3.5 w-3.5 text-yellow-400" />
                <span className="text-sm font-medium text-white">
                  {plugin.rating_avg?.toFixed(1)}
                </span>
              </div>
              <div className="flex items-center text-gray-400">
                <Download className="mr-1 h-3.5 w-3.5" />
                <span className="text-sm">{formatInstalls(plugin.installs)}</span>
              </div>
            </div>
            <div className="inline-flex items-center justify-center rounded-md bg-[#2A3142] px-4 py-1.5 text-xs font-medium text-white transition-all duration-300 group-hover:scale-105 group-hover:bg-[#353D52]">
              Learn More
            </div>
          </div>
        </div>
      </div>
    </button>
  );
}

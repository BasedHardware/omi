'use client';

import { Brain, Cpu, Bell, Plug2, MessageSquare } from 'lucide-react';
import type { CapabilityInfo } from '../types';

export function CapabilityLegend() {
  const capabilities: Record<string, CapabilityInfo> = {
    'ai-powered': {
      icon: Brain,
      label: 'AI Powered',
      description: 'Uses artificial intelligence to enhance functionality',
    },
    memories: {
      icon: Cpu,
      label: 'Memories',
      description: 'Stores and processes conversation history',
    },
    notification: {
      icon: Bell,
      label: 'Notifications',
      description: 'Provides proactive notifications and alerts',
    },
    integration: {
      icon: Plug2,
      label: 'Integration',
      description: 'Connects with external services and tools',
    },
    chat: {
      icon: MessageSquare,
      label: 'Chat',
      description: 'Enables interactive chat functionality',
    },
  };

  return (
    <div className="mb-8">
      <div className="flex flex-wrap gap-4">
        {Object.entries(capabilities).map(([key, info]) => (
          <div
            key={key}
            className="group relative flex items-center gap-2 rounded-full bg-gray-800/50 px-3 py-1.5"
          >
            <info.icon className="h-4 w-4 text-gray-400" />
            <span className="text-sm text-gray-300">{info.label}</span>
            <div className="absolute -bottom-2 left-1/2 z-10 hidden -translate-x-1/2 translate-y-full rounded-lg bg-gray-800 p-2 text-sm text-gray-300 group-hover:block">
              <div className="relative">
                <div className="absolute -top-2 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 bg-gray-800"></div>
                {info.description}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

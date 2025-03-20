/* eslint-disable prettier/prettier */
import { Star, Download } from 'lucide-react';
import type { Plugin } from '../types';

interface AppStatsProps {
  plugin: Plugin;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function AppStats({ plugin, size = 'md', className = '' }: AppStatsProps) {
  const sizeClasses = {
    sm: {
      container: 'space-x-3',
      icon: 'h-3.5 w-3.5',
      text: 'text-sm',
    },
    md: {
      container: 'space-x-4',
      icon: 'h-4 w-4',
      text: 'text-base',
    },
    lg: {
      container: 'space-x-6',
      icon: 'h-5 w-5',
      text: 'text-lg',
    },
  };

  return (
    <div className={`flex items-center ${sizeClasses[size].container} text-gray-400 ${className}`}>
      <div className="flex items-center">
        <Star className={`mr-2 ${sizeClasses[size].icon} text-yellow-400`} />
        <span className={sizeClasses[size].text}>
          {(plugin.rating_avg ?? 0).toFixed(1)} ({plugin.rating_count})
        </span>
      </div>
      <span>•</span>
      <div className="flex items-center">
        <Download className={`mr-2 ${sizeClasses[size].icon}`} />
        <span className={sizeClasses[size].text}>
          {plugin.installs.toLocaleString()} installs
        </span>
      </div>
    </div>
  );
} 
'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Flame, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';

interface TaskProgressCardProps {
  overdueCount: number;
  todayTotal: number;
  todayCompleted: number;
  totalPending: number;
  totalCompleted: number;
  weekCompleted?: number;
  weekPending?: number;
  streak?: number;
  compact?: boolean;
}

export function TaskProgressCard({
  overdueCount,
  todayTotal,
  todayCompleted,
  totalPending,
  totalCompleted,
  weekCompleted = 0,
  weekPending = 0,
  streak = 0,
  compact = false,
}: TaskProgressCardProps) {
  const [animatedProgress, setAnimatedProgress] = useState(0);

  // Calculate completion percentage
  const total = totalPending + totalCompleted;
  const completionPercent = total > 0 ? Math.round((totalCompleted / total) * 100) : 0;

  // Weekly stats
  const weekTotal = weekCompleted + weekPending;
  const weekPercent = weekTotal > 0 ? Math.round((weekCompleted / weekTotal) * 100) : 0;

  // Animate progress on mount
  useEffect(() => {
    const timer = setTimeout(() => {
      setAnimatedProgress(completionPercent);
    }, 100);
    return () => clearTimeout(timer);
  }, [completionPercent]);

  // Get motivational message based on state
  const getMessage = () => {
    if (overdueCount > 0) {
      return "Let's tackle these first";
    }
    if (completionPercent === 100 && total > 0) {
      return 'All caught up!';
    }
    if (completionPercent >= 75) {
      return 'Almost there!';
    }
    if (completionPercent >= 50) {
      return "You're making progress!";
    }
    if (total === 0) {
      return 'No tasks yet';
    }
    return 'Ready to be productive?';
  };

  const message = getMessage();

  // SVG circle parameters
  const size = 72;
  const strokeWidth = 5;
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const strokeDashoffset = circumference - (animatedProgress / 100) * circumference;

  return (
    <div
      className={cn(
        'noise-overlay rounded-xl',
        'bg-white/[0.02] border border-white/[0.06]',
        compact ? 'flex flex-col' : 'grid grid-cols-2 gap-0'
      )}
    >
      {/* Left side - Progress Ring & Main Stats */}
      <div className={cn(
        "flex items-center gap-4 p-4",
        !compact && "border-r border-bg-tertiary"
      )}>
        {/* Progress Ring */}
        <div className="relative flex-shrink-0">
          <svg width={size} height={size} className="transform -rotate-90">
            {/* Background circle */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke="currentColor"
              strokeWidth={strokeWidth}
              className="text-bg-quaternary"
            />
            {/* Progress circle */}
            <motion.circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke="url(#progressGradient)"
              strokeWidth={strokeWidth}
              strokeLinecap="round"
              strokeDasharray={circumference}
              initial={{ strokeDashoffset: circumference }}
              animate={{ strokeDashoffset }}
              transition={{ duration: 0.8, ease: 'easeOut' }}
            />
            {/* Gradient definition */}
            <defs>
              <linearGradient id="progressGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#8B5CF6" />
                <stop offset="100%" stopColor="#A855F7" />
              </linearGradient>
            </defs>
          </svg>

          {/* Center text */}
          <div className="absolute inset-0 flex items-center justify-center">
            <motion.span
              className="text-base font-semibold text-text-primary"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
            >
              {animatedProgress}%
            </motion.span>
          </div>
        </div>

        {/* Stats */}
        <div className="flex-1 min-w-0">
          {/* Overdue badge */}
          {overdueCount > 0 && (
            <div className="mb-1.5">
              <span
                className={cn(
                  'px-2 py-0.5 rounded-md text-xs font-medium',
                  'bg-error/10 text-error'
                )}
              >
                {overdueCount} overdue
              </span>
            </div>
          )}

          <p className="text-sm text-text-secondary mb-1">{message}</p>

          {/* Counts */}
          <div className="flex items-center gap-3 text-xs text-text-quaternary">
            <span>{totalPending} pending</span>
            <span>{totalCompleted} completed</span>
          </div>
        </div>
      </div>

      {/* Right side - Weekly Stats & Streak */}
      <div className={cn(
        "flex flex-col justify-center p-4 gap-3",
        compact && "border-t border-bg-tertiary"
      )}>
        {/* This Week Progress */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-purple-primary" />
              <span className="text-xs font-medium text-text-secondary">This Week</span>
            </div>
            <span className="text-xs text-text-quaternary">{weekCompleted}/{weekTotal}</span>
          </div>
          <div className="h-2 bg-bg-quaternary rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-purple-primary to-purple-secondary rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${weekPercent}%` }}
              transition={{ duration: 0.6, delay: 0.2, ease: 'easeOut' }}
            />
          </div>
        </div>

        {/* Streak Counter */}
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded-lg',
              streak > 0 ? 'bg-orange-500/10' : 'bg-bg-quaternary'
            )}
          >
            <Flame
              className={cn(
                'w-4 h-4',
                streak > 0 ? 'text-orange-500' : 'text-text-quaternary'
              )}
            />
            <span
              className={cn(
                'text-sm font-medium',
                streak > 0 ? 'text-orange-500' : 'text-text-quaternary'
              )}
            >
              {streak}
            </span>
          </div>
          <span className="text-xs text-text-quaternary">
            {streak === 0
              ? 'Complete a task to start!'
              : streak === 1
              ? 'day streak'
              : 'day streak'}
          </span>
        </div>
      </div>
    </div>
  );
}

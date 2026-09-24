'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from '@tschk/moonshine-next/navigation';
import Image from '@tschk/moonshine-next/image';
import Link from '@tschk/moonshine-next/link';
import {
  User,
  Bell,
  Shield,
  Code,
  LogOut,
  Trash2,
  Globe,
  Clock,
  ChevronDown,
  Loader2,
  ExternalLink,
  Copy,
  Check,
  AlertTriangle,
  BarChart3,
  Puzzle,
  Plus,
  X,
  Key,
  Webhook,
  BookOpen,
  MessageSquare,
  Calendar,
  Github,
  Twitter,
  Settings,
  Brain,
  Server,
  Monitor,
  Download,
  Network,
  Mic,
  Radio,
  FileText,
  Lightbulb,
  ArrowLeft,
  Crown,
  ChevronRight,
  Zap,
  CreditCard,
  Scale,
} from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { useToast } from '@/components/ui/Toast';
import { cn } from '@/lib/utils';
import { DEFAULT_PLAN_FEATURES } from '@/lib/planFeatures';
import { PageHeader } from '@/components/layout/PageHeader';
import {
  CLAUDE_CONNECTOR_OAUTH,
  SECTION_INFO,
  SIGNED_OUT_DESTINATION,
  isSettingsSectionId,
  type SettingsSectionId,
} from '@/lib/settingsSections';
import {
  getUserLanguage,
  setUserLanguage,
  getDailySummarySettings,
  updateDailySummarySettings,
  getRecordingPermission,
  setRecordingPermission,
  getTrainingDataOptIn,
  setTrainingDataOptIn,
  deleteAccount,
  getAllUsageData,
  getUserSubscription,
  getCustomVocabulary,
  updateCustomVocabulary,
  getDeveloperWebhook,
  getDeveloperWebhooksStatus,
  setDeveloperWebhook,
  enableDeveloperWebhook,
  disableDeveloperWebhook,
  getDeveloperApiKeys,
  createDeveloperApiKey,
  deleteDeveloperApiKey,
  getMcpApiKeys,
  createMcpApiKey,
  deleteMcpApiKey,
  exportAllData,
  deleteKnowledgeGraph,
  getAvailablePlans,
  createCheckoutSession,
  upgradeSubscription,
  cancelSubscription,
  getCustomerPortal,
} from '@/lib/api';
import { SUPPORTED_LANGUAGES, API_KEY_SCOPES } from '@/types/user';
import { decodePlan, planGrantsPaidCapability } from '@/types/user';
import type {
  DailySummarySettings,
  UserUsage,
  UserSubscription,
  AllUsageData,
  DeveloperWebhooks,
  DeveloperApiKey,
  McpApiKey,
  UsageHistoryPoint,
  PricingOption,
} from '@/types/user';
import { clearRetiredExperimentalFeaturesStorage } from './retiredExperimentalFeatures';

// ============================================================================
// Types
// ============================================================================

type SettingsSection = SettingsSectionId;

// ============================================================================
// Reusable Components
// ============================================================================

function Toggle({
  enabled,
  onChange,
  disabled = false,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={cn(
        'relative h-6 w-11 flex-shrink-0 rounded-full transition-all duration-200',
        enabled
          ? 'bg-text-primary shadow-[0_0_12px_rgba(255,255,255,0.25)]'
          : 'bg-white/[0.08]',
        disabled && 'cursor-not-allowed opacity-50',
      )}
    >
      <div
        className={cn(
          'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-all duration-200',
          enabled ? 'left-[22px]' : 'left-0.5',
        )}
      />
    </button>
  );
}

function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-2xl p-5',
        // Layered background for depth instead of harsh border
        'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
        // Soft shadow stack
        'shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]',
        className,
      )}
    >
      {children}
    </div>
  );
}

function SettingRow({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between border-b border-white/[0.04] py-4 last:border-0">
      <div className="mr-4 min-w-0 flex-1">
        <p className="text-[15px] font-medium text-white/85">{label}</p>
        {description && (
          <p className="mt-0.5 text-[13px] leading-relaxed text-white/40">
            {description}
          </p>
        )}
      </div>
      {children}
    </div>
  );
}

function Dropdown({
  value,
  options,
  onChange,
  placeholder = 'Select...',
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectedOption = options.find((o) => o.value === value);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center justify-between gap-2 rounded-xl px-4 py-2.5',
          'bg-white/[0.04] ring-1 ring-white/[0.06]',
          'min-w-[160px] text-white/80',
          'transition-colors hover:bg-white/[0.06]',
        )}
      >
        <span className="truncate text-sm">{selectedOption?.label || placeholder}</span>
        <ChevronDown
          className={cn(
            'h-4 w-4 text-white/40 transition-transform',
            isOpen && 'rotate-180',
          )}
        />
      </button>

      {isOpen && (
        <div
          className={cn(
            'absolute z-50 mt-2 max-h-64 w-full overflow-y-auto rounded-xl py-1.5',
            'bg-[#1a1a1f]/95 backdrop-blur-xl',
            'shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_10px_30px_-5px_rgba(0,0,0,0.5)]',
          )}
        >
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
              className={cn(
                'flex w-full items-center justify-between px-4 py-2.5 text-left text-sm transition-colors',
                option.value === value
                  ? 'bg-white/[0.08] text-white'
                  : 'text-white/70 hover:bg-white/[0.04] hover:text-white/90',
              )}
            >
              <span>{option.label}</span>
              {option.value === value && (
                <Check className="h-4 w-4 text-text-secondary" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function HourPicker({
  value,
  onChange,
}: {
  value: number;
  onChange: (hour: number) => void;
}) {
  const hours = Array.from({ length: 24 }, (_, i) => {
    const hour = i;
    const period = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
    return {
      value: hour.toString(),
      label: `${displayHour}:00 ${period}`,
    };
  });

  return (
    <Dropdown
      value={value.toString()}
      options={hours}
      onChange={(v) => onChange(parseInt(v))}
      placeholder="Select time"
    />
  );
}

function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
  isDestructive = false,
  isLoading = false,
}: {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  isDestructive?: boolean;
  isLoading?: boolean;
}) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onCancel} />
      <div className="relative mx-4 w-full max-w-md rounded-2xl border border-white/[0.06] bg-bg-secondary p-6 shadow-2xl">
        <div className="mb-4 flex items-start gap-4">
          <div
            className={cn(
              'rounded-full p-2',
              isDestructive ? 'bg-red-500/10' : 'bg-white/[0.08]',
            )}
          >
            <AlertTriangle
              className={cn(
                'h-6 w-6',
                isDestructive ? 'text-red-400' : 'text-text-secondary',
              )}
            />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
            <p className="mt-1 text-text-secondary">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className={cn(
              'rounded-xl px-4 py-2 font-medium',
              'bg-bg-tertiary text-text-primary',
              'transition-colors hover:bg-bg-quaternary',
              'disabled:opacity-50',
            )}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className={cn(
              'flex items-center gap-2 rounded-xl px-4 py-2 font-medium',
              isDestructive
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-text-primary text-bg-primary hover:bg-text-primary/90',
              'transition-colors disabled:opacity-50',
            )}
          >
            {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Profile Section
// ============================================================================

function ProfileSection({
  user,
  onCopyUserId,
  language,
  vocabulary,
  onLanguageChange,
  onAddWord,
  onRemoveWord,
  dailySummary,
  onDailySummaryToggle,
  onDailySummaryHourChange,
}: {
  user: any;
  onCopyUserId: () => void;
  language: string;
  vocabulary: string[] | null;
  onLanguageChange: (lang: string) => void;
  onAddWord: (word: string) => void;
  onRemoveWord: (word: string) => void;
  dailySummary: DailySummarySettings | null;
  onDailySummaryToggle: (enabled: boolean) => void;
  onDailySummaryHourChange: (hour: number) => void;
}) {
  const [copiedUserId, setCopiedUserId] = useState(false);
  const [newWord, setNewWord] = useState('');

  const handleCopy = () => {
    onCopyUserId();
    setCopiedUserId(true);
    setTimeout(() => setCopiedUserId(false), 2000);
  };

  const words = vocabulary ?? [];

  const handleAddWord = () => {
    if (vocabulary !== null && newWord.trim()) {
      onAddWord(newWord.trim());
      setNewWord('');
    }
  };

  const languageOptions = SUPPORTED_LANGUAGES.map((l) => ({
    value: l.code,
    label: l.name,
  }));

  return (
    <div className="space-y-8">
      {/* Account Info */}
      <div id="account-info" className="scroll-mt-4 space-y-3">
        <h3 className="text-sm font-medium uppercase tracking-wider text-text-tertiary">
          Account
        </h3>
        <Card>
          <div className="flex items-center gap-5">
            <div className="h-20 w-20 flex-shrink-0 overflow-hidden rounded-full bg-bg-tertiary ring-2 ring-white/25">
              {user?.photoURL ? (
                <Image
                  src={user.photoURL}
                  alt={user.displayName || 'User'}
                  width={80}
                  height={80}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-2xl font-medium text-text-tertiary">
                  {user?.displayName?.charAt(0) || 'U'}
                </div>
              )}
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-lg font-semibold text-text-primary">
                {user?.displayName || 'User'}
              </h3>
              <p className="truncate text-text-tertiary">{user?.email}</p>
            </div>
          </div>
        </Card>

        <Card>
          <SettingRow label="User ID" description="Your unique identifier">
            <div className="flex items-center gap-2">
              <code className="rounded-lg bg-bg-tertiary px-3 py-1.5 font-mono text-sm text-text-tertiary">
                {user?.uid?.slice(0, 8)}...{user?.uid?.slice(-4)}
              </code>
              <button
                onClick={handleCopy}
                className={cn(
                  'rounded-lg p-2 transition-colors',
                  copiedUserId
                    ? 'bg-green-500/10 text-green-400'
                    : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary',
                )}
              >
                {copiedUserId ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </button>
            </div>
          </SettingRow>
        </Card>
      </div>

      {/* Language & Transcription */}
      <div id="language" className="scroll-mt-4 space-y-3">
        <h3 className="text-sm font-medium uppercase tracking-wider text-text-tertiary">
          Language & Transcription
        </h3>
        <Card>
          <SettingRow
            label="Primary Language"
            description="Default language for transcription"
          >
            <Dropdown
              value={language}
              options={languageOptions}
              onChange={onLanguageChange}
            />
          </SettingRow>
        </Card>
      </div>

      {/* Custom Vocabulary */}
      <div id="vocabulary" className="scroll-mt-4 space-y-3">
        <h3 className="text-sm font-medium uppercase tracking-wider text-text-tertiary">
          Custom Vocabulary
        </h3>
        <Card>
          <div className="space-y-4">
            <p className="text-sm text-text-tertiary">
              Add words or phrases to improve transcription accuracy
            </p>

            <div className="flex gap-2">
              <input
                type="text"
                value={newWord}
                onChange={(e) => setNewWord(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddWord()}
                placeholder="Enter a word or phrase"
                className={cn(
                  'flex-1 rounded-xl px-4 py-2.5',
                  'border border-white/[0.06] bg-bg-tertiary',
                  'text-text-primary placeholder:text-text-quaternary',
                  'focus:border-white/25 focus:outline-none',
                )}
              />
              <button
                onClick={handleAddWord}
                disabled={vocabulary === null || !newWord.trim()}
                className={cn(
                  'rounded-xl px-4 py-2.5 font-medium',
                  'bg-text-primary text-bg-primary',
                  'transition-colors hover:bg-text-primary/90',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              >
                <Plus className="h-5 w-5" />
              </button>
            </div>

            {words.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-2">
                {words.map((word) => (
                  <span
                    key={word}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-bg-tertiary px-3 py-1.5 text-sm text-text-secondary"
                  >
                    {word}
                    <button
                      onClick={() => onRemoveWord(word)}
                      className="text-text-quaternary transition-colors hover:text-red-400"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {vocabulary !== null && words.length === 0 && (
              <p className="py-4 text-center text-sm text-text-quaternary">
                No custom vocabulary added yet
              </p>
            )}
            {vocabulary === null && (
              <p className="py-4 text-center text-sm text-text-quaternary">
                Could not load your vocabulary
              </p>
            )}
          </div>
        </Card>
      </div>

      {/* Notifications */}
      <div id="notifications" className="scroll-mt-4 space-y-3">
        <h3 className="text-sm font-medium uppercase tracking-wider text-text-tertiary">
          Notifications
        </h3>
        <Card>
          <SettingRow
            label="Daily Summary"
            description={
              dailySummary === null
                ? 'Could not load your daily summary settings'
                : 'Receive a daily digest of your action items'
            }
          >
            <Toggle
              enabled={dailySummary?.enabled ?? false}
              onChange={onDailySummaryToggle}
              disabled={dailySummary === null}
            />
          </SettingRow>

          {dailySummary?.enabled && (
            <SettingRow
              label="Delivery Time"
              description="When to receive your daily summary"
            >
              <HourPicker value={dailySummary.hour} onChange={onDailySummaryHourChange} />
            </SettingRow>
          )}
        </Card>
      </div>
    </div>
  );
}

// ============================================================================
// Privacy Section
// ============================================================================

function PrivacySection({
  recordingPermission,
  trainingDataOptIn,
  onRecordingChange,
  onTrainingDataChange,
}: {
  recordingPermission: boolean;
  trainingDataOptIn: boolean;
  onRecordingChange: (enabled: boolean) => void;
  onTrainingDataChange: (enabled: boolean) => void;
}) {
  return (
    <div className="space-y-6">
      <Card>
        <SettingRow
          label="Store Recordings"
          description="Allow storing audio recordings for improved accuracy"
        >
          <Toggle enabled={recordingPermission} onChange={onRecordingChange} />
        </SettingRow>

        <SettingRow
          label="Training Data"
          description="Help improve Omi by contributing anonymous usage data"
        >
          <Toggle
            enabled={trainingDataOptIn}
            onChange={onTrainingDataChange}
            disabled={trainingDataOptIn}
          />
        </SettingRow>
      </Card>

      <Card className="border-white/25">
        <div className="flex items-start gap-4">
          <div className="rounded-lg bg-white/[0.08] p-2">
            <Shield className="h-5 w-5 text-text-secondary" />
          </div>
          <div>
            <h3 className="font-medium text-text-primary">Your Privacy Matters</h3>
            <p className="mt-1 text-sm text-text-tertiary">
              Your data is encrypted and never shared with third parties. You have full
              control over what data is collected and stored.
            </p>
            <a
              href="https://omi.me/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-flex items-center gap-1 text-sm text-text-secondary hover:underline"
            >
              Learn more about our privacy policy
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      </Card>
    </div>
  );
}

// ============================================================================
// Plan & Usage Section
// ============================================================================

type UsagePeriod = 'today' | 'monthly' | 'yearly' | 'all_time';

const PERIOD_LABELS: Record<UsagePeriod, string> = {
  today: 'Today',
  monthly: 'This Month',
  yearly: 'This Year',
  all_time: 'All Time',
};

function UsageChart({
  history,
  period,
}: {
  history?: UsageHistoryPoint[];
  period: UsagePeriod;
}) {
  const [selectedMetric, setSelectedMetric] = useState<
    'listening' | 'words' | 'insights' | 'memories'
  >('listening');

  if (!history || history.length === 0) {
    return (
      <Card className="flex h-48 items-center justify-center">
        <p className="text-text-quaternary">No activity data available</p>
      </Card>
    );
  }

  // For all_time with many data points, aggregate by year
  let dataToProcess = history;
  if (period === 'all_time' && history.length > 12) {
    // Group by year and aggregate
    const yearlyData = new Map<string, UsageHistoryPoint>();
    history.forEach((point) => {
      const date = new Date(point.date);
      const key = String(date.getFullYear());
      const existing = yearlyData.get(key);
      if (existing) {
        yearlyData.set(key, {
          date: `${key}-01-01`,
          transcription_seconds:
            existing.transcription_seconds + point.transcription_seconds,
          words_transcribed: existing.words_transcribed + point.words_transcribed,
          insights_gained: existing.insights_gained + point.insights_gained,
          memories_created: existing.memories_created + point.memories_created,
        });
      } else {
        yearlyData.set(key, { ...point, date: `${key}-01-01` });
      }
    });
    dataToProcess = Array.from(yearlyData.values()).sort((a, b) =>
      a.date.localeCompare(b.date),
    );
  }

  // Process history data for display
  const processedData = dataToProcess.map((point, index) => {
    // Parse date string - handles both "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SSZ" formats
    let label = '';

    if (period === 'today') {
      // For today, extract hour from ISO format "2026-01-02T00:00:00Z"
      const timeMatch = point.date.match(/T(\d{2}):/);
      const hour = timeMatch ? parseInt(timeMatch[1], 10) : 0;
      label = `${hour}:00`;
    } else {
      // For other periods, parse the date portion "YYYY-MM-DD"
      const datePart = point.date.split('T')[0]; // Get date part before 'T'
      const [year, month, day] = datePart.split('-').map(Number);

      if (period === 'monthly') {
        label = `${day}`;
      } else if (period === 'yearly') {
        label = [
          'Jan',
          'Feb',
          'Mar',
          'Apr',
          'May',
          'Jun',
          'Jul',
          'Aug',
          'Sep',
          'Oct',
          'Nov',
          'Dec',
        ][month - 1];
      } else {
        // For all_time, show year
        label = String(year);
      }
    }
    return { ...point, label, index };
  });

  // Get value based on selected metric
  const getValue = (d: UsageHistoryPoint) => {
    switch (selectedMetric) {
      case 'listening':
        return d.transcription_seconds / 60; // Convert to minutes
      case 'words':
        return d.words_transcribed;
      case 'insights':
        return d.insights_gained;
      case 'memories':
        return d.memories_created;
    }
  };

  // Format value for display
  const formatValue = (value: number) => {
    if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
    return Math.round(value).toLocaleString();
  };

  // Format value with unit
  const formatValueWithUnit = (value: number) => {
    const formatted = formatValue(value);
    switch (selectedMetric) {
      case 'listening':
        return `${formatted} min`;
      case 'words':
        return formatted;
      case 'insights':
        return formatted;
      case 'memories':
        return formatted;
    }
  };

  // Find max value for scaling
  const maxValue = Math.max(...processedData.map((d) => getValue(d)), 1);

  const metricConfig = [
    { key: 'listening' as const, color: 'rgb(96, 165, 250)', label: 'Listening' },
    { key: 'words' as const, color: 'rgb(74, 222, 128)', label: 'Words' },
    { key: 'insights' as const, color: 'rgb(251, 146, 60)', label: 'Insights' },
    { key: 'memories' as const, color: 'rgb(192, 132, 252)', label: 'Memories' },
  ];

  const currentMetric = metricConfig.find((m) => m.key === selectedMetric)!;

  return (
    <Card>
      {/* Header with metric selector */}
      <div className="mb-4 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-text-secondary">Activity Over Time</h4>
        <div className="flex gap-1">
          {metricConfig.map((metric) => (
            <button
              key={metric.key}
              onClick={() => setSelectedMetric(metric.key)}
              className={cn(
                'rounded-md px-2.5 py-1 text-xs font-medium transition-all',
                selectedMetric === metric.key
                  ? 'opacity-100'
                  : 'opacity-40 hover:opacity-60',
              )}
              style={{
                backgroundColor:
                  selectedMetric === metric.key ? `${metric.color}20` : 'transparent',
                color: metric.color,
              }}
            >
              {metric.label}
            </button>
          ))}
        </div>
      </div>

      {/* Bar Chart */}
      <div className="flex items-end gap-4 pt-2">
        {processedData.map((d, i) => {
          const value = getValue(d);
          // Calculate height in pixels (max 100px), with minimum 8px for visibility
          const maxBarHeight = 100;
          const barHeight = Math.max((value / maxValue) * maxBarHeight, 8);
          // Convert rgb(r,g,b) to rgba format for opacity
          const rgbMatch = currentMetric.color.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
          const rgba = rgbMatch
            ? `rgba(${rgbMatch[1]}, ${rgbMatch[2]}, ${rgbMatch[3]}, 0.5)`
            : currentMetric.color;
          return (
            <div key={i} className="flex flex-1 flex-col items-center">
              {/* Value on top */}
              <span
                className="mb-2 whitespace-nowrap text-xs font-bold"
                style={{ color: currentMetric.color }}
              >
                {formatValueWithUnit(value)}
              </span>
              {/* Bar with fixed pixel height */}
              <div
                className="w-full max-w-[80px] rounded-t-lg transition-all duration-300"
                style={{
                  height: `${barHeight}px`,
                  backgroundColor: rgba,
                }}
              />
              {/* Label */}
              <span className="mt-2 text-xs font-medium text-text-quaternary">
                {d.label}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

type PlanUsageTab = 'plan' | 'usage';

function UnknownPlanCard() {
  return (
    <Card>
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-white/[0.08]">
          <AlertTriangle className="h-5 w-5 text-text-secondary" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-text-primary">Plan unavailable</h3>
          <p className="mt-1 text-sm text-text-tertiary">
            This account uses a plan that this version of Omi does not recognize yet. Plan
            features are unavailable until the plan can be identified.
          </p>
        </div>
      </div>
    </Card>
  );
}

function UsageSectionContent({
  allUsage,
  subscription,
  onSubscriptionUpdate,
  cachedPlans,
}: {
  allUsage: AllUsageData | null;
  subscription: UserSubscription | null;
  onSubscriptionUpdate: () => void;
  cachedPlans: PricingOption[] | null;
}) {
  const [activeTab, setActiveTab] = useState<PlanUsageTab>('plan');
  const [selectedPeriod, setSelectedPeriod] = useState<UsagePeriod>('all_time');
  const [selectedPriceId, setSelectedPriceId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [isCanceling, setIsCanceling] = useState(false);
  const [showUpgradeOptions, setShowUpgradeOptions] = useState(false);

  // Set initial selected price when plans load, and keep it in sync when the
  // subscription's current price changes (e.g. after a plan change or
  // cancellation) so a pending-cancellation user isn't left on a stale option.
  const currentPriceId = subscription?.current_price_id;
  useEffect(() => {
    if (cachedPlans && cachedPlans.length > 0) {
      const activePlan = cachedPlans.find((p) => p.is_active || p.id === currentPriceId);
      if (activePlan) {
        setSelectedPriceId(activePlan.id);
      } else if (!selectedPriceId) {
        setSelectedPriceId(cachedPlans[0].id);
      }
    }
  }, [cachedPlans, currentPriceId]);

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
  };

  const formatNumber = (num: number) => {
    if (num >= 1000) {
      return `${(num / 1000).toFixed(1)}k`;
    }
    return num.toString();
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  // Get usage for selected period
  const usage = allUsage ? allUsage[selectedPeriod] : null;
  const monthlyUsage = allUsage?.monthly;
  const periods: UsagePeriod[] = ['today', 'monthly', 'yearly', 'all_time'];

  // Default limits for basic plan (1200 minutes = 72000 seconds)
  const limits = {
    transcription_seconds: 72000, // 1200 minutes
    words_transcribed: 50000,
    insights_gained: 100,
    memories_created: 50,
  };

  const planIdentity = subscription
    ? subscription.plan_identity ?? decodePlan(subscription.plan)
    : null;
  const isUnlimited = planIdentity ? planGrantsPaidCapability(planIdentity) : false;
  const isUnknownPlan = planIdentity?.kind === 'unknown';
  const isCancelingSubscription = subscription?.cancel_at_period_end;

  // Calculate usage percentages for basic plan
  const getUsagePercent = (used: number, limit: number) => {
    if (limit <= 0) return 0;
    return Math.min((used / limit) * 100, 100);
  };

  // Sort pricing options: monthly first, then annual
  const sortedOptions = cachedPlans
    ? [...cachedPlans].sort((a, b) => {
        const aIsAnnual =
          a.interval === 'year' || a.title?.toLowerCase().includes('annual');
        const bIsAnnual =
          b.interval === 'year' || b.title?.toLowerCase().includes('annual');
        return (aIsAnnual ? 1 : 0) - (bIsAnnual ? 1 : 0);
      })
    : [];

  const selectedOption = cachedPlans?.find((p) => p.id === selectedPriceId);

  const handleSubscribe = async () => {
    if (!selectedPriceId) return;

    setIsLoading(true);
    setError(null);

    try {
      const isCurrentPlan =
        selectedOption?.is_active ||
        selectedOption?.id === subscription?.current_price_id;

      if (isCancelingSubscription && selectedPriceId !== subscription?.current_price_id) {
        setError('Plan changes are available after your current subscription ends.');
        return;
      }

      if (isUnlimited && !isCancelingSubscription && !isCurrentPlan) {
        const result = await upgradeSubscription(selectedPriceId);
        if (result?.status === 'success' || result?.scheduled_start) {
          onSubscriptionUpdate();
        } else {
          setError(result?.message || 'Failed to upgrade plan');
        }
      } else {
        const result = await createCheckoutSession(selectedPriceId);
        if (result?.url) {
          window.open(result.url, '_blank');
          const handleFocus = () => {
            onSubscriptionUpdate();
            window.removeEventListener('focus', handleFocus);
          };
          window.addEventListener('focus', handleFocus);
        } else if (result?.status === 'reactivated') {
          onSubscriptionUpdate();
        } else {
          setError('Failed to create checkout session');
        }
      }
    } catch (err) {
      setError('An error occurred. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleManagePayment = async () => {
    setIsLoading(true);
    try {
      const result = await getCustomerPortal();
      if (result?.url) {
        window.open(result.url, '_blank');
        const handleFocus = () => {
          onSubscriptionUpdate();
          window.removeEventListener('focus', handleFocus);
        };
        window.addEventListener('focus', handleFocus);
      } else {
        setError('Failed to open payment portal');
      }
    } catch (err) {
      setError('Failed to open payment portal');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancelSubscription = async () => {
    setIsCanceling(true);
    try {
      const result = await cancelSubscription();
      if (result?.status === 'success' || result?.cancel_at_period_end) {
        onSubscriptionUpdate();
        setShowCancelConfirm(false);
      } else {
        setError(result?.message || 'Failed to cancel subscription');
      }
    } catch (err) {
      setError('Failed to cancel subscription');
    } finally {
      setIsCanceling(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Tab Switcher */}
      <div className="flex w-fit gap-1 rounded-xl bg-bg-tertiary p-1">
        <button
          onClick={() => setActiveTab('plan')}
          className={cn(
            'rounded-lg px-4 py-2 text-sm font-medium transition-all',
            activeTab === 'plan'
              ? 'bg-text-primary text-bg-primary shadow-md'
              : 'text-text-secondary hover:bg-bg-quaternary hover:text-text-primary',
          )}
        >
          Plan
        </button>
        <button
          onClick={() => setActiveTab('usage')}
          className={cn(
            'rounded-lg px-4 py-2 text-sm font-medium transition-all',
            activeTab === 'usage'
              ? 'bg-text-primary text-bg-primary shadow-md'
              : 'text-text-secondary hover:bg-bg-quaternary hover:text-text-primary',
          )}
        >
          Usage
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'plan' ? (
        /* PLAN TAB - Unknown plans remain neutral; known plans choose Basic vs paid. */
        <div className="space-y-6">
          {isUnknownPlan ? (
            <UnknownPlanCard />
          ) : !isUnlimited ? (
            /* BASIC PLAN VIEW */
            <>
              {/* Current Plan Card */}
              <Card className="relative overflow-hidden">
                {/* Header */}
                <div className="mb-6 flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/[0.08]">
                      <Zap className="h-6 w-6 text-text-secondary" />
                    </div>
                    <div>
                      <h3 className="text-xl font-semibold text-text-primary">
                        Basic Plan
                      </h3>
                      <p className="text-sm text-text-tertiary">Free tier</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setShowUpgradeOptions(true)}
                      className="rounded-xl bg-text-primary px-5 py-2.5 text-sm font-semibold text-bg-primary shadow-lg shadow-black/40 transition-all hover:bg-text-primary/90"
                    >
                      Upgrade to Unlimited
                    </button>
                    {subscription?.stripe_subscription_id && (
                      <button
                        onClick={handleManagePayment}
                        disabled={isLoading}
                        className="rounded-xl border border-bg-quaternary px-4 py-2.5 text-sm font-medium text-text-secondary transition-colors hover:text-text-primary disabled:opacity-50"
                      >
                        Billing &amp; Invoices
                      </button>
                    )}
                  </div>
                </div>

                {/* Monthly Listening Usage */}
                <div className="mb-6 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <Clock className="h-4 w-4 text-amber-400" />
                    <span className="text-sm font-semibold text-amber-400">
                      Monthly Listening Limit
                    </span>
                  </div>
                  <div className="mb-2 flex items-baseline justify-between">
                    <span className="text-2xl font-bold text-text-primary">
                      {monthlyUsage
                        ? Math.round(monthlyUsage.transcription_seconds / 60)
                        : 0}
                      <span className="ml-1 text-sm font-normal text-text-tertiary">
                        / 1,200 min
                      </span>
                    </span>
                    <span className="text-sm text-text-tertiary">
                      {monthlyUsage
                        ? 1200 - Math.round(monthlyUsage.transcription_seconds / 60)
                        : 1200}{' '}
                      min left
                    </span>
                  </div>
                  <div className="h-2.5 overflow-hidden rounded-full bg-bg-quaternary">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-amber-500 to-amber-400 transition-all duration-500"
                      style={{
                        width: `${
                          monthlyUsage
                            ? getUsagePercent(
                                monthlyUsage.transcription_seconds,
                                limits.transcription_seconds,
                              )
                            : 0
                        }%`,
                      }}
                    />
                  </div>
                </div>

                {/* What's Included - Checklist */}
                <div>
                  <h4 className="mb-3 text-sm font-semibold text-text-secondary">
                    What&apos;s included
                  </h4>
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded bg-amber-500/20">
                        <Clock className="h-3 w-3 text-amber-400" />
                      </div>
                      <span className="text-sm text-text-secondary">
                        <span className="font-medium text-text-primary">
                          1,200 minutes
                        </span>{' '}
                        of listening per month
                        <span className="ml-1 text-xs text-amber-400">(limited)</span>
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded bg-green-500/20">
                        <Check className="h-3 w-3 text-green-400" />
                      </div>
                      <span className="text-sm text-text-secondary">
                        <span className="font-medium text-text-primary">Unlimited</span>{' '}
                        words transcribed
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded bg-green-500/20">
                        <Check className="h-3 w-3 text-green-400" />
                      </div>
                      <span className="text-sm text-text-secondary">
                        <span className="font-medium text-text-primary">Unlimited</span>{' '}
                        insights
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded bg-green-500/20">
                        <Check className="h-3 w-3 text-green-400" />
                      </div>
                      <span className="text-sm text-text-secondary">
                        <span className="font-medium text-text-primary">Unlimited</span>{' '}
                        memories
                      </span>
                    </div>
                  </div>
                </div>
              </Card>

              {/* Billing error surfaced in the Basic view (not only the upgrade panel) */}
              {error && !showUpgradeOptions && (
                <div className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 p-3">
                  <AlertTriangle className="h-4 w-4 flex-shrink-0 text-red-400" />
                  <p className="text-sm text-red-400">{error}</p>
                </div>
              )}

              {/* Upgrade Options (shown when clicked) */}
              {showUpgradeOptions && (
                <Card className="border-white/25">
                  <div className="mb-5 flex items-center justify-between">
                    <div>
                      <h4 className="text-lg font-semibold text-text-primary">
                        Choose a Plan
                      </h4>
                      <p className="text-sm text-text-tertiary">
                        Unlock unlimited listening time
                      </p>
                    </div>
                    <button
                      onClick={() => setShowUpgradeOptions(false)}
                      className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
                    >
                      <X className="h-5 w-5 text-text-quaternary" />
                    </button>
                  </div>

                  {/* Plan Selection */}
                  {sortedOptions.length > 0 ? (
                    <div className="mb-5 grid grid-cols-2 gap-4">
                      {sortedOptions.map((option) => {
                        const isSelected = selectedPriceId === option.id;
                        const isAnnual =
                          option.interval === 'year' ||
                          option.title?.toLowerCase().includes('annual');

                        return (
                          <button
                            key={option.id}
                            onClick={() => setSelectedPriceId(option.id)}
                            className={cn(
                              'relative rounded-2xl border-2 p-5 text-left transition-all',
                              isSelected
                                ? 'border-white/25 bg-white/[0.08] shadow-lg shadow-black/40'
                                : 'border-bg-tertiary bg-bg-tertiary/30 hover:border-white/25',
                            )}
                          >
                            {isAnnual && (
                              <span className="absolute -top-2.5 right-3 rounded-full bg-text-primary px-3 py-1 text-[10px] font-bold uppercase tracking-wide text-bg-primary">
                                Best Value
                              </span>
                            )}
                            <h4 className="mb-1 font-semibold text-text-primary">
                              {option.title}
                            </h4>
                            <p className="text-2xl font-bold text-text-primary">
                              {option.price_string}
                            </p>
                            {option.description && (
                              <p className="mt-2 text-xs font-medium text-text-secondary">
                                {option.description}
                              </p>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="h-6 w-6 animate-spin text-text-primary" />
                    </div>
                  )}

                  {/* Error Message */}
                  {error && (
                    <div className="mb-4 flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 p-3">
                      <AlertTriangle className="h-4 w-4 flex-shrink-0 text-red-400" />
                      <p className="text-sm text-red-400">{error}</p>
                    </div>
                  )}

                  <button
                    onClick={handleSubscribe}
                    disabled={isLoading || !selectedPriceId}
                    className={cn(
                      'w-full rounded-xl py-3.5 font-semibold transition-all',
                      'bg-text-primary text-bg-primary',
                      'hover:bg-text-primary/90',
                      'shadow-lg shadow-black/40',
                      'disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none',
                    )}
                  >
                    {isLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Processing...
                      </span>
                    ) : (
                      'Continue to Payment'
                    )}
                  </button>
                </Card>
              )}

              {/* This Month Stats - Compact Single Row */}
              <Card>
                <h4 className="mb-4 text-sm font-semibold text-text-secondary">
                  This month
                </h4>
                <div className="grid grid-cols-4 gap-3">
                  <div className="text-center">
                    <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10">
                      <Mic className="h-5 w-5 text-blue-400" />
                    </div>
                    <p className="text-xl font-bold text-blue-400">
                      {monthlyUsage
                        ? formatDuration(monthlyUsage.transcription_seconds)
                        : '0m'}
                    </p>
                    <p className="text-xs text-text-quaternary">Listening</p>
                  </div>
                  <div className="text-center">
                    <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-green-500/10">
                      <MessageSquare className="h-5 w-5 text-green-400" />
                    </div>
                    <p className="text-xl font-bold text-green-400">
                      {monthlyUsage ? formatNumber(monthlyUsage.words_transcribed) : '0'}
                    </p>
                    <p className="text-xs text-text-quaternary">Words</p>
                  </div>
                  <div className="text-center">
                    <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-orange-500/10">
                      <Lightbulb className="h-5 w-5 text-orange-400" />
                    </div>
                    <p className="text-xl font-bold text-orange-400">
                      {monthlyUsage?.insights_gained || 0}
                    </p>
                    <p className="text-xs text-text-quaternary">Insights</p>
                  </div>
                  <div className="text-center">
                    <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-white/[0.08]">
                      <Brain className="h-5 w-5 text-text-secondary" />
                    </div>
                    <p className="text-xl font-bold text-text-secondary">
                      {monthlyUsage?.memories_created || 0}
                    </p>
                    <p className="text-xs text-text-quaternary">Memories</p>
                  </div>
                </div>
              </Card>
            </>
          ) : (
            /* UNLIMITED PLAN VIEW */
            <>
              {/* Header */}
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/[0.14]">
                  <Crown className="h-5 w-5 text-text-secondary" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-text-primary">
                    {isCancelingSubscription ? 'Your Plan' : 'Manage Your Plan'}
                  </h3>
                  {subscription?.current_period_end && (
                    <p className="text-xs text-text-quaternary">
                      {isCancelingSubscription
                        ? `Cancels on ${formatDate(subscription.current_period_end)}`
                        : `Renews ${formatDate(subscription.current_period_end)}`}
                    </p>
                  )}
                </div>
              </div>

              {/* Plan Selection */}
              {sortedOptions.length > 0 ? (
                <div className="grid grid-cols-2 gap-3">
                  {sortedOptions.map((option) => {
                    const isSelected = selectedPriceId === option.id;
                    const isCurrent =
                      option.is_active || option.id === subscription?.current_price_id;
                    const isAnnual =
                      option.interval === 'year' ||
                      option.title?.toLowerCase().includes('annual');

                    return (
                      <button
                        key={option.id}
                        onClick={() => setSelectedPriceId(option.id)}
                        disabled={isCancelingSubscription && !isCurrent}
                        className={cn(
                          'relative rounded-xl border-2 p-4 text-left transition-all',
                          isSelected
                            ? 'border-white/25 bg-white/[0.08]'
                            : 'border-bg-tertiary bg-bg-tertiary/50 hover:border-bg-quaternary',
                          isCancelingSubscription &&
                            !isCurrent &&
                            'cursor-not-allowed opacity-50',
                        )}
                      >
                        {isAnnual && (
                          <span className="absolute -top-2 right-2 rounded-full bg-text-primary px-2 py-0.5 text-[10px] font-medium text-bg-primary">
                            POPULAR
                          </span>
                        )}

                        <h4 className="mb-1 font-medium text-text-primary">
                          {option.title}
                        </h4>
                        <p className="text-lg font-bold text-text-primary">
                          {option.price_string}
                        </p>
                        {option.description && (
                          <p className="mt-1 text-xs text-text-secondary">
                            {option.description}
                          </p>
                        )}

                        {isCurrent && (
                          <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-green-500/10 px-2 py-0.5 text-xs text-green-400">
                            <Check className="h-3 w-3" />
                            Current
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-text-primary" />
                </div>
              )}

              {isCancelingSubscription && subscription?.current_period_end && (
                <p className="text-sm text-text-tertiary">
                  You can reactivate your current plan now. Plan changes are available
                  after {formatDate(subscription.current_period_end)}.
                </p>
              )}

              {/* Features List */}
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-text-secondary">Features:</h4>
                <ul className="space-y-2">
                  {DEFAULT_PLAN_FEATURES.map((feature, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-text-secondary" />
                      <span className="text-sm text-text-tertiary">{feature}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Error Message */}
              {error && (
                <div className="flex items-center gap-2 rounded-lg bg-red-500/10 p-3">
                  <AlertTriangle className="h-4 w-4 flex-shrink-0 text-red-400" />
                  <p className="text-sm text-red-400">{error}</p>
                </div>
              )}

              {/* Primary Action Button */}
              <button
                onClick={handleSubscribe}
                disabled={
                  isLoading ||
                  !selectedPriceId ||
                  (!isCancelingSubscription &&
                    (selectedOption?.is_active ||
                      selectedOption?.id === subscription?.current_price_id)) ||
                  (isCancelingSubscription &&
                    selectedPriceId !== subscription?.current_price_id)
                }
                className={cn(
                  'w-full rounded-xl py-3 font-medium transition-colors',
                  'bg-text-primary text-bg-primary',
                  'hover:bg-text-primary/90',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              >
                {isLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Processing...
                  </span>
                ) : isCancelingSubscription ? (
                  'Reactivate Subscription'
                ) : selectedOption?.is_active ||
                  selectedOption?.id === subscription?.current_price_id ? (
                  'Current Plan'
                ) : (
                  'Change Plan'
                )}
              </button>

              {/* Secondary Actions */}
              <div className="space-y-3 border-t border-bg-tertiary pt-4">
                <button
                  onClick={handleManagePayment}
                  disabled={isLoading}
                  className="flex w-full items-center justify-center gap-2 py-2.5 text-text-secondary transition-colors hover:text-text-primary"
                >
                  <CreditCard className="h-4 w-4" />
                  <span className="text-sm">Manage Billing &amp; Invoices</span>
                </button>

                {!isCancelingSubscription && (
                  <button
                    onClick={() => setShowCancelConfirm(true)}
                    disabled={isLoading}
                    className="w-full py-2.5 text-sm text-red-400/70 transition-colors hover:text-red-400"
                  >
                    Cancel Subscription
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      ) : (
        /* USAGE TAB */
        <div className="space-y-6">
          {/* Period Tabs */}
          <div className="flex gap-1 rounded-xl bg-bg-tertiary p-1">
            {periods.map((period) => (
              <button
                key={period}
                onClick={() => setSelectedPeriod(period)}
                className={cn(
                  'flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-all',
                  selectedPeriod === period
                    ? 'bg-text-primary text-bg-primary shadow-md'
                    : 'text-text-secondary hover:bg-bg-quaternary hover:text-text-primary',
                )}
              >
                {PERIOD_LABELS[period]}
              </button>
            ))}
          </div>

          {/* Stats Summary - Compact Single Row */}
          <Card>
            <div className="grid grid-cols-4 gap-3">
              <div className="text-center">
                <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10">
                  <Mic className="h-5 w-5 text-blue-400" />
                </div>
                <p className="text-xl font-bold text-blue-400">
                  {usage ? formatDuration(usage.transcription_seconds) : '0m'}
                </p>
                <p className="text-xs text-text-quaternary">Listening</p>
              </div>
              <div className="text-center">
                <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-green-500/10">
                  <MessageSquare className="h-5 w-5 text-green-400" />
                </div>
                <p className="text-xl font-bold text-green-400">
                  {usage ? formatNumber(usage.words_transcribed) : '0'}
                </p>
                <p className="text-xs text-text-quaternary">Words</p>
              </div>
              <div className="text-center">
                <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-orange-500/10">
                  <Lightbulb className="h-5 w-5 text-orange-400" />
                </div>
                <p className="text-xl font-bold text-orange-400">
                  {usage?.insights_gained || 0}
                </p>
                <p className="text-xs text-text-quaternary">Insights</p>
              </div>
              <div className="text-center">
                <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-white/[0.08]">
                  <Brain className="h-5 w-5 text-text-secondary" />
                </div>
                <p className="text-xl font-bold text-text-secondary">
                  {usage?.memories_created || 0}
                </p>
                <p className="text-xs text-text-quaternary">Memories</p>
              </div>
            </div>
          </Card>

          {/* Usage Trends Chart */}
          <UsageChart history={usage?.history} period={selectedPeriod} />
        </div>
      )}

      {/* Cancel Subscription Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showCancelConfirm}
        title="Cancel Subscription?"
        message={
          subscription?.current_period_end
            ? `Your subscription will remain active until ${formatDate(
                subscription.current_period_end,
              )}. After that, you'll be moved to the Free plan.`
            : "Are you sure you want to cancel your subscription? You'll lose access to unlimited features."
        }
        confirmLabel="Cancel Subscription"
        onConfirm={handleCancelSubscription}
        onCancel={() => setShowCancelConfirm(false)}
        isDestructive={true}
        isLoading={isCanceling}
      />
    </div>
  );
}

// ============================================================================
// Developer Section
// ============================================================================

// Create API Key Dialog
function CreateApiKeyDialog({
  isOpen,
  onClose,
  onCreateKey,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreateKey: (name: string, scopes: string[]) => Promise<DeveloperApiKey | null>;
}) {
  const [keyName, setKeyName] = useState('');
  const [scopes, setScopes] = useState<Record<string, boolean>>({
    'conversations:read': false,
    'conversations:write': false,
    'memories:read': false,
    'memories:write': false,
    'action_items:read': false,
    'action_items:write': false,
  });
  const [isCreating, setIsCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<DeveloperApiKey | null>(null);
  const [copied, setCopied] = useState(false);

  const selectedScopes = Object.entries(scopes)
    .filter(([, v]) => v)
    .map(([k]) => k);
  const isReadOnly =
    scopes['conversations:read'] &&
    scopes['memories:read'] &&
    scopes['action_items:read'] &&
    !scopes['conversations:write'] &&
    !scopes['memories:write'] &&
    !scopes['action_items:write'];
  const isFullAccess = Object.values(scopes).every((v) => v);

  const selectReadOnly = () => {
    setScopes({
      'conversations:read': true,
      'conversations:write': false,
      'memories:read': true,
      'memories:write': false,
      'action_items:read': true,
      'action_items:write': false,
    });
  };

  const selectFullAccess = () => {
    setScopes(Object.fromEntries(Object.keys(scopes).map((k) => [k, true])));
  };

  const handleCreate = async () => {
    if (!keyName.trim()) return;
    setIsCreating(true);
    const key = await onCreateKey(
      keyName.trim(),
      selectedScopes.length > 0 ? selectedScopes : (undefined as unknown as string[]),
    );
    if (key) {
      setCreatedKey(key);
    }
    setIsCreating(false);
  };

  const handleCopy = () => {
    if (createdKey?.key) {
      navigator.clipboard.writeText(createdKey.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleClose = () => {
    setKeyName('');
    setScopes(Object.fromEntries(Object.keys(scopes).map((k) => [k, false])));
    setCreatedKey(null);
    setCopied(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={handleClose}
    >
      <div
        className="mx-4 w-full max-w-md overflow-hidden rounded-2xl bg-bg-secondary"
        onClick={(e) => e.stopPropagation()}
      >
        {createdKey ? (
          <div className="p-6">
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-xl bg-green-500/20 p-3">
                <Check className="h-6 w-6 text-green-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text-primary">
                  API Key Created
                </h3>
                <p className="text-sm text-text-tertiary">
                  Save this key now - you won&apos;t see it again!
                </p>
              </div>
            </div>
            <div className="mb-4 rounded-xl bg-bg-tertiary p-4">
              <p className="mb-2 text-xs text-text-tertiary">Your API Key</p>
              <code className="break-all font-mono text-sm text-text-primary">
                {createdKey.key}
              </code>
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleCopy}
                className={cn(
                  'flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-3 font-medium transition-colors',
                  copied
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-text-primary text-bg-primary hover:bg-text-primary/90',
                )}
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copied ? 'Copied!' : 'Copy Key'}
              </button>
              <button
                onClick={handleClose}
                className="rounded-xl bg-bg-tertiary px-4 py-3 text-text-secondary transition-colors hover:bg-bg-quaternary"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="p-6">
            <div className="mb-6 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-text-primary">Create API Key</h3>
              <button
                onClick={handleClose}
                className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
              >
                <X className="h-5 w-5 text-text-tertiary" />
              </button>
            </div>

            <div className="space-y-6">
              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                  Key Name
                </label>
                <input
                  type="text"
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  placeholder="e.g., My App Integration"
                  className="w-full rounded-xl border border-white/[0.06] bg-bg-tertiary px-4 py-3 text-text-primary placeholder:text-text-quaternary focus:border-white/25 focus:outline-none"
                />
              </div>

              <div>
                <div className="mb-3 flex items-center justify-between">
                  <label className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                    Permissions
                  </label>
                  <div className="flex gap-2">
                    <button
                      onClick={selectReadOnly}
                      className={cn(
                        'rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
                        isReadOnly
                          ? 'bg-text-primary text-bg-primary'
                          : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary',
                      )}
                    >
                      Read Only
                    </button>
                    <button
                      onClick={selectFullAccess}
                      className={cn(
                        'rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
                        isFullAccess
                          ? 'bg-text-primary text-bg-primary'
                          : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary',
                      )}
                    >
                      Full Access
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  {['Conversations', 'Memories', 'Action Items'].map((resource) => {
                    const readKey = `${resource.toLowerCase().replace(' ', '_')}:read`;
                    const writeKey = `${resource.toLowerCase().replace(' ', '_')}:write`;
                    return (
                      <div
                        key={resource}
                        className="flex items-center justify-between rounded-xl bg-bg-tertiary p-3"
                      >
                        <span className="text-sm text-text-primary">{resource}</span>
                        <div className="flex overflow-hidden rounded-lg bg-bg-quaternary">
                          <button
                            onClick={() =>
                              setScopes({ ...scopes, [readKey]: !scopes[readKey] })
                            }
                            className={cn(
                              'px-3 py-1.5 text-xs font-semibold transition-colors',
                              scopes[readKey]
                                ? 'bg-blue-500 text-white'
                                : 'text-text-quaternary hover:text-text-secondary',
                            )}
                          >
                            R
                          </button>
                          <button
                            onClick={() =>
                              setScopes({ ...scopes, [writeKey]: !scopes[writeKey] })
                            }
                            className={cn(
                              'px-3 py-1.5 text-xs font-semibold transition-colors',
                              scopes[writeKey]
                                ? 'bg-text-primary text-bg-primary'
                                : 'text-text-quaternary hover:text-text-secondary',
                            )}
                          >
                            W
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <p className="mt-2 text-xs text-text-quaternary">
                  R = Read, W = Write. Defaults to read-only if nothing selected.
                </p>
              </div>

              <button
                onClick={handleCreate}
                disabled={!keyName.trim() || isCreating}
                className={cn(
                  'w-full rounded-xl py-3 font-medium transition-colors',
                  keyName.trim() && !isCreating
                    ? 'bg-text-primary text-bg-primary hover:bg-text-primary/90'
                    : 'cursor-not-allowed bg-bg-tertiary text-text-quaternary',
                )}
              >
                {isCreating ? 'Creating...' : 'Create Key'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Create MCP Key Dialog
function CreateMcpKeyDialog({
  isOpen,
  onClose,
  onCreateKey,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreateKey: (name: string) => Promise<McpApiKey | null>;
}) {
  const [keyName, setKeyName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<McpApiKey | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCreate = async () => {
    if (!keyName.trim()) return;
    setIsCreating(true);
    const key = await onCreateKey(keyName.trim());
    if (key) {
      setCreatedKey(key);
    }
    setIsCreating(false);
  };

  const handleCopy = () => {
    if (createdKey?.key) {
      navigator.clipboard.writeText(createdKey.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleClose = () => {
    setKeyName('');
    setCreatedKey(null);
    setCopied(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={handleClose}
    >
      <div
        className="mx-4 w-full max-w-md overflow-hidden rounded-2xl bg-bg-secondary"
        onClick={(e) => e.stopPropagation()}
      >
        {createdKey ? (
          <div className="p-6">
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-xl bg-green-500/20 p-3">
                <Check className="h-6 w-6 text-green-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text-primary">
                  MCP Key Created
                </h3>
                <p className="text-sm text-text-tertiary">
                  Save this key now - you won&apos;t see it again!
                </p>
              </div>
            </div>
            <div className="mb-4 rounded-xl bg-bg-tertiary p-4">
              <p className="mb-2 text-xs text-text-tertiary">Your MCP Key</p>
              <code className="break-all font-mono text-sm text-text-primary">
                {createdKey.key}
              </code>
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleCopy}
                className={cn(
                  'flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-3 font-medium transition-colors',
                  copied
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-text-primary text-bg-primary hover:bg-text-primary/90',
                )}
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copied ? 'Copied!' : 'Copy Key'}
              </button>
              <button
                onClick={handleClose}
                className="rounded-xl bg-bg-tertiary px-4 py-3 text-text-secondary transition-colors hover:bg-bg-quaternary"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="p-6">
            <div className="mb-6 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-text-primary">Create MCP Key</h3>
              <button
                onClick={handleClose}
                className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
              >
                <X className="h-5 w-5 text-text-tertiary" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                  Key Name
                </label>
                <input
                  type="text"
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  placeholder="e.g., Claude Desktop"
                  className="w-full rounded-xl border border-white/[0.06] bg-bg-tertiary px-4 py-3 text-text-primary placeholder:text-text-quaternary focus:border-white/25 focus:outline-none"
                />
              </div>
              <button
                onClick={handleCreate}
                disabled={!keyName.trim() || isCreating}
                className={cn(
                  'w-full rounded-xl py-3 font-medium transition-colors',
                  keyName.trim() && !isCreating
                    ? 'bg-text-primary text-bg-primary hover:bg-text-primary/90'
                    : 'cursor-not-allowed bg-bg-tertiary text-text-quaternary',
                )}
              >
                {isCreating ? 'Creating...' : 'Create Key'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DeveloperSection({
  apiKeys,
  mcpKeys,
  webhooks,
  onCreateApiKey,
  onDeleteApiKey,
  onCreateMcpKey,
  onDeleteMcpKey,
  onWebhookChange,
  onExportData,
  isExporting,
  onDeleteKnowledgeGraph,
}: {
  apiKeys: DeveloperApiKey[];
  mcpKeys: McpApiKey[];
  webhooks: DeveloperWebhooks;
  onCreateApiKey: (name: string, scopes: string[]) => Promise<DeveloperApiKey | null>;
  onDeleteApiKey: (keyId: string) => void;
  onCreateMcpKey: (name: string) => Promise<McpApiKey | null>;
  onDeleteMcpKey: (keyId: string) => void;
  onWebhookChange: (type: string, enabled: boolean, url?: string, delay?: string) => void;
  onExportData: () => void;
  isExporting?: boolean;
  onDeleteKnowledgeGraph: () => void;
}) {
  const [showApiKeyDialog, setShowApiKeyDialog] = useState(false);
  const [showMcpKeyDialog, setShowMcpKeyDialog] = useState(false);
  const [showDeleteGraphDialog, setShowDeleteGraphDialog] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedClaudeName, setCopiedClaudeName] = useState(false);
  const [copiedClaudeUrl, setCopiedClaudeUrl] = useState(false);
  const [copiedClaudeClientId, setCopiedClaudeClientId] = useState(false);
  const [copiedClaudeSecret, setCopiedClaudeSecret] = useState(false);

  const mcpServerUrl = `${
    process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me'
  }/v1/mcp/sse`;

  // Claude connector values — mirror the 4 fields in Claude's "Add custom connector" form
  const claudeConnectorName = 'Omi Memory';
  const claudeConnectorUrl = mcpServerUrl;
  const claudeConnectorClientId = CLAUDE_CONNECTOR_OAUTH.clientId;
  const claudeConnectorSecret: string = CLAUDE_CONNECTOR_OAUTH.clientSecret;

  // Parse audio_bytes URL which may contain comma-separated URL and delay (e.g., "https://example.com,5")
  const parseAudioBytesUrl = (rawUrl: string) => {
    if (!rawUrl) return { url: '', delay: '5' };
    const parts = rawUrl.split(',');
    if (parts.length >= 2) {
      return { url: parts[0], delay: parts[1] };
    }
    return { url: rawUrl, delay: '5' };
  };

  const initialAudioBytes = parseAudioBytesUrl(webhooks.audio_bytes?.url || '');

  const [webhookUrls, setWebhookUrls] = useState<Record<string, string>>({
    memory_created: webhooks.memory_created?.url || '',
    transcript_received: webhooks.transcript_received?.url || '',
    audio_bytes: initialAudioBytes.url,
    day_summary: webhooks.day_summary?.url || '',
  });
  const [audioBytesDelay, setAudioBytesDelay] = useState(initialAudioBytes.delay);

  // Update webhook URLs when webhooks prop changes
  useEffect(() => {
    const audioBytes = parseAudioBytesUrl(webhooks.audio_bytes?.url || '');
    setWebhookUrls({
      memory_created: webhooks.memory_created?.url || '',
      transcript_received: webhooks.transcript_received?.url || '',
      audio_bytes: audioBytes.url,
      day_summary: webhooks.day_summary?.url || '',
    });
    setAudioBytesDelay(audioBytes.delay);
  }, [webhooks]);

  const webhookTypes = [
    {
      id: 'memory_created',
      label: 'Conversation Events',
      description: 'New conversation created',
      icon: MessageSquare,
    },
    {
      id: 'transcript_received',
      label: 'Real-time Transcript',
      description: 'Transcript received',
      icon: FileText,
    },
    {
      id: 'audio_bytes',
      label: 'Audio Bytes',
      description: 'Audio data received',
      icon: Radio,
      hasDelay: true,
    },
    {
      id: 'day_summary',
      label: 'Day Summary',
      description: 'Summary generated',
      icon: Calendar,
    },
  ];

  const claudeDesktopConfig = `{
  "mcpServers": {
    "omi": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "-e", "OMI_API_KEY=your_api_key_here", "omiai/mcp-server:latest"]
    }
  }
}`;

  const copyConfig = () => {
    navigator.clipboard.writeText(claudeDesktopConfig);
    setCopiedConfig(true);
    setTimeout(() => setCopiedConfig(false), 2000);
  };

  const copyUrl = () => {
    navigator.clipboard.writeText(mcpServerUrl);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2000);
  };

  return (
    <div className="space-y-8">
      {/* Developer API Keys */}
      <div id="api-keys" className="scroll-mt-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-text-tertiary">
            Developer API Keys
          </h3>
          <button
            onClick={() => setShowApiKeyDialog(true)}
            className="flex items-center gap-1.5 rounded-full bg-white/[0.08] px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-white/[0.14]"
          >
            <Plus className="h-3 w-3" />
            Create Key
          </button>
        </div>
        <Card>
          {apiKeys.length > 0 ? (
            <div className="space-y-3">
              {apiKeys.map((apiKey) => (
                <div
                  key={apiKey.id}
                  className="flex items-center justify-between rounded-xl bg-bg-tertiary p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-text-primary">
                        {apiKey.name}
                      </span>
                      <code className="rounded bg-bg-quaternary px-2 py-0.5 font-mono text-xs text-text-tertiary">
                        {apiKey.key_prefix}...
                      </code>
                      {apiKey.scopes && apiKey.scopes.length > 0 && (
                        <span className="rounded bg-white/[0.08] px-2 py-0.5 text-xs text-text-secondary">
                          {apiKey.scopes.length} scopes
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-text-quaternary">
                      Created {new Date(apiKey.created_at).toLocaleDateString()}
                      {apiKey.last_used_at &&
                        ` • Last used ${new Date(
                          apiKey.last_used_at,
                        ).toLocaleDateString()}`}
                    </p>
                  </div>
                  <button
                    onClick={() => onDeleteApiKey(apiKey.id)}
                    className="rounded-lg p-2 text-text-secondary transition-colors hover:bg-red-500/10 hover:text-red-400"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-text-quaternary">
              No API keys created yet
            </p>
          )}
        </Card>
      </div>

      {/* MCP Section */}
      <div id="mcp" className="scroll-mt-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-text-tertiary">
              MCP
            </h3>
            <a
              href="https://docs.omi.me/doc/developer/MCP"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-text-secondary transition-colors hover:text-text-secondary"
            >
              Docs ↗
            </a>
          </div>
          <button
            onClick={() => setShowMcpKeyDialog(true)}
            className="flex items-center gap-1.5 rounded-full bg-white/[0.08] px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-white/[0.14]"
          >
            <Plus className="h-3 w-3" />
            Create Key
          </button>
        </div>

        {/* MCP Keys List */}
        <Card>
          {mcpKeys.length > 0 ? (
            <div className="space-y-3">
              {mcpKeys.map((key) => (
                <div
                  key={key.id}
                  className="flex items-center justify-between rounded-xl bg-bg-tertiary p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-text-primary">
                        {key.name}
                      </span>
                      <code className="rounded bg-bg-quaternary px-2 py-0.5 font-mono text-xs text-text-tertiary">
                        {key.key_prefix}...
                      </code>
                    </div>
                    <p className="mt-1 text-xs text-text-quaternary">
                      Created {new Date(key.created_at).toLocaleDateString()}
                      {key.last_used_at &&
                        ` • Last used ${new Date(key.last_used_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  <button
                    onClick={() => onDeleteMcpKey(key.id)}
                    className="rounded-lg p-2 text-text-secondary transition-colors hover:bg-red-500/10 hover:text-red-400"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-text-quaternary">
              No MCP keys created yet
            </p>
          )}
        </Card>

        {/* Claude Desktop Config */}
        <Card>
          <div className="mb-4 flex items-center gap-3">
            <div className="rounded-lg bg-bg-tertiary p-2">
              <Monitor className="h-5 w-5 text-text-tertiary" />
            </div>
            <div>
              <p className="font-medium text-text-primary">Claude Desktop</p>
              <p className="text-xs text-text-tertiary">
                Add to claude_desktop_config.json
              </p>
            </div>
          </div>
          <div className="overflow-x-auto rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-4 font-mono text-xs">
            <pre className="whitespace-pre text-text-secondary">
              {claudeDesktopConfig}
            </pre>
          </div>
          <button
            onClick={copyConfig}
            className={cn(
              'mt-3 flex w-full items-center justify-center gap-2 rounded-xl py-2.5 transition-colors',
              copiedConfig
                ? 'bg-green-500/20 text-green-400'
                : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary',
            )}
          >
            {copiedConfig ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copiedConfig ? 'Copied!' : 'Copy Config'}
          </button>
        </Card>

        {/* Generic MCP Server Info */}
        <Card>
          <div className="mb-4 flex items-center gap-3">
            <div className="rounded-lg bg-bg-tertiary p-2">
              <Server className="h-5 w-5 text-text-tertiary" />
            </div>
            <div>
              <p className="font-medium text-text-primary">MCP Server</p>
              <p className="text-xs text-text-tertiary">
                Connect ChatGPT, Codex, Claude, or any MCP client to your data
              </p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                Server URL
              </p>
              <button
                onClick={copyUrl}
                className="flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 transition-colors hover:border-white/25"
              >
                <code className="mr-2 truncate font-mono text-sm text-text-primary">
                  {mcpServerUrl}
                </code>
                {copiedUrl ? (
                  <Check className="h-4 w-4 flex-shrink-0 text-green-400" />
                ) : (
                  <Copy className="h-4 w-4 flex-shrink-0 text-text-quaternary" />
                )}
              </button>
            </div>

            <div className="border-t border-white/[0.06] pt-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                API Key Auth
              </p>
              <div className="flex items-center gap-4 text-sm">
                <span className="text-text-tertiary">Header</span>
                <code className="font-mono text-xs text-text-quaternary">
                  Authorization: Bearer &lt;key&gt;
                </code>
              </div>
            </div>

            <div className="border-t border-white/[0.06] pt-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                OAuth
              </p>
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-4">
                  <span className="w-24 text-text-tertiary">Client ID</span>
                  <code className="font-mono text-text-primary">omi</code>
                </div>
                <div className="flex items-center gap-4">
                  <span className="w-24 text-text-tertiary">Client Secret</span>
                  <span className="text-xs italic text-text-quaternary">
                    Use your MCP API key
                  </span>
                </div>
              </div>
            </div>
          </div>
        </Card>

        {/* Claude Connector — 4 copy fields mirroring Claude's "Add custom connector" form */}
        <Card>
          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl border border-orange-500/20 bg-gradient-to-br from-orange-500/20 to-orange-600/10">
              <span className="text-lg font-semibold text-orange-400">C</span>
            </div>
            <div>
              <p className="font-medium text-text-primary">Claude</p>
              <p className="text-xs text-text-tertiary">Live MCP or memory pack</p>
            </div>
          </div>

          <p className="mb-4 text-sm text-text-secondary">
            Connect over MCP so Claude reads your memories live, or copy a memory pack.
            Each field below maps to Claude&rsquo;s{' '}
            <span className="text-text-tertiary">
              Settings → Connectors → Add custom connector
            </span>{' '}
            form.
          </p>

          <div className="space-y-3">
            {/* Field 1: Name → pastes into Claude's "Name" input */}
            <div>
              <p className="mb-1.5 text-xs font-medium text-text-tertiary">
                1. Name{' '}
                <span className="font-normal text-text-secondary">
                  → Claude &quot;Name&quot;
                </span>
              </p>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(claudeConnectorName);
                  setCopiedClaudeName(true);
                  setTimeout(() => setCopiedClaudeName(false), 2000);
                }}
                className="group flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 transition-colors hover:border-white/25"
              >
                <code className="font-mono text-sm text-text-primary">
                  {claudeConnectorName}
                </code>
                {copiedClaudeName ? (
                  <Check className="h-4 w-4 text-green-400" />
                ) : (
                  <Copy className="h-4 w-4 text-text-quaternary transition-colors group-hover:text-text-secondary" />
                )}
              </button>
            </div>

            {/* Field 2: Server URL → pastes into Claude's "Remote MCP server URL" input */}
            <div>
              <p className="mb-1.5 text-xs font-medium text-text-tertiary">
                2. Remote MCP server URL{' '}
                <span className="font-normal text-text-secondary">
                  → Claude &quot;Remote MCP server URL&quot;
                </span>
              </p>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(claudeConnectorUrl);
                  setCopiedClaudeUrl(true);
                  setTimeout(() => setCopiedClaudeUrl(false), 2000);
                }}
                className="group flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 transition-colors hover:border-white/25"
              >
                <code className="mr-2 truncate font-mono text-sm text-text-primary">
                  {claudeConnectorUrl}
                </code>
                {copiedClaudeUrl ? (
                  <Check className="h-4 w-4 flex-shrink-0 text-green-400" />
                ) : (
                  <Copy className="h-4 w-4 flex-shrink-0 text-text-quaternary transition-colors group-hover:text-text-secondary" />
                )}
              </button>
            </div>

            {/* Field 3: OAuth Client ID → pastes into Claude's Advanced "OAuth Client ID" */}
            <div>
              <p className="mb-1.5 text-xs font-medium text-text-tertiary">
                3. OAuth Client ID{' '}
                <span className="font-normal text-text-secondary">
                  → Claude Advanced &quot;OAuth Client ID&quot;
                </span>
              </p>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(claudeConnectorClientId);
                  setCopiedClaudeClientId(true);
                  setTimeout(() => setCopiedClaudeClientId(false), 2000);
                }}
                className="group flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 transition-colors hover:border-white/25"
              >
                <code className="font-mono text-sm text-text-primary">
                  {claudeConnectorClientId}
                </code>
                {copiedClaudeClientId ? (
                  <Check className="h-4 w-4 text-green-400" />
                ) : (
                  <Copy className="h-4 w-4 text-text-quaternary transition-colors group-hover:text-text-secondary" />
                )}
              </button>
            </div>

            {/* Field 4: OAuth Client Secret → pastes into Claude's Advanced "OAuth Client Secret" */}
            <div>
              <p className="mb-1.5 text-xs font-medium text-text-tertiary">
                4. OAuth Client Secret{' '}
                <span className="font-normal text-text-secondary">
                  → Claude Advanced &quot;OAuth Client Secret&quot;
                </span>
              </p>
              {claudeConnectorSecret ? (
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(claudeConnectorSecret);
                    setCopiedClaudeSecret(true);
                    setTimeout(() => setCopiedClaudeSecret(false), 2000);
                  }}
                  className="group flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 transition-colors hover:border-white/25"
                >
                  <code className="mr-2 truncate font-mono text-sm text-text-primary">
                    {claudeConnectorSecret.slice(0, 8)}…{claudeConnectorSecret.slice(-4)}
                  </code>
                  {copiedClaudeSecret ? (
                    <Check className="h-4 w-4 flex-shrink-0 text-green-400" />
                  ) : (
                    <Copy className="h-4 w-4 flex-shrink-0 text-text-quaternary transition-colors group-hover:text-text-secondary" />
                  )}
                </button>
              ) : (
                <div className="flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 opacity-60">
                  <span className="text-sm italic text-text-quaternary">Leave blank</span>
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 border-t border-white/[0.06] pt-4">
            <ol className="list-inside list-decimal space-y-1.5 text-xs text-text-tertiary">
              <li>
                Open{' '}
                <span className="text-text-secondary">
                  claude.ai → Settings → Connectors → Add custom connector
                </span>
              </li>
              <li>
                Click each <span className="text-text-secondary">Copy</span> button above
                and paste into the matching field
              </li>
              <li>
                Under <span className="text-text-secondary">Advanced settings</span>,
                paste OAuth Client ID + Secret
              </li>
              <li>
                Click <span className="text-text-secondary">Add</span>, then{' '}
                <span className="text-text-secondary">Connect</span>
              </li>
            </ol>
          </div>
        </Card>
      </div>

      {/* Webhooks */}
      <div id="webhooks" className="scroll-mt-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-text-tertiary">
            Webhooks
          </h3>
          <a
            href="https://docs.omi.me/doc/developer/apps/Introduction"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-text-secondary transition-colors hover:text-text-secondary"
          >
            Docs ↗
          </a>
        </div>
        <Card>
          <div className="space-y-1">
            {webhookTypes.map((webhook, index) => {
              const webhookData = webhooks[webhook.id as keyof DeveloperWebhooks];
              const isEnabled = webhookData?.enabled || false;
              const Icon = webhook.icon;

              return (
                <div key={webhook.id}>
                  {index > 0 && <div className="my-4 border-t border-white/[0.06]" />}
                  <div className="py-2">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="rounded-lg bg-bg-tertiary p-2">
                          <Icon className="h-4 w-4 text-text-tertiary" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-text-primary">
                            {webhook.label}
                          </p>
                          <p className="text-xs text-text-tertiary">
                            {webhook.description}
                          </p>
                        </div>
                      </div>
                      <Toggle
                        enabled={isEnabled}
                        onChange={(enabled) =>
                          onWebhookChange(
                            webhook.id,
                            enabled,
                            webhookUrls[webhook.id],
                            webhook.hasDelay ? audioBytesDelay : undefined,
                          )
                        }
                      />
                    </div>
                    {isEnabled && (
                      <div className="mt-3 space-y-2">
                        <input
                          type="url"
                          value={webhookUrls[webhook.id] || ''}
                          onChange={(e) =>
                            setWebhookUrls({
                              ...webhookUrls,
                              [webhook.id]: e.target.value,
                            })
                          }
                          onBlur={() =>
                            onWebhookChange(
                              webhook.id,
                              true,
                              webhookUrls[webhook.id],
                              webhook.hasDelay ? audioBytesDelay : undefined,
                            )
                          }
                          placeholder="https://your-server.com/webhook"
                          className="w-full rounded-lg border border-white/[0.06] bg-bg-tertiary px-3 py-2 text-sm text-text-primary placeholder:text-text-quaternary focus:border-white/25 focus:outline-none"
                        />
                        {webhook.hasDelay && (
                          <input
                            type="number"
                            value={audioBytesDelay}
                            onChange={(e) => setAudioBytesDelay(e.target.value)}
                            onBlur={() =>
                              onWebhookChange(
                                webhook.id,
                                true,
                                webhookUrls[webhook.id],
                                audioBytesDelay,
                              )
                            }
                            placeholder="Interval (seconds)"
                            className="w-full rounded-lg border border-white/[0.06] bg-bg-tertiary px-3 py-2 text-sm text-text-primary placeholder:text-text-quaternary focus:border-white/25 focus:outline-none"
                          />
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* Data Management */}
      <div id="data-management" className="scroll-mt-4 space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-text-tertiary">
          Data Management
        </h3>
        <Card>
          <button
            onClick={onExportData}
            disabled={isExporting}
            className={cn(
              'flex w-full items-center gap-4 py-3 transition-colors',
              isExporting
                ? 'cursor-not-allowed text-text-tertiary'
                : 'text-text-primary hover:text-text-secondary',
            )}
          >
            <div className="rounded-lg bg-bg-tertiary p-2">
              {isExporting ? (
                <Loader2 className="h-5 w-5 animate-spin text-text-tertiary" />
              ) : (
                <Download className="h-5 w-5 text-text-tertiary" />
              )}
            </div>
            <div className="flex-1 text-left">
              <p className="font-medium">
                {isExporting ? 'Exporting...' : 'Export All Data'}
              </p>
              <p className="text-xs text-text-tertiary">
                {isExporting
                  ? 'This may take a moment'
                  : 'Export conversations to a JSON file'}
              </p>
            </div>
            {!isExporting && <ExternalLink className="h-4 w-4 text-text-quaternary" />}
          </button>
        </Card>
        <Card className="border-red-500/20">
          <button
            onClick={() => setShowDeleteGraphDialog(true)}
            className="flex w-full items-center gap-4 py-3 text-text-primary transition-colors hover:text-red-400"
          >
            <div className="rounded-lg bg-red-500/10 p-2">
              <Network className="h-5 w-5 text-red-400" />
            </div>
            <div className="flex-1 text-left">
              <p className="font-medium">Delete Knowledge Graph</p>
              <p className="text-xs text-text-tertiary">
                Clear all nodes and connections
              </p>
            </div>
            <Trash2 className="h-4 w-4 text-text-quaternary" />
          </button>
        </Card>
      </div>

      {/* Links */}
      <Card>
        <a
          href="https://docs.omi.me"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-between py-3 text-text-primary transition-colors hover:text-text-secondary"
        >
          <div className="flex items-center gap-3">
            <BookOpen className="h-5 w-5 text-text-tertiary" />
            <span>API Documentation</span>
          </div>
          <ExternalLink className="h-4 w-4" />
        </a>
      </Card>

      {/* Dialogs */}
      <CreateApiKeyDialog
        isOpen={showApiKeyDialog}
        onClose={() => setShowApiKeyDialog(false)}
        onCreateKey={onCreateApiKey}
      />
      <CreateMcpKeyDialog
        isOpen={showMcpKeyDialog}
        onClose={() => setShowMcpKeyDialog(false)}
        onCreateKey={onCreateMcpKey}
      />

      {/* Delete Knowledge Graph Dialog */}
      {showDeleteGraphDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => setShowDeleteGraphDialog(false)}
        >
          <div
            className="mx-4 w-full max-w-md rounded-2xl bg-bg-secondary p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-xl bg-red-500/20 p-3">
                <AlertTriangle className="h-6 w-6 text-red-400" />
              </div>
              <h3 className="text-lg font-semibold text-text-primary">
                Delete Knowledge Graph?
              </h3>
            </div>
            <p className="mb-6 text-sm text-text-secondary">
              This will delete all derived knowledge graph data (nodes and connections).
              Your original memories will remain safe. The graph will be rebuilt over
              time.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowDeleteGraphDialog(false)}
                className="flex-1 rounded-xl bg-bg-tertiary py-3 text-text-secondary transition-colors hover:bg-bg-quaternary"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  onDeleteKnowledgeGraph();
                  setShowDeleteGraphDialog(false);
                }}
                className="flex-1 rounded-xl bg-red-500 py-3 text-white transition-colors hover:bg-red-600"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Account Section
// ============================================================================

function AccountSection({
  allUsage,
  subscription,
  cachedPlans,
  onSubscriptionUpdate,
  onSignOut,
  onDeleteAccount,
}: {
  allUsage: AllUsageData | null;
  subscription: UserSubscription | null;
  cachedPlans: PricingOption[] | null;
  onSubscriptionUpdate: () => void;
  onSignOut: () => void;
  onDeleteAccount: () => void;
}) {
  return (
    <div className="space-y-8">
      {/* Plan & Usage */}
      <div id="plan-usage" className="scroll-mt-4">
        <UsageSectionContent
          allUsage={allUsage}
          subscription={subscription}
          onSubscriptionUpdate={onSubscriptionUpdate}
          cachedPlans={cachedPlans}
        />
      </div>

      {/* Fair Use */}
      <div id="fair-use" className="scroll-mt-4">
        <Card>
          <Link
            href="/fair-use"
            className="flex items-center justify-between py-2 text-text-primary transition-colors hover:text-text-secondary"
          >
            <div className="flex items-center gap-3">
              <Scale className="h-5 w-5 text-text-tertiary" />
              <div>
                <span className="font-medium">Fair Use</span>
                <p className="text-sm text-text-quaternary">
                  View speech usage and policy status
                </p>
              </div>
            </div>
            <ChevronRight className="h-4 w-4 text-text-quaternary" />
          </Link>
        </Card>
      </div>

      {/* Account Actions */}
      <div id="actions" className="scroll-mt-4 space-y-3">
        <h3 className="text-sm font-medium uppercase tracking-wider text-text-tertiary">
          Account Actions
        </h3>
        <Card>
          <button
            onClick={onSignOut}
            className="flex w-full items-center gap-3 py-3 text-text-primary transition-colors hover:text-text-secondary"
          >
            <LogOut className="h-5 w-5" />
            <span className="font-medium">Sign Out</span>
          </button>
        </Card>

        <Card className="border-red-500/20">
          <button
            onClick={onDeleteAccount}
            className="flex w-full items-center gap-3 py-3 text-red-400 transition-colors hover:text-red-300"
          >
            <Trash2 className="h-5 w-5" />
            <div className="text-left">
              <span className="block font-medium">Delete Account</span>
              <span className="text-sm text-red-400/70">
                Permanently delete your account and all data
              </span>
            </div>
          </button>
        </Card>
      </div>

      {/* Support */}
      <div id="support" className="scroll-mt-4 space-y-3">
        <h3 className="text-sm font-medium uppercase tracking-wider text-text-tertiary">
          Support
        </h3>
        <Card>
          <a
            href="https://feedback.omi.me"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between border-b border-white/[0.06] py-3 text-text-primary transition-colors hover:text-text-secondary"
          >
            <span>Feedback & Bug Reports</span>
            <ExternalLink className="h-4 w-4" />
          </a>
          <a
            href="https://help.omi.me"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between py-3 text-text-primary transition-colors hover:text-text-secondary"
          >
            <span>Help Center</span>
            <ExternalLink className="h-4 w-4" />
          </a>
        </Card>
      </div>
    </div>
  );
}

// ============================================================================
// Main Settings Page Component
// ============================================================================

// Section titles and descriptions for the header

export function SettingsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, signOut } = useAuth();
  const { showToast } = useToast();
  const [isExporting, setIsExporting] = useState(false);

  // Get section from URL, default to 'account'
  const sectionParam = searchParams.get('section');
  const activeSection: SettingsSection =
    sectionParam && isSettingsSectionId(sectionParam) ? sectionParam : 'account';

  // Track which sections have been loaded (using ref to avoid dependency issues)
  const loadedSectionsRef = useRef<Set<SettingsSection>>(new Set());
  const [sectionLoading, setSectionLoading] = useState<SettingsSection | null>(null);

  // Settings state - each section's data
  const [language, setLanguage] = useState('en');
  // null until the list is known: saving replaces the whole vocabulary, so a
  // failed load must not be sent back as an empty one.
  const [vocabulary, setVocabulary] = useState<string[] | null>(null);
  // null until the settings are known: the save sends the whole object, so a
  // default must not be written over the user's delivery time.
  const [dailySummary, setDailySummary] = useState<DailySummarySettings | null>(null);
  const [recordingPermission, setRecordingPermissionState] = useState(false);
  const [trainingDataOptIn, setTrainingDataOptInState] = useState(false);
  const [allUsage, setAllUsage] = useState<AllUsageData | null>(null);
  const [subscription, setSubscription] = useState<UserSubscription | null>(null);
  const [cachedPlans, setCachedPlans] = useState<PricingOption[] | null>(null);
  const [apiKeys, setApiKeys] = useState<DeveloperApiKey[]>([]);
  const [mcpKeys, setMcpKeys] = useState<McpApiKey[]>([]);
  const [webhooks, setWebhooks] = useState<DeveloperWebhooks>({});

  // Dialog states
  const [showSignOutDialog, setShowSignOutDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      clearRetiredExperimentalFeaturesStorage(() => window.localStorage);
    }
  }, []);

  // Load section data on demand
  useEffect(() => {
    const section = activeSection;
    if (loadedSectionsRef.current.has(section)) return;

    const loadSectionData = async () => {
      setSectionLoading(section);
      try {
        switch (section) {
          case 'privacy':
            const [recording, training] = await Promise.all([
              getRecordingPermission().catch(() => ({ enabled: false })),
              getTrainingDataOptIn().catch(() => ({ opted_in: false })),
            ]);
            setRecordingPermissionState(recording.enabled);
            setTrainingDataOptInState(training.opted_in);
            break;
          case 'account':
            // The merged Account section renders the former Profile and Account
            // groups together, so it loads both sets in one pass.
            const [lang, vocab, summary, usageData, sub, plansData] = await Promise.all([
              getUserLanguage().catch(() => 'en'),
              getCustomVocabulary().catch(() => null),
              getDailySummarySettings().catch(() => null),
              getAllUsageData().catch(() => null),
              getUserSubscription().catch(() => null),
              getAvailablePlans().catch(() => null),
            ]);
            setLanguage(lang);
            setVocabulary(vocab);
            setDailySummary(summary);
            setAllUsage(usageData);
            setSubscription(sub);
            if (plansData?.plans) {
              setCachedPlans(plansData.plans);
            }
            break;
          case 'developer':
            // Fetch API keys, MCP keys, webhook status, and individual webhook URLs in parallel
            // Note: Status API returns boolean fields, URL API returns {url: string}
            const [
              keys,
              mKeys,
              webhookStatus,
              memoryUrl,
              transcriptUrl,
              audioBytesUrl,
              daySummaryUrl,
            ] = await Promise.all([
              getDeveloperApiKeys().catch(() => []),
              getMcpApiKeys().catch(() => []),
              getDeveloperWebhooksStatus().catch(() => ({})),
              getDeveloperWebhook('memory_created').catch(() => ({ url: '' })),
              getDeveloperWebhook('realtime_transcript').catch(() => ({ url: '' })),
              getDeveloperWebhook('audio_bytes').catch(() => ({ url: '' })),
              getDeveloperWebhook('day_summary').catch(() => ({ url: '' })),
            ]);
            setApiKeys(keys);
            // Full MCP key is only returned at creation time; keep secrets in memory for this session only.
            if (typeof window !== 'undefined') {
              localStorage.removeItem('omi_mcp_api_key_secrets');
            }
            setMcpKeys(mKeys);
            // Combine status (booleans) with URLs
            const statusMap = webhookStatus as Record<string, boolean>;
            setWebhooks({
              memory_created: {
                url: memoryUrl?.url || '',
                enabled: statusMap['memory_created'] ?? false,
              },
              transcript_received: {
                url: transcriptUrl?.url || '',
                enabled: statusMap['realtime_transcript'] ?? false,
              },
              audio_bytes: {
                url: audioBytesUrl?.url || '',
                enabled: statusMap['audio_bytes'] ?? false,
              },
              day_summary: {
                url: daySummaryUrl?.url || '',
                enabled: statusMap['day_summary'] ?? false,
              },
            });
            break;
          // sections not listed here don't need API calls
        }
        loadedSectionsRef.current.add(section);
      } catch (error) {
        console.error(`Failed to load ${section} settings:`, error);
      } finally {
        setSectionLoading(null);
      }
    };

    loadSectionData();
  }, [activeSection]);

  // Handlers
  const handleLanguageChange = async (newLanguage: string) => {
    const oldLanguage = language;
    setLanguage(newLanguage);
    try {
      await setUserLanguage(newLanguage);
    } catch {
      setLanguage(oldLanguage);
    }
  };

  const handleAddWord = async (word: string) => {
    if (vocabulary === null) return;
    const newVocabulary = [...vocabulary, word];
    setVocabulary(newVocabulary);
    try {
      await updateCustomVocabulary(newVocabulary);
    } catch {
      setVocabulary(vocabulary);
    }
  };

  const handleRemoveWord = async (word: string) => {
    if (vocabulary === null) return;
    const newVocabulary = vocabulary.filter((w) => w !== word);
    setVocabulary(newVocabulary);
    try {
      await updateCustomVocabulary(newVocabulary);
    } catch {
      setVocabulary(vocabulary);
    }
  };

  const handleDailySummaryToggle = async (enabled: boolean) => {
    if (dailySummary === null) return;
    const oldSettings = dailySummary;
    setDailySummary({ ...dailySummary, enabled });
    try {
      await updateDailySummarySettings({ ...dailySummary, enabled });
    } catch {
      setDailySummary(oldSettings);
    }
  };

  const handleDailySummaryHourChange = async (hour: number) => {
    if (dailySummary === null) return;
    const oldSettings = dailySummary;
    setDailySummary({ ...dailySummary, hour });
    try {
      await updateDailySummarySettings({ ...dailySummary, hour });
    } catch {
      setDailySummary(oldSettings);
    }
  };

  const handleRecordingPermissionChange = async (enabled: boolean) => {
    const oldValue = recordingPermission;
    setRecordingPermissionState(enabled);
    try {
      await setRecordingPermission(enabled);
    } catch {
      setRecordingPermissionState(oldValue);
    }
  };

  const handleTrainingDataChange = async (optIn: boolean) => {
    if (!optIn) return;
    const oldValue = trainingDataOptIn;
    setTrainingDataOptInState(optIn);
    try {
      await setTrainingDataOptIn(optIn);
    } catch {
      setTrainingDataOptInState(oldValue);
    }
  };

  const refreshSubscription = async () => {
    try {
      const [usageData, sub] = await Promise.all([
        getAllUsageData().catch(() => null),
        getUserSubscription().catch(() => null),
      ]);
      setAllUsage(usageData);
      setSubscription(sub);
    } catch (error) {
      console.error('Failed to refresh subscription:', error);
    }
  };

  const handleCopyUserId = () => {
    if (user?.uid) {
      navigator.clipboard.writeText(user.uid);
    }
  };

  const handleCreateApiKey = async (
    name: string,
    scopes: string[],
  ): Promise<DeveloperApiKey | null> => {
    try {
      const newKey = await createDeveloperApiKey(name, scopes);
      setApiKeys([...apiKeys, newKey]);
      return newKey;
    } catch (error) {
      console.error('Failed to create API key:', error);
      return null;
    }
  };

  const handleDeleteApiKey = async (keyId: string) => {
    try {
      await deleteDeveloperApiKey(keyId);
      setApiKeys(apiKeys.filter((k) => k.id !== keyId));
    } catch (error) {
      console.error('Failed to delete API key:', error);
    }
  };

  const handleCreateMcpKey = async (name: string): Promise<McpApiKey | null> => {
    try {
      const newKey = await createMcpApiKey(name);
      setMcpKeys([...mcpKeys, newKey]);
      return newKey;
    } catch (error) {
      console.error('Failed to create MCP key:', error);
      return null;
    }
  };

  const handleDeleteMcpKey = async (keyId: string) => {
    try {
      await deleteMcpApiKey(keyId);
      setMcpKeys(mcpKeys.filter((k) => k.id !== keyId));
    } catch (error) {
      console.error('Failed to delete MCP key:', error);
    }
  };

  const handleExportData = async () => {
    if (isExporting) return;
    setIsExporting(true);
    try {
      const blob = await exportAllData();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'omi-export.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast('Data exported successfully', 'success');
    } catch (error) {
      console.error('Failed to export data:', error);
      showToast('Failed to export data. Please try again.', 'error');
    } finally {
      setIsExporting(false);
    }
  };

  const handleDeleteKnowledgeGraph = async () => {
    try {
      await deleteKnowledgeGraph();
    } catch (error) {
      console.error('Failed to delete knowledge graph:', error);
    }
  };

  const handleWebhookChange = async (
    type: string,
    enabled: boolean,
    url?: string,
    delay?: string,
  ) => {
    // Convert internal type names to API type names
    // UI uses 'transcript_received' but API expects 'realtime_transcript'
    const apiType = type === 'transcript_received' ? 'realtime_transcript' : type;
    const webhookType = apiType as
      | 'memory_created'
      | 'realtime_transcript'
      | 'audio_bytes'
      | 'day_summary';
    try {
      // For audio_bytes, combine URL and delay if both are provided
      const webhookUrl = type === 'audio_bytes' && url && delay ? `${url},${delay}` : url;
      if (webhookUrl) {
        await setDeveloperWebhook(webhookType, webhookUrl);
      }
      if (enabled) {
        await enableDeveloperWebhook(webhookType);
      } else {
        await disableDeveloperWebhook(webhookType);
      }
      setWebhooks({
        ...webhooks,
        [type]: {
          enabled,
          // Mirror what was sent: audio_bytes keeps its interval in the URL, and
          // storing the bare URL here made the interval field fall back to 5.
          url: webhookUrl || webhooks[type as keyof DeveloperWebhooks]?.url || '',
        },
      });
    } catch (error) {
      console.error('Failed to update webhook:', error);
    }
  };

  const handleSignOut = async () => {
    await signOut();
    router.push(SIGNED_OUT_DESTINATION);
  };

  const handleDeleteAccount = async () => {
    setIsDeleting(true);
    try {
      await deleteAccount();
      await signOut();
      router.push(SIGNED_OUT_DESTINATION);
    } catch {
      setIsDeleting(false);
    }
  };

  const renderSection = () => {
    // Show loading spinner when section is loading
    if (sectionLoading === activeSection) {
      return (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-text-primary" />
        </div>
      );
    }

    switch (activeSection) {
      case 'privacy':
        return (
          <PrivacySection
            recordingPermission={recordingPermission}
            trainingDataOptIn={trainingDataOptIn}
            onRecordingChange={handleRecordingPermissionChange}
            onTrainingDataChange={handleTrainingDataChange}
          />
        );
      case 'account':
        return (
          <div className="space-y-10">
            <ProfileSection
              user={user}
              onCopyUserId={handleCopyUserId}
              language={language}
              vocabulary={vocabulary}
              onLanguageChange={handleLanguageChange}
              onAddWord={handleAddWord}
              onRemoveWord={handleRemoveWord}
              dailySummary={dailySummary}
              onDailySummaryToggle={handleDailySummaryToggle}
              onDailySummaryHourChange={handleDailySummaryHourChange}
            />
            <AccountSection
              allUsage={allUsage}
              subscription={subscription}
              cachedPlans={cachedPlans}
              onSubscriptionUpdate={refreshSubscription}
              onSignOut={() => setShowSignOutDialog(true)}
              onDeleteAccount={() => setShowDeleteDialog(true)}
            />
          </div>
        );
      case 'developer':
        return (
          <DeveloperSection
            apiKeys={apiKeys}
            mcpKeys={mcpKeys}
            webhooks={webhooks}
            onCreateApiKey={handleCreateApiKey}
            onDeleteApiKey={handleDeleteApiKey}
            onCreateMcpKey={handleCreateMcpKey}
            onDeleteMcpKey={handleDeleteMcpKey}
            onWebhookChange={handleWebhookChange}
            onExportData={handleExportData}
            isExporting={isExporting}
            onDeleteKnowledgeGraph={handleDeleteKnowledgeGraph}
          />
        );
      default:
        return null;
    }
  };

  const sectionInfo = SECTION_INFO[activeSection];

  // Quick nav sections for each settings section
  const getQuickNavSections = () => {
    switch (activeSection) {
      case 'account':
        return [
          { id: 'account-info', label: 'Account' },
          { id: 'language', label: 'Language' },
          { id: 'vocabulary', label: 'Vocabulary' },
          { id: 'notifications', label: 'Notifications' },
          { id: 'plan-usage', label: 'Plan & Usage' },
          { id: 'fair-use', label: 'Fair Use' },
          { id: 'actions', label: 'Actions' },
          { id: 'support', label: 'Support' },
        ];
      case 'developer':
        return [
          { id: 'api-keys', label: 'API Keys' },
          { id: 'mcp', label: 'MCP' },
          { id: 'webhooks', label: 'Webhooks' },
          { id: 'data-management', label: 'Data' },
        ];
      default:
        return [];
    }
  };

  const quickNavSections = getQuickNavSections();

  return (
    <div className="flex h-full flex-col">
      {/* Export in-progress dialog */}
      {isExporting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" />
          <div className="relative mx-4 w-full max-w-sm rounded-2xl border border-white/[0.06] bg-bg-secondary p-6 shadow-2xl">
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="rounded-full bg-white/[0.08] p-3">
                <Loader2 className="h-8 w-8 animate-spin text-text-secondary" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text-primary">
                  Exporting Your Data
                </h3>
                <p className="mt-2 text-sm text-text-secondary">
                  This may take a moment depending on the amount of data in your account.
                </p>
              </div>
              <div className="flex items-center gap-2 rounded-xl bg-yellow-500/10 px-4 py-2">
                <AlertTriangle className="h-4 w-4 flex-shrink-0 text-yellow-400" />
                <span className="text-xs text-yellow-400">
                  Please don&apos;t close this tab
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Page Header */}
      <PageHeader title={sectionInfo.title} icon={Settings} showBackButton />

      {/* Main Content with optional Quick Nav */}
      <main className="flex-1 overflow-y-auto pb-12">
        <div className="mx-auto max-w-4xl px-6 pt-6 lg:px-8">
          <div className="flex gap-6">
            {/* Main content */}
            <div className="min-w-0 flex-1">{renderSection()}</div>

            {/* Quick Nav Sidebar - only show on desktop when there are sections */}
            {quickNavSections.length > 0 && (
              <div className="hidden w-32 flex-shrink-0 lg:block">
                <div className="sticky top-4">
                  <p className="mb-3 text-xs font-medium uppercase tracking-wider text-text-quaternary">
                    On this page
                  </p>
                  <nav className="space-y-1">
                    {quickNavSections.map((section) => (
                      <a
                        key={section.id}
                        href={`#${section.id}`}
                        className="block py-1 text-sm text-text-tertiary transition-colors hover:text-text-primary"
                      >
                        {section.label}
                      </a>
                    ))}
                  </nav>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Dialogs */}
      <ConfirmDialog
        isOpen={showSignOutDialog}
        title="Sign Out"
        message="Are you sure you want to sign out?"
        confirmLabel="Sign Out"
        onConfirm={handleSignOut}
        onCancel={() => setShowSignOutDialog(false)}
      />

      <ConfirmDialog
        isOpen={showDeleteDialog}
        title="Delete Account"
        message="This action cannot be undone. All your data, conversations, and settings will be permanently deleted."
        confirmLabel="Delete Account"
        onConfirm={handleDeleteAccount}
        onCancel={() => setShowDeleteDialog(false)}
        isDestructive
        isLoading={isDeleting}
      />
    </div>
  );
}

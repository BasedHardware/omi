'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Image from 'next/image';
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
  FlaskConical,
  Activity,
  UserPlus,
  Lightbulb,
  Target,
  Moon,
  ArrowLeft,
  Crown,
  ChevronRight,
  Zap,
  CreditCard,
} from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { cn } from '@/lib/utils';
import { PageHeader } from '@/components/layout/PageHeader';
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
  getIntegrations,
  getIntegrationOAuthUrl,
  disconnectIntegration,
  getAvailablePlans,
  createCheckoutSession,
  upgradeSubscription,
  cancelSubscription,
  getCustomerPortal,
} from '@/lib/api';
import { SUPPORTED_LANGUAGES, API_KEY_SCOPES } from '@/types/user';
import type { DailySummarySettings, UserUsage, UserSubscription, AllUsageData, DeveloperWebhooks, DeveloperApiKey, McpApiKey, Integration, UsageHistoryPoint, PricingOption } from '@/types/user';

// ============================================================================
// Types
// ============================================================================

type SettingsSection = 'profile' | 'privacy' | 'integrations' | 'developer' | 'account';

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
        'relative w-11 h-6 rounded-full transition-all duration-200 flex-shrink-0',
        enabled
          ? 'bg-purple-500 shadow-[0_0_12px_rgba(139,92,246,0.4)]'
          : 'bg-white/[0.08]',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      <div
        className={cn(
          'absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all duration-200 shadow-sm',
          enabled ? 'left-[22px]' : 'left-0.5'
        )}
      />
    </button>
  );
}

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        'rounded-2xl p-5',
        // Layered background for depth instead of harsh border
        'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
        // Soft shadow stack
        'shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]',
        className
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
    <div className="flex items-center justify-between py-4 border-b border-white/[0.04] last:border-0">
      <div className="flex-1 min-w-0 mr-4">
        <p className="text-[15px] text-white/85 font-medium">{label}</p>
        {description && (
          <p className="text-[13px] text-white/40 mt-0.5 leading-relaxed">{description}</p>
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
          'flex items-center justify-between gap-2 px-4 py-2.5 rounded-xl',
          'bg-white/[0.04] ring-1 ring-white/[0.06]',
          'text-white/80 min-w-[160px]',
          'hover:bg-white/[0.06] transition-colors'
        )}
      >
        <span className="truncate text-sm">{selectedOption?.label || placeholder}</span>
        <ChevronDown
          className={cn(
            'w-4 h-4 text-white/40 transition-transform',
            isOpen && 'rotate-180'
          )}
        />
      </button>

      {isOpen && (
        <div className={cn(
          'absolute z-50 w-full mt-2 py-1.5 rounded-xl max-h-64 overflow-y-auto',
          'bg-[#1a1a1f]/95 backdrop-blur-xl',
          'shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_10px_30px_-5px_rgba(0,0,0,0.5)]'
        )}>
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
              className={cn(
                'w-full px-4 py-2.5 text-left transition-colors flex items-center justify-between text-sm',
                option.value === value
                  ? 'bg-purple-500/15 text-white'
                  : 'text-white/70 hover:bg-white/[0.04] hover:text-white/90'
              )}
            >
              <span>{option.label}</span>
              {option.value === value && (
                <Check className="w-4 h-4 text-purple-400" />
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
      <div className="relative bg-bg-secondary rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl border border-white/[0.06]">
        <div className="flex items-start gap-4 mb-4">
          <div
            className={cn(
              'p-2 rounded-full',
              isDestructive ? 'bg-red-500/10' : 'bg-purple-500/10'
            )}
          >
            <AlertTriangle
              className={cn(
                'w-6 h-6',
                isDestructive ? 'text-red-400' : 'text-purple-400'
              )}
            />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
            <p className="text-text-secondary mt-1">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className={cn(
              'px-4 py-2 rounded-xl font-medium',
              'bg-bg-tertiary text-text-primary',
              'hover:bg-bg-quaternary transition-colors',
              'disabled:opacity-50'
            )}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className={cn(
              'px-4 py-2 rounded-xl font-medium flex items-center gap-2',
              isDestructive
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-purple-500 text-white hover:bg-purple-600',
              'transition-colors disabled:opacity-50'
            )}
          >
            {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
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
  vocabulary: string[];
  onLanguageChange: (lang: string) => void;
  onAddWord: (word: string) => void;
  onRemoveWord: (word: string) => void;
  dailySummary: DailySummarySettings;
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

  const handleAddWord = () => {
    if (newWord.trim()) {
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
      <div id="account-info" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">Account</h3>
        <Card>
          <div className="flex items-center gap-5">
            <div className="w-20 h-20 rounded-full overflow-hidden bg-bg-tertiary ring-2 ring-purple-500/30 flex-shrink-0">
              {user?.photoURL ? (
                <Image
                  src={user.photoURL}
                  alt={user.displayName || 'User'}
                  width={80}
                  height={80}
                  className="object-cover w-full h-full"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-text-tertiary text-2xl font-medium">
                  {user?.displayName?.charAt(0) || 'U'}
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-semibold text-text-primary truncate">
                {user?.displayName || 'User'}
              </h3>
              <p className="text-text-tertiary truncate">{user?.email}</p>
            </div>
          </div>
        </Card>

        <Card>
          <SettingRow label="User ID" description="Your unique identifier">
            <div className="flex items-center gap-2">
              <code className="text-sm text-text-tertiary font-mono bg-bg-tertiary px-3 py-1.5 rounded-lg">
                {user?.uid?.slice(0, 8)}...{user?.uid?.slice(-4)}
              </code>
              <button
                onClick={handleCopy}
                className={cn(
                  'p-2 rounded-lg transition-colors',
                  copiedUserId
                    ? 'bg-green-500/10 text-green-400'
                    : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary'
                )}
              >
                {copiedUserId ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
          </SettingRow>
        </Card>
      </div>

      {/* Language & Transcription */}
      <div id="language" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">Language & Transcription</h3>
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
      <div id="vocabulary" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">Custom Vocabulary</h3>
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
                  'flex-1 px-4 py-2.5 rounded-xl',
                  'bg-bg-tertiary border border-white/[0.06]',
                  'text-text-primary placeholder:text-text-quaternary',
                  'focus:outline-none focus:border-purple-500'
                )}
              />
              <button
                onClick={handleAddWord}
                disabled={!newWord.trim()}
                className={cn(
                  'px-4 py-2.5 rounded-xl font-medium',
                  'bg-purple-500 text-white',
                  'hover:bg-purple-600 transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                <Plus className="w-5 h-5" />
              </button>
            </div>

            {vocabulary.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-2">
                {vocabulary.map((word) => (
                  <span
                    key={word}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-bg-tertiary text-text-secondary text-sm"
                  >
                    {word}
                    <button
                      onClick={() => onRemoveWord(word)}
                      className="text-text-quaternary hover:text-red-400 transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {vocabulary.length === 0 && (
              <p className="text-sm text-text-quaternary text-center py-4">
                No custom vocabulary added yet
              </p>
            )}
          </div>
        </Card>
      </div>

      {/* Notifications */}
      <div id="notifications" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">Notifications</h3>
        <Card>
          <SettingRow
            label="Daily Summary"
            description="Receive a daily digest of your action items"
          >
            <Toggle enabled={dailySummary.enabled} onChange={onDailySummaryToggle} />
          </SettingRow>

          {dailySummary.enabled && (
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
          <Toggle enabled={trainingDataOptIn} onChange={onTrainingDataChange} />
        </SettingRow>
      </Card>

      <Card className="border-purple-500/20">
        <div className="flex items-start gap-4">
          <div className="p-2 rounded-lg bg-purple-500/10">
            <Shield className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h3 className="text-text-primary font-medium">Your Privacy Matters</h3>
            <p className="text-sm text-text-tertiary mt-1">
              Your data is encrypted and never shared with third parties. You have full control over what data is collected and stored.
            </p>
            <a
              href="https://omi.me/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-purple-400 hover:underline mt-2"
            >
              Learn more about our privacy policy
              <ExternalLink className="w-3.5 h-3.5" />
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

function UsageChart({ history, period }: { history?: UsageHistoryPoint[]; period: UsagePeriod }) {
  const [selectedMetric, setSelectedMetric] = useState<'listening' | 'words' | 'insights' | 'memories'>('listening');

  if (!history || history.length === 0) {
    return (
      <Card className="h-48 flex items-center justify-center">
        <p className="text-text-quaternary">No activity data available</p>
      </Card>
    );
  }

  // For all_time with many data points, aggregate by year
  let dataToProcess = history;
  if (period === 'all_time' && history.length > 12) {
    // Group by year and aggregate
    const yearlyData = new Map<string, UsageHistoryPoint>();
    history.forEach(point => {
      const date = new Date(point.date);
      const key = String(date.getFullYear());
      const existing = yearlyData.get(key);
      if (existing) {
        yearlyData.set(key, {
          date: `${key}-01-01`,
          transcription_seconds: existing.transcription_seconds + point.transcription_seconds,
          words_transcribed: existing.words_transcribed + point.words_transcribed,
          insights_gained: existing.insights_gained + point.insights_gained,
          memories_created: existing.memories_created + point.memories_created,
        });
      } else {
        yearlyData.set(key, { ...point, date: `${key}-01-01` });
      }
    });
    dataToProcess = Array.from(yearlyData.values()).sort((a, b) => a.date.localeCompare(b.date));
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
        label = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][month - 1];
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
      case 'listening': return d.transcription_seconds / 60; // Convert to minutes
      case 'words': return d.words_transcribed;
      case 'insights': return d.insights_gained;
      case 'memories': return d.memories_created;
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
      case 'listening': return `${formatted} min`;
      case 'words': return formatted;
      case 'insights': return formatted;
      case 'memories': return formatted;
    }
  };

  // Find max value for scaling
  const maxValue = Math.max(...processedData.map(d => getValue(d)), 1);

  const metricConfig = [
    { key: 'listening' as const, color: 'rgb(96, 165, 250)', label: 'Listening' },
    { key: 'words' as const, color: 'rgb(74, 222, 128)', label: 'Words' },
    { key: 'insights' as const, color: 'rgb(251, 146, 60)', label: 'Insights' },
    { key: 'memories' as const, color: 'rgb(192, 132, 252)', label: 'Memories' },
  ];

  const currentMetric = metricConfig.find(m => m.key === selectedMetric)!;

  return (
    <Card>
      {/* Header with metric selector */}
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-sm font-semibold text-text-secondary">Activity Over Time</h4>
        <div className="flex gap-1">
          {metricConfig.map(metric => (
            <button
              key={metric.key}
              onClick={() => setSelectedMetric(metric.key)}
              className={cn(
                'px-2.5 py-1 rounded-md text-xs font-medium transition-all',
                selectedMetric === metric.key
                  ? 'opacity-100'
                  : 'opacity-40 hover:opacity-60'
              )}
              style={{
                backgroundColor: selectedMetric === metric.key ? `${metric.color}20` : 'transparent',
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
            <div key={i} className="flex-1 flex flex-col items-center">
              {/* Value on top */}
              <span
                className="text-xs font-bold mb-2 whitespace-nowrap"
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
              <span className="text-xs text-text-quaternary mt-2 font-medium">{d.label}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

type PlanUsageTab = 'plan' | 'usage';

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

  // Set initial selected price when plans load
  useEffect(() => {
    if (cachedPlans && cachedPlans.length > 0 && !selectedPriceId) {
      const activePlan = cachedPlans.find((p) => p.is_active);
      if (activePlan) {
        setSelectedPriceId(activePlan.id);
      } else {
        setSelectedPriceId(cachedPlans[0].id);
      }
    }
  }, [cachedPlans, selectedPriceId]);

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

  const getPlanDisplayName = (plan: string) => {
    if (plan === 'unlimited') return 'Unlimited';
    if (plan === 'basic') return 'Free';
    return plan || 'Free';
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

  const isUnlimited = subscription?.is_unlimited;
  const isCancelingSubscription = subscription?.cancel_at_period_end;

  // Calculate usage percentages for basic plan
  const getUsagePercent = (used: number, limit: number) => {
    if (limit <= 0) return 0;
    return Math.min((used / limit) * 100, 100);
  };

  // Sort pricing options: monthly first, then annual
  const sortedOptions = cachedPlans ? [...cachedPlans].sort((a, b) => {
    const aIsAnnual = a.interval === 'year' || a.title?.toLowerCase().includes('annual');
    const bIsAnnual = b.interval === 'year' || b.title?.toLowerCase().includes('annual');
    return (aIsAnnual ? 1 : 0) - (bIsAnnual ? 1 : 0);
  }) : [];

  const selectedOption = cachedPlans?.find((p) => p.id === selectedPriceId);

  // Default features for unlimited plan
  const defaultFeatures = [
    'Unlimited conversations',
    'Unlimited memories',
    'Priority processing',
    'Advanced insights',
  ];

  const handleSubscribe = async () => {
    if (!selectedPriceId) return;

    setIsLoading(true);
    setError(null);

    try {
      const isCurrentPlan = selectedOption?.is_active;

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
      <div className="flex gap-1 p-1 bg-bg-tertiary rounded-xl w-fit">
          <button
            onClick={() => setActiveTab('plan')}
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-medium transition-all',
              activeTab === 'plan'
                ? 'bg-purple-500 text-white shadow-md'
                : 'text-text-secondary hover:text-text-primary hover:bg-bg-quaternary'
            )}
          >
            Plan
          </button>
          <button
            onClick={() => setActiveTab('usage')}
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-medium transition-all',
              activeTab === 'usage'
                ? 'bg-purple-500 text-white shadow-md'
                : 'text-text-secondary hover:text-text-primary hover:bg-bg-quaternary'
            )}
          >
            Usage
          </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'plan' ? (
        /* PLAN TAB - Different views for Basic vs Unlimited */
        <div className="space-y-6">
            {!isUnlimited ? (
              /* BASIC PLAN VIEW */
              <>
                {/* Current Plan Card */}
                <Card className="relative overflow-hidden">
                  {/* Header */}
                  <div className="flex items-start justify-between mb-6">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-purple-500/20 to-purple-600/10 flex items-center justify-center">
                        <Zap className="w-6 h-6 text-purple-400" />
                      </div>
                      <div>
                        <h3 className="text-xl font-semibold text-text-primary">Basic Plan</h3>
                        <p className="text-sm text-text-tertiary">Free tier</p>
                      </div>
                    </div>
                    <button
                      onClick={() => setShowUpgradeOptions(true)}
                      className="px-5 py-2.5 bg-gradient-to-r from-purple-500 to-purple-600 hover:from-purple-600 hover:to-purple-700 text-white text-sm font-semibold rounded-xl transition-all shadow-lg shadow-purple-500/20"
                    >
                      Upgrade to Unlimited
                    </button>
                  </div>

                  {/* Monthly Listening Usage */}
                  <div className="p-4 bg-amber-500/5 border border-amber-500/20 rounded-xl mb-6">
                    <div className="flex items-center gap-2 mb-3">
                      <Clock className="w-4 h-4 text-amber-400" />
                      <span className="text-sm font-semibold text-amber-400">Monthly Listening Limit</span>
                    </div>
                    <div className="flex items-baseline justify-between mb-2">
                      <span className="text-2xl font-bold text-text-primary">
                        {monthlyUsage ? Math.round(monthlyUsage.transcription_seconds / 60) : 0}
                        <span className="text-sm font-normal text-text-tertiary ml-1">/ 1,200 min</span>
                      </span>
                      <span className="text-sm text-text-tertiary">
                        {monthlyUsage ? (1200 - Math.round(monthlyUsage.transcription_seconds / 60)) : 1200} min left
                      </span>
                    </div>
                    <div className="h-2.5 bg-bg-quaternary rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all duration-500"
                        style={{ width: `${monthlyUsage ? getUsagePercent(monthlyUsage.transcription_seconds, limits.transcription_seconds) : 0}%` }}
                      />
                    </div>
                  </div>

                  {/* What's Included - Checklist */}
                  <div>
                    <h4 className="text-sm font-semibold text-text-secondary mb-3">What&apos;s included</h4>
                    <div className="space-y-3">
                      <div className="flex items-center gap-3">
                        <div className="w-5 h-5 rounded bg-amber-500/20 flex items-center justify-center flex-shrink-0">
                          <Clock className="w-3 h-3 text-amber-400" />
                        </div>
                        <span className="text-sm text-text-secondary">
                          <span className="font-medium text-text-primary">1,200 minutes</span> of listening per month
                          <span className="text-amber-400 text-xs ml-1">(limited)</span>
                        </span>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="w-5 h-5 rounded bg-green-500/20 flex items-center justify-center flex-shrink-0">
                          <Check className="w-3 h-3 text-green-400" />
                        </div>
                        <span className="text-sm text-text-secondary">
                          <span className="font-medium text-text-primary">Unlimited</span> words transcribed
                        </span>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="w-5 h-5 rounded bg-green-500/20 flex items-center justify-center flex-shrink-0">
                          <Check className="w-3 h-3 text-green-400" />
                        </div>
                        <span className="text-sm text-text-secondary">
                          <span className="font-medium text-text-primary">Unlimited</span> insights
                        </span>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="w-5 h-5 rounded bg-green-500/20 flex items-center justify-center flex-shrink-0">
                          <Check className="w-3 h-3 text-green-400" />
                        </div>
                        <span className="text-sm text-text-secondary">
                          <span className="font-medium text-text-primary">Unlimited</span> memories
                        </span>
                      </div>
                    </div>
                  </div>
                </Card>

                {/* Upgrade Options (shown when clicked) */}
                {showUpgradeOptions && (
                  <Card className="border-purple-500/20">
                    <div className="flex items-center justify-between mb-5">
                      <div>
                        <h4 className="text-lg font-semibold text-text-primary">Choose a Plan</h4>
                        <p className="text-sm text-text-tertiary">Unlock unlimited listening time</p>
                      </div>
                      <button
                        onClick={() => setShowUpgradeOptions(false)}
                        className="p-2 hover:bg-bg-tertiary rounded-lg transition-colors"
                      >
                        <X className="w-5 h-5 text-text-quaternary" />
                      </button>
                    </div>

                    {/* Plan Selection */}
                    {sortedOptions.length > 0 ? (
                      <div className="grid grid-cols-2 gap-4 mb-5">
                        {sortedOptions.map((option) => {
                          const isSelected = selectedPriceId === option.id;
                          const isAnnual = option.interval === 'year' || option.title?.toLowerCase().includes('annual');

                          return (
                            <button
                              key={option.id}
                              onClick={() => setSelectedPriceId(option.id)}
                              className={cn(
                                'relative p-5 rounded-2xl border-2 text-left transition-all',
                                isSelected
                                  ? 'border-purple-500 bg-purple-500/5 shadow-lg shadow-purple-500/10'
                                  : 'border-bg-tertiary hover:border-purple-500/30 bg-bg-tertiary/30'
                              )}
                            >
                              {isAnnual && (
                                <span className="absolute -top-2.5 right-3 px-3 py-1 bg-gradient-to-r from-purple-500 to-purple-600 text-white text-[10px] font-bold rounded-full uppercase tracking-wide">
                                  Best Value
                                </span>
                              )}
                              <h4 className="font-semibold text-text-primary mb-1">{option.title}</h4>
                              <p className="text-2xl font-bold text-text-primary">{option.price_string}</p>
                              {option.description && (
                                <p className="text-xs text-purple-400 mt-2 font-medium">{option.description}</p>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 className="w-6 h-6 text-purple-500 animate-spin" />
                      </div>
                    )}

                    {/* Error Message */}
                    {error && (
                      <div className="flex items-center gap-2 p-3 bg-red-500/10 rounded-xl mb-4 border border-red-500/20">
                        <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                        <p className="text-sm text-red-400">{error}</p>
                      </div>
                    )}

                    <button
                      onClick={handleSubscribe}
                      disabled={isLoading || !selectedPriceId}
                      className={cn(
                        'w-full py-3.5 rounded-xl font-semibold transition-all',
                        'bg-gradient-to-r from-purple-500 to-purple-600 text-white',
                        'hover:from-purple-600 hover:to-purple-700',
                        'shadow-lg shadow-purple-500/20',
                        'disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none'
                      )}
                    >
                      {isLoading ? (
                        <span className="flex items-center justify-center gap-2">
                          <Loader2 className="w-4 h-4 animate-spin" />
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
                  <h4 className="text-sm font-semibold text-text-secondary mb-4">This month</h4>
                  <div className="grid grid-cols-4 gap-3">
                    <div className="text-center">
                      <div className="w-10 h-10 mx-auto rounded-xl bg-blue-500/10 flex items-center justify-center mb-2">
                        <Mic className="w-5 h-5 text-blue-400" />
                      </div>
                      <p className="text-xl font-bold text-blue-400">
                        {monthlyUsage ? formatDuration(monthlyUsage.transcription_seconds) : '0m'}
                      </p>
                      <p className="text-xs text-text-quaternary">Listening</p>
                    </div>
                    <div className="text-center">
                      <div className="w-10 h-10 mx-auto rounded-xl bg-green-500/10 flex items-center justify-center mb-2">
                        <MessageSquare className="w-5 h-5 text-green-400" />
                      </div>
                      <p className="text-xl font-bold text-green-400">
                        {monthlyUsage ? formatNumber(monthlyUsage.words_transcribed) : '0'}
                      </p>
                      <p className="text-xs text-text-quaternary">Words</p>
                    </div>
                    <div className="text-center">
                      <div className="w-10 h-10 mx-auto rounded-xl bg-orange-500/10 flex items-center justify-center mb-2">
                        <Lightbulb className="w-5 h-5 text-orange-400" />
                      </div>
                      <p className="text-xl font-bold text-orange-400">
                        {monthlyUsage?.insights_gained || 0}
                      </p>
                      <p className="text-xs text-text-quaternary">Insights</p>
                    </div>
                    <div className="text-center">
                      <div className="w-10 h-10 mx-auto rounded-xl bg-purple-500/10 flex items-center justify-center mb-2">
                        <Brain className="w-5 h-5 text-purple-400" />
                      </div>
                      <p className="text-xl font-bold text-purple-400">
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
                  <div className="w-10 h-10 rounded-full bg-purple-500/20 flex items-center justify-center">
                    <Crown className="w-5 h-5 text-purple-400" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-text-primary">
                      {isCancelingSubscription ? 'Your Plan' : 'Manage Your Plan'}
                    </h3>
                    {subscription?.current_period_end && (
                      <p className="text-xs text-text-quaternary">
                        {isCancelingSubscription
                          ? `Cancels on ${formatDate(subscription.current_period_end)}`
                          : `Renews ${formatDate(subscription.current_period_end)}`
                        }
                      </p>
                    )}
                  </div>
                </div>

                {/* Plan Selection */}
                {sortedOptions.length > 0 ? (
                  <div className="grid grid-cols-2 gap-3">
                    {sortedOptions.map((option) => {
                      const isSelected = selectedPriceId === option.id;
                      const isCurrent = option.is_active;
                      const isAnnual = option.interval === 'year' || option.title?.toLowerCase().includes('annual');

                      return (
                        <button
                          key={option.id}
                          onClick={() => setSelectedPriceId(option.id)}
                          className={cn(
                            'relative p-4 rounded-xl border-2 text-left transition-all',
                            isSelected
                              ? 'border-purple-500 bg-purple-500/5'
                              : 'border-bg-tertiary hover:border-bg-quaternary bg-bg-tertiary/50'
                          )}
                        >
                          {isAnnual && (
                            <span className="absolute -top-2 right-2 px-2 py-0.5 bg-purple-500 text-white text-[10px] font-medium rounded-full">
                              POPULAR
                            </span>
                          )}

                          <h4 className="font-medium text-text-primary mb-1">
                            {option.title}
                          </h4>
                          <p className="text-lg font-bold text-text-primary">
                            {option.price_string}
                          </p>
                          {option.description && (
                            <p className="text-xs text-purple-400 mt-1">
                              {option.description}
                            </p>
                          )}

                          {isCurrent && (
                            <span className="inline-flex items-center gap-1 mt-2 px-2 py-0.5 bg-green-500/10 text-green-400 text-xs rounded-full">
                              <Check className="w-3 h-3" />
                              Current
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-6 h-6 text-purple-500 animate-spin" />
                  </div>
                )}

                {/* Features List */}
                <div className="space-y-2">
                  <h4 className="text-sm font-medium text-text-secondary">Features:</h4>
                  <ul className="space-y-2">
                    {defaultFeatures.map((feature, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <Check className="w-4 h-4 text-purple-400 flex-shrink-0 mt-0.5" />
                        <span className="text-sm text-text-tertiary">{feature}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Error Message */}
                {error && (
                  <div className="flex items-center gap-2 p-3 bg-red-500/10 rounded-lg">
                    <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                    <p className="text-sm text-red-400">{error}</p>
                  </div>
                )}

                {/* Primary Action Button */}
                <button
                  onClick={handleSubscribe}
                  disabled={isLoading || !selectedPriceId || (!isCancelingSubscription && selectedOption?.is_active)}
                  className={cn(
                    'w-full py-3 rounded-xl font-medium transition-colors',
                    'bg-purple-500 text-white',
                    'hover:bg-purple-600',
                    'disabled:opacity-50 disabled:cursor-not-allowed'
                  )}
                >
                  {isLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Processing...
                    </span>
                  ) : isCancelingSubscription ? (
                    'Reactivate Subscription'
                  ) : selectedOption?.is_active ? (
                    'Current Plan'
                  ) : (
                    'Change Plan'
                  )}
                </button>

                {/* Secondary Actions */}
                <div className="pt-4 border-t border-bg-tertiary space-y-3">
                  <button
                    onClick={handleManagePayment}
                    disabled={isLoading}
                    className="w-full flex items-center justify-center gap-2 py-2.5 text-text-secondary hover:text-text-primary transition-colors"
                  >
                    <CreditCard className="w-4 h-4" />
                    <span className="text-sm">Manage Payment Method</span>
                  </button>

                  {!isCancelingSubscription && (
                    <button
                      onClick={() => setShowCancelConfirm(true)}
                      disabled={isLoading}
                      className="w-full py-2.5 text-sm text-red-400/70 hover:text-red-400 transition-colors"
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
          <div className="flex gap-1 p-1 bg-bg-tertiary rounded-xl">
            {periods.map((period) => (
              <button
                key={period}
                onClick={() => setSelectedPeriod(period)}
                className={cn(
                  'flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all',
                  selectedPeriod === period
                    ? 'bg-purple-500 text-white shadow-md'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-quaternary'
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
                <div className="w-10 h-10 mx-auto rounded-xl bg-blue-500/10 flex items-center justify-center mb-2">
                  <Mic className="w-5 h-5 text-blue-400" />
                </div>
                <p className="text-xl font-bold text-blue-400">
                  {usage ? formatDuration(usage.transcription_seconds) : '0m'}
                </p>
                <p className="text-xs text-text-quaternary">Listening</p>
              </div>
              <div className="text-center">
                <div className="w-10 h-10 mx-auto rounded-xl bg-green-500/10 flex items-center justify-center mb-2">
                  <MessageSquare className="w-5 h-5 text-green-400" />
                </div>
                <p className="text-xl font-bold text-green-400">
                  {usage ? formatNumber(usage.words_transcribed) : '0'}
                </p>
                <p className="text-xs text-text-quaternary">Words</p>
              </div>
              <div className="text-center">
                <div className="w-10 h-10 mx-auto rounded-xl bg-orange-500/10 flex items-center justify-center mb-2">
                  <Lightbulb className="w-5 h-5 text-orange-400" />
                </div>
                <p className="text-xl font-bold text-orange-400">
                  {usage?.insights_gained || 0}
                </p>
                <p className="text-xs text-text-quaternary">Insights</p>
              </div>
              <div className="text-center">
                <div className="w-10 h-10 mx-auto rounded-xl bg-purple-500/10 flex items-center justify-center mb-2">
                  <Brain className="w-5 h-5 text-purple-400" />
                </div>
                <p className="text-xl font-bold text-purple-400">
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
            ? `Your subscription will remain active until ${formatDate(subscription.current_period_end)}. After that, you'll be moved to the Free plan.`
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
// Integrations Section
// ============================================================================

function IntegrationsSection({
  integrations,
  onRefresh
}: {
  integrations: Integration[];
  onRefresh: () => Promise<void>;
}) {
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState<string | null>(null);

  const handleConnect = async (integration: Integration) => {
    if (integration.coming_soon || loadingId) return;

    setLoadingId(integration.id);
    try {
      const authUrl = await getIntegrationOAuthUrl(integration.id);
      if (authUrl) {
        // Open OAuth URL in new window
        window.open(authUrl, '_blank', 'width=600,height=700');
        // Note: User will complete OAuth in the popup, then we need to refresh
        // Set up a listener for when they return
        const checkConnection = setInterval(async () => {
          await onRefresh();
        }, 3000);
        // Stop checking after 2 minutes
        setTimeout(() => clearInterval(checkConnection), 120000);
      }
    } catch (error) {
      console.error('Failed to get OAuth URL:', error);
    } finally {
      setLoadingId(null);
    }
  };

  const handleDisconnect = async (integration: Integration) => {
    if (loadingId) return;

    setLoadingId(integration.id);
    setShowDisconnectConfirm(null);
    try {
      await disconnectIntegration(integration.id);
      await onRefresh();
    } catch (error) {
      console.error('Failed to disconnect:', error);
    } finally {
      setLoadingId(null);
    }
  };

  const handleToggle = (integration: Integration) => {
    if (integration.connected) {
      setShowDisconnectConfirm(integration.id);
    } else {
      handleConnect(integration);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {integrations.map((integration) => (
          <Card key={integration.id} className={cn(integration.coming_soon && 'opacity-60')}>
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl overflow-hidden bg-bg-tertiary flex items-center justify-center">
                {integration.icon.startsWith('/') ? (
                  <img
                    src={integration.icon}
                    alt={integration.name}
                    className="w-10 h-10 object-contain"
                  />
                ) : (
                  <Puzzle className="w-6 h-6" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="text-text-primary font-medium">{integration.name}</h3>
                  {integration.coming_soon && (
                    <span className="px-2 py-0.5 rounded-full text-xs bg-bg-tertiary text-text-tertiary">
                      Soon
                    </span>
                  )}
                  {integration.connected && !integration.coming_soon && (
                    <span className="px-2 py-0.5 rounded-full text-xs bg-green-500/20 text-green-400">
                      Connected
                    </span>
                  )}
                </div>
                <p className="text-sm text-text-tertiary truncate">{integration.description}</p>
              </div>
              {!integration.coming_soon && (
                loadingId === integration.id ? (
                  <Loader2 className="w-5 h-5 animate-spin text-text-tertiary" />
                ) : (
                  <Toggle
                    enabled={integration.connected}
                    onChange={() => handleToggle(integration)}
                  />
                )
              )}
            </div>
          </Card>
        ))}
      </div>

      {/* Disconnect Confirmation Dialog */}
      {showDisconnectConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-bg-secondary rounded-2xl p-6 max-w-md mx-4 shadow-xl">
            <h3 className="text-lg font-semibold text-text-primary mb-2">
              Disconnect {integrations.find(i => i.id === showDisconnectConfirm)?.name}?
            </h3>
            <p className="text-text-secondary mb-6">
              This will remove the connection. You can reconnect anytime.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowDisconnectConfirm(null)}
                className="px-4 py-2 rounded-lg bg-bg-tertiary text-text-primary hover:bg-bg-tertiary/80 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  const integration = integrations.find(i => i.id === showDisconnectConfirm);
                  if (integration) handleDisconnect(integration);
                }}
                className="px-4 py-2 rounded-lg bg-red-500 text-white hover:bg-red-600 transition-colors"
              >
                Disconnect
              </button>
            </div>
          </div>
        </div>
      )}
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

  const selectedScopes = Object.entries(scopes).filter(([, v]) => v).map(([k]) => k);
  const isReadOnly = scopes['conversations:read'] && scopes['memories:read'] && scopes['action_items:read'] &&
    !scopes['conversations:write'] && !scopes['memories:write'] && !scopes['action_items:write'];
  const isFullAccess = Object.values(scopes).every(v => v);

  const selectReadOnly = () => {
    setScopes({
      'conversations:read': true, 'conversations:write': false,
      'memories:read': true, 'memories:write': false,
      'action_items:read': true, 'action_items:write': false,
    });
  };

  const selectFullAccess = () => {
    setScopes(Object.fromEntries(Object.keys(scopes).map(k => [k, true])));
  };

  const handleCreate = async () => {
    if (!keyName.trim()) return;
    setIsCreating(true);
    const key = await onCreateKey(keyName.trim(), selectedScopes.length > 0 ? selectedScopes : undefined as unknown as string[]);
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
    setScopes(Object.fromEntries(Object.keys(scopes).map(k => [k, false])));
    setCreatedKey(null);
    setCopied(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={handleClose}>
      <div className="bg-bg-secondary rounded-2xl w-full max-w-md mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
        {createdKey ? (
          <div className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-xl bg-green-500/20">
                <Check className="w-6 h-6 text-green-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text-primary">API Key Created</h3>
                <p className="text-sm text-text-tertiary">Save this key now - you won&apos;t see it again!</p>
              </div>
            </div>
            <div className="p-4 rounded-xl bg-bg-tertiary mb-4">
              <p className="text-xs text-text-tertiary mb-2">Your API Key</p>
              <code className="text-sm text-text-primary font-mono break-all">{createdKey.key}</code>
            </div>
            <div className="flex gap-3">
              <button onClick={handleCopy} className={cn(
                'flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium transition-colors',
                copied ? 'bg-green-500/20 text-green-400' : 'bg-purple-500 text-white hover:bg-purple-600'
              )}>
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                {copied ? 'Copied!' : 'Copy Key'}
              </button>
              <button onClick={handleClose} className="px-4 py-3 rounded-xl bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary transition-colors">
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-text-primary">Create API Key</h3>
              <button onClick={handleClose} className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors">
                <X className="w-5 h-5 text-text-tertiary" />
              </button>
            </div>

            <div className="space-y-6">
              <div>
                <label className="block text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">Key Name</label>
                <input
                  type="text"
                  value={keyName}
                  onChange={e => setKeyName(e.target.value)}
                  placeholder="e.g., My App Integration"
                  className="w-full px-4 py-3 rounded-xl bg-bg-tertiary border border-white/[0.06] text-text-primary placeholder:text-text-quaternary focus:outline-none focus:border-purple-500"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-3">
                  <label className="text-xs font-semibold text-text-tertiary uppercase tracking-wider">Permissions</label>
                  <div className="flex gap-2">
                    <button onClick={selectReadOnly} className={cn(
                      'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                      isReadOnly ? 'bg-purple-500 text-white' : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary'
                    )}>Read Only</button>
                    <button onClick={selectFullAccess} className={cn(
                      'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                      isFullAccess ? 'bg-purple-500 text-white' : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary'
                    )}>Full Access</button>
                  </div>
                </div>

                <div className="space-y-2">
                  {['Conversations', 'Memories', 'Action Items'].map(resource => {
                    const readKey = `${resource.toLowerCase().replace(' ', '_')}:read`;
                    const writeKey = `${resource.toLowerCase().replace(' ', '_')}:write`;
                    return (
                      <div key={resource} className="flex items-center justify-between p-3 rounded-xl bg-bg-tertiary">
                        <span className="text-sm text-text-primary">{resource}</span>
                        <div className="flex bg-bg-quaternary rounded-lg overflow-hidden">
                          <button
                            onClick={() => setScopes({ ...scopes, [readKey]: !scopes[readKey] })}
                            className={cn(
                              'px-3 py-1.5 text-xs font-semibold transition-colors',
                              scopes[readKey] ? 'bg-blue-500 text-white' : 'text-text-quaternary hover:text-text-secondary'
                            )}
                          >R</button>
                          <button
                            onClick={() => setScopes({ ...scopes, [writeKey]: !scopes[writeKey] })}
                            className={cn(
                              'px-3 py-1.5 text-xs font-semibold transition-colors',
                              scopes[writeKey] ? 'bg-purple-500 text-white' : 'text-text-quaternary hover:text-text-secondary'
                            )}
                          >W</button>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <p className="text-xs text-text-quaternary mt-2">R = Read, W = Write. Defaults to read-only if nothing selected.</p>
              </div>

              <button
                onClick={handleCreate}
                disabled={!keyName.trim() || isCreating}
                className={cn(
                  'w-full py-3 rounded-xl font-medium transition-colors',
                  keyName.trim() && !isCreating
                    ? 'bg-purple-500 text-white hover:bg-purple-600'
                    : 'bg-bg-tertiary text-text-quaternary cursor-not-allowed'
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={handleClose}>
      <div className="bg-bg-secondary rounded-2xl w-full max-w-md mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
        {createdKey ? (
          <div className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-xl bg-green-500/20">
                <Check className="w-6 h-6 text-green-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text-primary">MCP Key Created</h3>
                <p className="text-sm text-text-tertiary">Save this key now - you won&apos;t see it again!</p>
              </div>
            </div>
            <div className="p-4 rounded-xl bg-bg-tertiary mb-4">
              <p className="text-xs text-text-tertiary mb-2">Your MCP Key</p>
              <code className="text-sm text-text-primary font-mono break-all">{createdKey.key}</code>
            </div>
            <div className="flex gap-3">
              <button onClick={handleCopy} className={cn(
                'flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium transition-colors',
                copied ? 'bg-green-500/20 text-green-400' : 'bg-purple-500 text-white hover:bg-purple-600'
              )}>
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                {copied ? 'Copied!' : 'Copy Key'}
              </button>
              <button onClick={handleClose} className="px-4 py-3 rounded-xl bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary transition-colors">
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-text-primary">Create MCP Key</h3>
              <button onClick={handleClose} className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors">
                <X className="w-5 h-5 text-text-tertiary" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">Key Name</label>
                <input
                  type="text"
                  value={keyName}
                  onChange={e => setKeyName(e.target.value)}
                  placeholder="e.g., Claude Desktop"
                  className="w-full px-4 py-3 rounded-xl bg-bg-tertiary border border-white/[0.06] text-text-primary placeholder:text-text-quaternary focus:outline-none focus:border-purple-500"
                />
              </div>
              <button
                onClick={handleCreate}
                disabled={!keyName.trim() || isCreating}
                className={cn(
                  'w-full py-3 rounded-xl font-medium transition-colors',
                  keyName.trim() && !isCreating
                    ? 'bg-purple-500 text-white hover:bg-purple-600'
                    : 'bg-bg-tertiary text-text-quaternary cursor-not-allowed'
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
  onDeleteKnowledgeGraph: () => void;
}) {
  const [showApiKeyDialog, setShowApiKeyDialog] = useState(false);
  const [showMcpKeyDialog, setShowMcpKeyDialog] = useState(false);
  const [showDeleteGraphDialog, setShowDeleteGraphDialog] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);

  // Experimental features (stored in localStorage)
  const [experimentalFeatures, setExperimentalFeatures] = useState({
    transcriptionDiagnostics: false,
    autoCreateSpeakers: false,
    followUpQuestions: false,
    goalTracker: false,
    dailyReflection: true,
  });

  // Load experimental features from localStorage on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('omi_experimental_features');
      if (saved) {
        try {
          setExperimentalFeatures(JSON.parse(saved));
        } catch {
          // Ignore parse errors
        }
      }
    }
  }, []);

  // Save experimental features to localStorage when they change
  const updateExperimentalFeature = (key: keyof typeof experimentalFeatures, value: boolean) => {
    const updated = { ...experimentalFeatures, [key]: value };
    setExperimentalFeatures(updated);
    if (typeof window !== 'undefined') {
      localStorage.setItem('omi_experimental_features', JSON.stringify(updated));
    }
  };

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
    { id: 'memory_created', label: 'Conversation Events', description: 'New conversation created', icon: MessageSquare },
    { id: 'transcript_received', label: 'Real-time Transcript', description: 'Transcript received', icon: FileText },
    { id: 'audio_bytes', label: 'Audio Bytes', description: 'Audio data received', icon: Radio, hasDelay: true },
    { id: 'day_summary', label: 'Day Summary', description: 'Summary generated', icon: Calendar },
  ];

  const mcpServerUrl = 'https://api.omi.me/v1/mcp/sse';

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
        <div id="api-keys" className="space-y-3 scroll-mt-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">Developer API Keys</h3>
          <button
            onClick={() => setShowApiKeyDialog(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-purple-500/10 text-purple-400 text-xs font-medium hover:bg-purple-500/20 transition-colors"
          >
            <Plus className="w-3 h-3" />
            Create Key
          </button>
        </div>
        <Card>
          {apiKeys.length > 0 ? (
            <div className="space-y-3">
              {apiKeys.map((apiKey) => (
                <div key={apiKey.id} className="flex items-center justify-between p-3 rounded-xl bg-bg-tertiary">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm text-text-primary font-medium">{apiKey.name}</span>
                      <code className="text-xs text-text-tertiary font-mono bg-bg-quaternary px-2 py-0.5 rounded">
                        {apiKey.key_prefix}...
                      </code>
                      {apiKey.scopes && apiKey.scopes.length > 0 && (
                        <span className="text-xs text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded">
                          {apiKey.scopes.length} scopes
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-text-quaternary mt-1">
                      Created {new Date(apiKey.created_at).toLocaleDateString()}
                      {apiKey.last_used_at && ` • Last used ${new Date(apiKey.last_used_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  <button
                    onClick={() => onDeleteApiKey(apiKey.id)}
                    className="p-2 rounded-lg text-text-secondary hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-text-quaternary text-center py-6">No API keys created yet</p>
          )}
        </Card>
      </div>

        {/* MCP Section */}
        <div id="mcp" className="space-y-3 scroll-mt-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">MCP</h3>
            <a href="https://docs.omi.me/doc/developer/MCP" target="_blank" rel="noopener noreferrer"
               className="text-xs text-purple-400 hover:text-purple-300 transition-colors">
              Docs ↗
            </a>
          </div>
          <button
            onClick={() => setShowMcpKeyDialog(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-purple-500/10 text-purple-400 text-xs font-medium hover:bg-purple-500/20 transition-colors"
          >
            <Plus className="w-3 h-3" />
            Create Key
          </button>
        </div>

        {/* MCP Keys List */}
        <Card>
          {mcpKeys.length > 0 ? (
            <div className="space-y-3">
              {mcpKeys.map((key) => (
                <div key={key.id} className="flex items-center justify-between p-3 rounded-xl bg-bg-tertiary">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-text-primary font-medium">{key.name}</span>
                      <code className="text-xs text-text-tertiary font-mono bg-bg-quaternary px-2 py-0.5 rounded">
                        {key.key_prefix}...
                      </code>
                    </div>
                    <p className="text-xs text-text-quaternary mt-1">
                      Created {new Date(key.created_at).toLocaleDateString()}
                      {key.last_used_at && ` • Last used ${new Date(key.last_used_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  <button
                    onClick={() => onDeleteMcpKey(key.id)}
                    className="p-2 rounded-lg text-text-secondary hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-text-quaternary text-center py-6">No MCP keys created yet</p>
          )}
        </Card>

        {/* Claude Desktop Config */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-bg-tertiary">
              <Monitor className="w-5 h-5 text-text-tertiary" />
            </div>
            <div>
              <p className="text-text-primary font-medium">Claude Desktop</p>
              <p className="text-xs text-text-tertiary">Add to claude_desktop_config.json</p>
            </div>
          </div>
          <div className="p-4 rounded-xl bg-[#0d0d0d] border border-white/[0.06] font-mono text-xs overflow-x-auto">
            <pre className="text-text-secondary whitespace-pre">{claudeDesktopConfig}</pre>
          </div>
          <button
            onClick={copyConfig}
            className={cn(
              'w-full mt-3 flex items-center justify-center gap-2 py-2.5 rounded-xl transition-colors',
              copiedConfig ? 'bg-green-500/20 text-green-400' : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary'
            )}
          >
            {copiedConfig ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copiedConfig ? 'Copied!' : 'Copy Config'}
          </button>
        </Card>

        {/* MCP Server Info */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-bg-tertiary">
              <Server className="w-5 h-5 text-text-tertiary" />
            </div>
            <div>
              <p className="text-text-primary font-medium">MCP Server</p>
              <p className="text-xs text-text-tertiary">Connect AI assistants to your data</p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <p className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">Server URL</p>
              <button
                onClick={copyUrl}
                className="w-full flex items-center justify-between p-3 rounded-xl bg-[#0d0d0d] border border-white/[0.06] hover:border-purple-500/50 transition-colors"
              >
                <code className="text-sm text-text-primary font-mono">{mcpServerUrl}</code>
                {copiedUrl ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4 text-text-quaternary" />}
              </button>
            </div>

            <div className="border-t border-white/[0.06] pt-4">
              <p className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">API Key Auth</p>
              <div className="flex items-center gap-4 text-sm">
                <span className="text-text-tertiary">Header</span>
                <code className="text-text-quaternary font-mono text-xs">Authorization: Bearer &lt;key&gt;</code>
              </div>
            </div>

            <div className="border-t border-white/[0.06] pt-4">
              <p className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">OAuth</p>
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-4">
                  <span className="text-text-tertiary w-24">Client ID</span>
                  <code className="text-text-primary font-mono">omi</code>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-text-tertiary w-24">Client Secret</span>
                  <span className="text-text-quaternary italic text-xs">Use your MCP API key</span>
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>

        {/* Webhooks */}
        <div id="webhooks" className="space-y-3 scroll-mt-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">Webhooks</h3>
          <a href="https://docs.omi.me/doc/developer/apps/Introduction" target="_blank" rel="noopener noreferrer"
             className="text-xs text-purple-400 hover:text-purple-300 transition-colors">
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
                  {index > 0 && <div className="border-t border-white/[0.06] my-4" />}
                  <div className="py-2">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-bg-tertiary">
                          <Icon className="w-4 h-4 text-text-tertiary" />
                        </div>
                        <div>
                          <p className="text-text-primary font-medium text-sm">{webhook.label}</p>
                          <p className="text-xs text-text-tertiary">{webhook.description}</p>
                        </div>
                      </div>
                      <Toggle
                        enabled={isEnabled}
                        onChange={(enabled) => onWebhookChange(
                          webhook.id,
                          enabled,
                          webhookUrls[webhook.id],
                          webhook.hasDelay ? audioBytesDelay : undefined
                        )}
                      />
                    </div>
                    {isEnabled && (
                      <div className="mt-3 space-y-2">
                        <input
                          type="url"
                          value={webhookUrls[webhook.id] || ''}
                          onChange={(e) => setWebhookUrls({ ...webhookUrls, [webhook.id]: e.target.value })}
                          onBlur={() => onWebhookChange(
                            webhook.id,
                            true,
                            webhookUrls[webhook.id],
                            webhook.hasDelay ? audioBytesDelay : undefined
                          )}
                          placeholder="https://your-server.com/webhook"
                          className="w-full px-3 py-2 rounded-lg bg-bg-tertiary border border-white/[0.06] text-text-primary text-sm placeholder:text-text-quaternary focus:outline-none focus:border-purple-500"
                        />
                        {webhook.hasDelay && (
                          <input
                            type="number"
                            value={audioBytesDelay}
                            onChange={(e) => setAudioBytesDelay(e.target.value)}
                            onBlur={() => onWebhookChange(webhook.id, true, webhookUrls[webhook.id], audioBytesDelay)}
                            placeholder="Interval (seconds)"
                            className="w-full px-3 py-2 rounded-lg bg-bg-tertiary border border-white/[0.06] text-text-primary text-sm placeholder:text-text-quaternary focus:outline-none focus:border-purple-500"
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
      <div id="data-management" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">Data Management</h3>
        <Card>
          <button
            onClick={onExportData}
            className="w-full flex items-center gap-4 py-3 text-text-primary hover:text-purple-400 transition-colors"
          >
            <div className="p-2 rounded-lg bg-bg-tertiary">
              <Download className="w-5 h-5 text-text-tertiary" />
            </div>
            <div className="flex-1 text-left">
              <p className="font-medium">Export All Data</p>
              <p className="text-xs text-text-tertiary">Export conversations to a JSON file</p>
            </div>
            <ExternalLink className="w-4 h-4 text-text-quaternary" />
          </button>
        </Card>
        <Card className="border-red-500/20">
          <button
            onClick={() => setShowDeleteGraphDialog(true)}
            className="w-full flex items-center gap-4 py-3 text-text-primary hover:text-red-400 transition-colors"
          >
            <div className="p-2 rounded-lg bg-red-500/10">
              <Network className="w-5 h-5 text-red-400" />
            </div>
            <div className="flex-1 text-left">
              <p className="font-medium">Delete Knowledge Graph</p>
              <p className="text-xs text-text-tertiary">Clear all nodes and connections</p>
            </div>
            <Trash2 className="w-4 h-4 text-text-quaternary" />
          </button>
        </Card>
      </div>

        {/* Experimental Features */}
        <div id="experimental" className="space-y-3 scroll-mt-4">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">Experimental</h3>
          <FlaskConical className="w-4 h-4 text-purple-400" />
        </div>
        <Card>
          <div className="space-y-1">
            {/* Transcription Diagnostics */}
            <div className="flex items-center justify-between py-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <Activity className="w-4 h-4 text-text-tertiary" />
                </div>
                <div>
                  <p className="text-text-primary font-medium text-sm">Transcription Diagnostics</p>
                  <p className="text-xs text-text-tertiary">Detailed diagnostic messages</p>
                </div>
              </div>
              <Toggle
                enabled={experimentalFeatures.transcriptionDiagnostics}
                onChange={(v) => updateExperimentalFeature('transcriptionDiagnostics', v)}
              />
            </div>

            {/* Auto-create Speakers */}
            <div className="flex items-center justify-between py-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <UserPlus className="w-4 h-4 text-text-tertiary" />
                </div>
                <div>
                  <p className="text-text-primary font-medium text-sm">Auto-create Speakers</p>
                  <p className="text-xs text-text-tertiary">Auto-create when name detected</p>
                </div>
              </div>
              <Toggle
                enabled={experimentalFeatures.autoCreateSpeakers}
                onChange={(v) => updateExperimentalFeature('autoCreateSpeakers', v)}
              />
            </div>

            {/* Follow-up Questions */}
            <div className="flex items-center justify-between py-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <Lightbulb className="w-4 h-4 text-text-tertiary" />
                </div>
                <div>
                  <p className="text-text-primary font-medium text-sm">Follow-up Questions</p>
                  <p className="text-xs text-text-tertiary">Suggest questions after conversations</p>
                </div>
              </div>
              <Toggle
                enabled={experimentalFeatures.followUpQuestions}
                onChange={(v) => updateExperimentalFeature('followUpQuestions', v)}
              />
            </div>

            {/* Goal Tracker */}
            <div className="flex items-center justify-between py-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <Target className="w-4 h-4 text-text-tertiary" />
                </div>
                <div>
                  <p className="text-text-primary font-medium text-sm">Goal Tracker</p>
                  <p className="text-xs text-text-tertiary">Track your personal goals on homepage</p>
                </div>
              </div>
              <Toggle
                enabled={experimentalFeatures.goalTracker}
                onChange={(v) => updateExperimentalFeature('goalTracker', v)}
              />
            </div>

            {/* Daily Reflection */}
            <div className="flex items-center justify-between py-3">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <Moon className="w-4 h-4 text-text-tertiary" />
                </div>
                <div>
                  <p className="text-text-primary font-medium text-sm">Daily Reflection</p>
                  <p className="text-xs text-text-tertiary">Get a 9 PM reminder to reflect on your day</p>
                </div>
              </div>
              <Toggle
                enabled={experimentalFeatures.dailyReflection}
                onChange={(v) => updateExperimentalFeature('dailyReflection', v)}
              />
            </div>
          </div>
        </Card>
      </div>

      {/* Links */}
      <Card>
        <a
          href="https://docs.omi.me"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-between py-3 text-text-primary hover:text-purple-400 transition-colors"
        >
          <div className="flex items-center gap-3">
            <BookOpen className="w-5 h-5 text-text-tertiary" />
            <span>API Documentation</span>
          </div>
          <ExternalLink className="w-4 h-4" />
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowDeleteGraphDialog(false)}>
          <div className="bg-bg-secondary rounded-2xl w-full max-w-md mx-4 p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-xl bg-red-500/20">
                <AlertTriangle className="w-6 h-6 text-red-400" />
              </div>
              <h3 className="text-lg font-semibold text-text-primary">Delete Knowledge Graph?</h3>
            </div>
            <p className="text-text-secondary text-sm mb-6">
              This will delete all derived knowledge graph data (nodes and connections). Your original memories will remain safe. The graph will be rebuilt over time.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowDeleteGraphDialog(false)}
                className="flex-1 py-3 rounded-xl bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  onDeleteKnowledgeGraph();
                  setShowDeleteGraphDialog(false);
                }}
                className="flex-1 py-3 rounded-xl bg-red-500 text-white hover:bg-red-600 transition-colors"
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

      {/* Account Actions */}
      <div id="actions" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">Account Actions</h3>
        <Card>
          <button
            onClick={onSignOut}
            className="w-full flex items-center gap-3 py-3 text-text-primary hover:text-purple-400 transition-colors"
          >
            <LogOut className="w-5 h-5" />
            <span className="font-medium">Sign Out</span>
          </button>
        </Card>

        <Card className="border-red-500/20">
          <button
            onClick={onDeleteAccount}
            className="w-full flex items-center gap-3 py-3 text-red-400 hover:text-red-300 transition-colors"
          >
            <Trash2 className="w-5 h-5" />
            <div className="text-left">
              <span className="font-medium block">Delete Account</span>
              <span className="text-sm text-red-400/70">Permanently delete your account and all data</span>
            </div>
          </button>
        </Card>
      </div>

      {/* Support */}
      <div id="support" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">Support</h3>
        <Card>
          <a
            href="https://feedback.omi.me"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between py-3 border-b border-white/[0.06] text-text-primary hover:text-purple-400 transition-colors"
          >
            <span>Feedback & Bug Reports</span>
            <ExternalLink className="w-4 h-4" />
          </a>
          <a
            href="https://help.omi.me"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between py-3 text-text-primary hover:text-purple-400 transition-colors"
          >
            <span>Help Center</span>
            <ExternalLink className="w-4 h-4" />
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
const SECTION_INFO: Record<SettingsSection, { title: string; description: string }> = {
  profile: { title: 'Profile', description: 'Account details, language, and notifications' },
  privacy: { title: 'Privacy', description: 'Data permissions and training settings' },
  integrations: { title: 'Integrations', description: 'Connected services and apps' },
  developer: { title: 'Developer', description: 'API keys, webhooks, and data export' },
  account: { title: 'Account', description: 'Plan, usage, and account management' },
};

export function SettingsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, signOut } = useAuth();

  // Get section from URL, default to 'profile'
  const sectionParam = searchParams.get('section');
  const activeSection: SettingsSection = (sectionParam && sectionParam in SECTION_INFO)
    ? (sectionParam as SettingsSection)
    : 'profile';

  // Track which sections have been loaded (using ref to avoid dependency issues)
  const loadedSectionsRef = useRef<Set<SettingsSection>>(new Set());
  const [sectionLoading, setSectionLoading] = useState<SettingsSection | null>(null);

  // Settings state - each section's data
  const [language, setLanguage] = useState('en');
  const [vocabulary, setVocabulary] = useState<string[]>([]);
  const [dailySummary, setDailySummary] = useState<DailySummarySettings>({ enabled: true, hour: 22 });
  const [recordingPermission, setRecordingPermissionState] = useState(false);
  const [trainingDataOptIn, setTrainingDataOptInState] = useState(false);
  const [allUsage, setAllUsage] = useState<AllUsageData | null>(null);
  const [subscription, setSubscription] = useState<UserSubscription | null>(null);
  const [cachedPlans, setCachedPlans] = useState<PricingOption[] | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [apiKeys, setApiKeys] = useState<DeveloperApiKey[]>([]);
  const [mcpKeys, setMcpKeys] = useState<McpApiKey[]>([]);
  const [webhooks, setWebhooks] = useState<DeveloperWebhooks>({});

  // Dialog states
  const [showSignOutDialog, setShowSignOutDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Load section data on demand
  useEffect(() => {
    const section = activeSection;
    if (loadedSectionsRef.current.has(section)) return;

    const loadSectionData = async () => {
      setSectionLoading(section);
      try {
        switch (section) {
          case 'profile':
            const [lang, vocab, summary] = await Promise.all([
              getUserLanguage().catch(() => 'en'),
              getCustomVocabulary().catch(() => []),
              getDailySummarySettings().catch(() => ({ enabled: true, hour: 22 })),
            ]);
            setLanguage(lang);
            setVocabulary(vocab);
            setDailySummary(summary);
            break;
          case 'privacy':
            const [recording, training] = await Promise.all([
              getRecordingPermission().catch(() => ({ enabled: false })),
              getTrainingDataOptIn().catch(() => ({ opted_in: false })),
            ]);
            setRecordingPermissionState(recording.enabled);
            setTrainingDataOptInState(training.opted_in);
            break;
          case 'account':
            const [usageData, sub, plansData] = await Promise.all([
              getAllUsageData().catch(() => null),
              getUserSubscription().catch(() => null),
              getAvailablePlans().catch(() => null),
            ]);
            setAllUsage(usageData);
            setSubscription(sub);
            if (plansData?.plans) {
              setCachedPlans(plansData.plans);
            }
            break;
          case 'integrations':
            const integ = await getIntegrations().catch(() => []);
            setIntegrations(integ);
            break;
          case 'developer':
            // Fetch API keys, MCP keys, webhook status, and individual webhook URLs in parallel
            // Note: Status API returns boolean fields, URL API returns {url: string}
            const [keys, mKeys, webhookStatus, memoryUrl, transcriptUrl, audioBytesUrl, daySummaryUrl] = await Promise.all([
              getDeveloperApiKeys().catch(() => []),
              getMcpApiKeys().catch(() => []),
              getDeveloperWebhooksStatus().catch(() => ({})),
              getDeveloperWebhook('memory_created').catch(() => ({ url: '' })),
              getDeveloperWebhook('realtime_transcript').catch(() => ({ url: '' })),
              getDeveloperWebhook('audio_bytes').catch(() => ({ url: '' })),
              getDeveloperWebhook('day_summary').catch(() => ({ url: '' })),
            ]);
            setApiKeys(keys);
            setMcpKeys(mKeys);
            // Combine status (booleans) with URLs
            const statusMap = webhookStatus as Record<string, boolean>;
            setWebhooks({
              memory_created: {
                url: memoryUrl?.url || '',
                enabled: statusMap['memory_created'] ?? false
              },
              transcript_received: {
                url: transcriptUrl?.url || '',
                enabled: statusMap['realtime_transcript'] ?? false
              },
              audio_bytes: {
                url: audioBytesUrl?.url || '',
                enabled: statusMap['audio_bytes'] ?? false
              },
              day_summary: {
                url: daySummaryUrl?.url || '',
                enabled: statusMap['day_summary'] ?? false
              },
            });
            break;
          // 'profile' and 'account' don't need API calls
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
    const newVocabulary = [...vocabulary, word];
    setVocabulary(newVocabulary);
    try {
      await updateCustomVocabulary(newVocabulary);
    } catch {
      setVocabulary(vocabulary);
    }
  };

  const handleRemoveWord = async (word: string) => {
    const newVocabulary = vocabulary.filter((w) => w !== word);
    setVocabulary(newVocabulary);
    try {
      await updateCustomVocabulary(newVocabulary);
    } catch {
      setVocabulary(vocabulary);
    }
  };

  const handleDailySummaryToggle = async (enabled: boolean) => {
    const oldSettings = dailySummary;
    setDailySummary({ ...dailySummary, enabled });
    try {
      await updateDailySummarySettings({ ...dailySummary, enabled });
    } catch {
      setDailySummary(oldSettings);
    }
  };

  const handleDailySummaryHourChange = async (hour: number) => {
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

  const handleCreateApiKey = async (name: string, scopes: string[]): Promise<DeveloperApiKey | null> => {
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
    try {
      const data = await exportAllData();
      const json = JSON.stringify(data, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'omi-export.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to export data:', error);
    }
  };

  const handleDeleteKnowledgeGraph = async () => {
    try {
      await deleteKnowledgeGraph();
    } catch (error) {
      console.error('Failed to delete knowledge graph:', error);
    }
  };

  const handleWebhookChange = async (type: string, enabled: boolean, url?: string, delay?: string) => {
    // Convert internal type names to API type names
    // UI uses 'transcript_received' but API expects 'realtime_transcript'
    const apiType = type === 'transcript_received' ? 'realtime_transcript' : type;
    const webhookType = apiType as 'memory_created' | 'realtime_transcript' | 'audio_bytes' | 'day_summary';
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
        [type]: { enabled, url: url || webhooks[type as keyof DeveloperWebhooks]?.url || '' },
      });
    } catch (error) {
      console.error('Failed to update webhook:', error);
    }
  };

  const handleSignOut = async () => {
    await signOut();
    router.push('/');
  };

  const handleDeleteAccount = async () => {
    setIsDeleting(true);
    try {
      await deleteAccount();
      await signOut();
      router.push('/');
    } catch {
      setIsDeleting(false);
    }
  };

  const renderSection = () => {
    // Show loading spinner when section is loading
    if (sectionLoading === activeSection) {
      return (
        <div className="h-64 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
        </div>
      );
    }

    switch (activeSection) {
      case 'profile':
        return (
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
        );
      case 'privacy':
        return (
          <PrivacySection
            recordingPermission={recordingPermission}
            trainingDataOptIn={trainingDataOptIn}
            onRecordingChange={handleRecordingPermissionChange}
            onTrainingDataChange={handleTrainingDataChange}
          />
        );
      case 'integrations':
        return (
          <IntegrationsSection
            integrations={integrations}
            onRefresh={async () => {
              const integ = await getIntegrations().catch(() => []);
              setIntegrations(integ);
            }}
          />
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
            onDeleteKnowledgeGraph={handleDeleteKnowledgeGraph}
          />
        );
      case 'account':
        return (
          <AccountSection
            allUsage={allUsage}
            subscription={subscription}
            cachedPlans={cachedPlans}
            onSubscriptionUpdate={refreshSubscription}
            onSignOut={() => setShowSignOutDialog(true)}
            onDeleteAccount={() => setShowDeleteDialog(true)}
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
      case 'profile':
        return [
          { id: 'account-info', label: 'Account' },
          { id: 'language', label: 'Language' },
          { id: 'vocabulary', label: 'Vocabulary' },
          { id: 'notifications', label: 'Notifications' },
        ];
      case 'account':
        return [
          { id: 'plan-usage', label: 'Plan & Usage' },
          { id: 'actions', label: 'Actions' },
          { id: 'support', label: 'Support' },
        ];
      case 'developer':
        return [
          { id: 'api-keys', label: 'API Keys' },
          { id: 'mcp', label: 'MCP' },
          { id: 'webhooks', label: 'Webhooks' },
          { id: 'data-management', label: 'Data' },
          { id: 'experimental', label: 'Experimental' },
        ];
      default:
        return [];
    }
  };

  const quickNavSections = getQuickNavSections();

  return (
    <div className="h-full flex flex-col">
      {/* Page Header */}
      <PageHeader title={sectionInfo.title} icon={Settings} showBackButton />

      {/* Main Content with optional Quick Nav */}
      <main className="flex-1 overflow-y-auto pb-12">
        <div className="max-w-4xl mx-auto px-6 lg:px-8 pt-6">
          <div className="flex gap-6">
            {/* Main content */}
            <div className="flex-1 min-w-0">
              {renderSection()}
            </div>

          {/* Quick Nav Sidebar - only show on desktop when there are sections */}
          {quickNavSections.length > 0 && (
            <div className="hidden lg:block w-32 flex-shrink-0">
              <div className="sticky top-4">
                <p className="text-xs font-medium text-text-quaternary uppercase tracking-wider mb-3">On this page</p>
                <nav className="space-y-1">
                  {quickNavSections.map((section) => (
                    <a
                      key={section.id}
                      href={`#${section.id}`}
                      className="block text-sm text-text-tertiary hover:text-text-primary transition-colors py-1"
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

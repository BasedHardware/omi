'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
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
} from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { cn } from '@/lib/utils';
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
} from '@/lib/api';
import { SUPPORTED_LANGUAGES, API_KEY_SCOPES } from '@/types/user';
import type { DailySummarySettings, UserUsage, UserSubscription, AllUsageData, DeveloperWebhooks, DeveloperApiKey, McpApiKey, Integration, UsageHistoryPoint } from '@/types/user';

// ============================================================================
// Types
// ============================================================================

type SettingsSection = 'profile' | 'language' | 'notifications' | 'privacy' | 'usage' | 'integrations' | 'developer' | 'account';

interface SectionNavItem {
  id: SettingsSection;
  label: string;
  icon: React.ReactNode;
}

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
        'relative w-12 h-7 rounded-full transition-all flex-shrink-0',
        enabled ? 'bg-purple-500' : 'bg-gray-600',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      <div
        className={cn(
          'absolute top-1 w-5 h-5 rounded-full bg-white transition-all shadow-md',
          enabled ? 'left-6' : 'left-1'
        )}
      />
    </button>
  );
}

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('bg-bg-secondary rounded-2xl border border-border-secondary p-5', className)}>
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
    <div className="flex items-center justify-between py-4 border-b border-border-secondary last:border-0">
      <div className="flex-1 min-w-0 mr-4">
        <p className="text-text-primary font-medium">{label}</p>
        {description && (
          <p className="text-sm text-text-tertiary mt-0.5">{description}</p>
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
          'flex items-center justify-between gap-2 px-4 py-2 rounded-xl',
          'bg-bg-tertiary border border-border-secondary',
          'text-text-primary min-w-[160px]',
          'hover:bg-bg-quaternary transition-colors'
        )}
      >
        <span className="truncate">{selectedOption?.label || placeholder}</span>
        <ChevronDown
          className={cn(
            'w-4 h-4 text-text-tertiary transition-transform',
            isOpen && 'rotate-180'
          )}
        />
      </button>

      {isOpen && (
        <div className="absolute z-50 w-full mt-2 py-2 rounded-xl bg-bg-secondary border border-border-secondary shadow-xl max-h-64 overflow-y-auto">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
              className={cn(
                'w-full px-4 py-2.5 text-left transition-colors flex items-center justify-between',
                option.value === value
                  ? 'bg-purple-500/20 text-white'
                  : 'text-text-primary hover:bg-bg-tertiary'
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
      <div className="relative bg-bg-secondary rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl border border-border-secondary">
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
// Section Navigation
// ============================================================================

const SECTIONS: SectionNavItem[] = [
  { id: 'profile', label: 'Profile', icon: <User className="w-5 h-5" /> },
  { id: 'language', label: 'Language', icon: <Globe className="w-5 h-5" /> },
  { id: 'notifications', label: 'Notifications', icon: <Bell className="w-5 h-5" /> },
  { id: 'privacy', label: 'Privacy', icon: <Shield className="w-5 h-5" /> },
  { id: 'usage', label: 'Plan & Usage', icon: <BarChart3 className="w-5 h-5" /> },
  { id: 'integrations', label: 'Integrations', icon: <Puzzle className="w-5 h-5" /> },
  { id: 'developer', label: 'Developer', icon: <Code className="w-5 h-5" /> },
  { id: 'account', label: 'Account', icon: <Settings className="w-5 h-5" /> },
];

function SectionNav({
  activeSection,
  onSectionChange,
}: {
  activeSection: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
}) {
  return (
    <nav className="space-y-1">
      {SECTIONS.map((section) => (
        <button
          key={section.id}
          onClick={() => onSectionChange(section.id)}
          className={cn(
            'w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-colors text-left',
            activeSection === section.id
              ? 'bg-purple-500/20 text-purple-400'
              : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
          )}
        >
          {section.icon}
          <span className="font-medium">{section.label}</span>
        </button>
      ))}
    </nav>
  );
}

// ============================================================================
// Profile Section
// ============================================================================

function ProfileSection({ user, onCopyUserId }: { user: any; onCopyUserId: () => void }) {
  const [copiedUserId, setCopiedUserId] = useState(false);

  const handleCopy = () => {
    onCopyUserId();
    setCopiedUserId(true);
    setTimeout(() => setCopiedUserId(false), 2000);
  };

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-text-primary">Profile</h2>

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
  );
}

// ============================================================================
// Language Section
// ============================================================================

function LanguageSection({
  language,
  vocabulary,
  onLanguageChange,
  onAddWord,
  onRemoveWord,
}: {
  language: string;
  vocabulary: string[];
  onLanguageChange: (lang: string) => void;
  onAddWord: (word: string) => void;
  onRemoveWord: (word: string) => void;
}) {
  const [newWord, setNewWord] = useState('');
  const languageOptions = SUPPORTED_LANGUAGES.map((l) => ({
    value: l.code,
    label: l.name,
  }));

  const handleAddWord = () => {
    if (newWord.trim()) {
      onAddWord(newWord.trim());
      setNewWord('');
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-text-primary">Language & Transcription</h2>

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

      <Card>
        <div className="space-y-4">
          <div>
            <h3 className="text-text-primary font-medium flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-purple-400" />
              Custom Vocabulary
            </h3>
            <p className="text-sm text-text-tertiary mt-1">
              Add words or phrases to improve transcription accuracy
            </p>
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={newWord}
              onChange={(e) => setNewWord(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAddWord()}
              placeholder="Enter a word or phrase"
              className={cn(
                'flex-1 px-4 py-2.5 rounded-xl',
                'bg-bg-tertiary border border-border-secondary',
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
  );
}

// ============================================================================
// Notifications Section
// ============================================================================

function NotificationsSection({
  dailySummary,
  onToggle,
  onHourChange,
}: {
  dailySummary: DailySummarySettings;
  onToggle: (enabled: boolean) => void;
  onHourChange: (hour: number) => void;
}) {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-text-primary">Notifications</h2>

      <Card>
        <SettingRow
          label="Daily Summary"
          description="Receive a daily digest of your action items"
        >
          <Toggle enabled={dailySummary.enabled} onChange={onToggle} />
        </SettingRow>

        {dailySummary.enabled && (
          <SettingRow
            label="Delivery Time"
            description="When to receive your daily summary"
          >
            <HourPicker value={dailySummary.hour} onChange={onHourChange} />
          </SettingRow>
        )}
      </Card>
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
      <h2 className="text-xl font-semibold text-text-primary">Privacy & Data</h2>

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
  const [visibleMetrics, setVisibleMetrics] = useState({
    listening: true,
    words: true,
    insights: true,
    memories: true,
  });

  if (!history || history.length === 0) {
    return (
      <Card className="h-48 flex items-center justify-center">
        <p className="text-text-quaternary">No activity data available</p>
      </Card>
    );
  }

  // For all_time with many data points, aggregate by month
  let dataToProcess = history;
  if (period === 'all_time' && history.length > 60) {
    // Group by year-month and aggregate
    const monthlyData = new Map<string, UsageHistoryPoint>();
    history.forEach(point => {
      const date = new Date(point.date);
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
      const existing = monthlyData.get(key);
      if (existing) {
        monthlyData.set(key, {
          date: `${key}-01`,
          transcription_seconds: existing.transcription_seconds + point.transcription_seconds,
          words_transcribed: existing.words_transcribed + point.words_transcribed,
          insights_gained: existing.insights_gained + point.insights_gained,
          memories_created: existing.memories_created + point.memories_created,
        });
      } else {
        monthlyData.set(key, { ...point, date: `${key}-01` });
      }
    });
    dataToProcess = Array.from(monthlyData.values()).sort((a, b) => a.date.localeCompare(b.date));
  }

  // Process history data for display
  const processedData = dataToProcess.map((point, index) => {
    const date = new Date(point.date);
    let label = '';
    if (period === 'today') {
      label = `${date.getHours()}:00`;
    } else if (period === 'monthly') {
      label = `${date.getDate()}`;
    } else if (period === 'yearly') {
      label = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][date.getMonth()];
    } else {
      // For all_time, show "Mon 'YY" format
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      label = `${months[date.getMonth()]} '${String(date.getFullYear()).slice(2)}`;
    }
    return { ...point, label, index };
  });

  // Find max values for scaling
  const maxListening = Math.max(...processedData.map(d => d.transcription_seconds / 60), 1);
  const maxWords = Math.max(...processedData.map(d => d.words_transcribed), 1);
  const maxInsights = Math.max(...processedData.map(d => d.insights_gained), 1);
  const maxMemories = Math.max(...processedData.map(d => d.memories_created), 1);

  const metricConfig = [
    { key: 'listening', color: 'rgb(96, 165, 250)', label: 'Listening', visible: visibleMetrics.listening },
    { key: 'words', color: 'rgb(74, 222, 128)', label: 'Words', visible: visibleMetrics.words },
    { key: 'insights', color: 'rgb(251, 146, 60)', label: 'Insights', visible: visibleMetrics.insights },
    { key: 'memories', color: 'rgb(192, 132, 252)', label: 'Memories', visible: visibleMetrics.memories },
  ];

  const toggleMetric = (key: string) => {
    setVisibleMetrics(prev => ({ ...prev, [key]: !prev[key as keyof typeof prev] }));
  };

  // Create SVG path for each metric
  const createPath = (data: UsageHistoryPoint[], getValue: (d: UsageHistoryPoint) => number, max: number) => {
    const width = 100;
    const height = 100;
    const points = data.map((d, i) => {
      const x = (i / (data.length - 1 || 1)) * width;
      const y = height - (getValue(d) / max) * height;
      return `${x},${y}`;
    });
    return `M ${points.join(' L ')}`;
  };

  return (
    <Card>
      {/* Legend/Toggles */}
      <div className="flex flex-wrap gap-2 mb-4">
        {metricConfig.map(metric => (
          <button
            key={metric.key}
            onClick={() => toggleMetric(metric.key)}
            className={cn(
              'px-3 py-1.5 rounded-full text-xs font-medium transition-all',
              metric.visible
                ? 'opacity-100'
                : 'opacity-40'
            )}
            style={{
              backgroundColor: metric.visible ? `${metric.color}20` : 'transparent',
              color: metric.color,
              border: `1px solid ${metric.color}40`,
            }}
          >
            {metric.label}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div className="relative h-40 w-full">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
          {/* Grid lines */}
          <line x1="0" y1="25" x2="100" y2="25" stroke="rgba(255,255,255,0.1)" strokeWidth="0.5" />
          <line x1="0" y1="50" x2="100" y2="50" stroke="rgba(255,255,255,0.1)" strokeWidth="0.5" />
          <line x1="0" y1="75" x2="100" y2="75" stroke="rgba(255,255,255,0.1)" strokeWidth="0.5" />
          <line x1="0" y1="100" x2="100" y2="100" stroke="rgba(255,255,255,0.2)" strokeWidth="0.5" />

          {/* Lines */}
          {visibleMetrics.listening && (
            <>
              <defs>
                <linearGradient id="listeningGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgb(96, 165, 250)" stopOpacity="0.3" />
                  <stop offset="100%" stopColor="rgb(96, 165, 250)" stopOpacity="0" />
                </linearGradient>
              </defs>
              <path
                d={createPath(processedData, d => d.transcription_seconds / 60, maxListening)}
                fill="none"
                stroke="rgb(96, 165, 250)"
                strokeWidth="2"
                vectorEffect="non-scaling-stroke"
              />
            </>
          )}
          {visibleMetrics.words && (
            <path
              d={createPath(processedData, d => d.words_transcribed, maxWords)}
              fill="none"
              stroke="rgb(74, 222, 128)"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
            />
          )}
          {visibleMetrics.insights && (
            <path
              d={createPath(processedData, d => d.insights_gained, maxInsights)}
              fill="none"
              stroke="rgb(251, 146, 60)"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
            />
          )}
          {visibleMetrics.memories && (
            <path
              d={createPath(processedData, d => d.memories_created, maxMemories)}
              fill="none"
              stroke="rgb(192, 132, 252)"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
      </div>

      {/* X-axis labels */}
      <div className="flex justify-between mt-2 text-xs text-text-quaternary">
        {processedData.filter((_, i) => {
          const step = Math.ceil(processedData.length / 6);
          return i % step === 0 || i === processedData.length - 1;
        }).map((d, i) => (
          <span key={i}>{d.label}</span>
        ))}
      </div>
    </Card>
  );
}

function UsageSection({
  allUsage,
  subscription,
}: {
  allUsage: AllUsageData | null;
  subscription: UserSubscription | null;
}) {
  const [selectedPeriod, setSelectedPeriod] = useState<UsagePeriod>('all_time');

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

  const getPlanBadgeColor = (plan: string) => {
    switch (plan?.toLowerCase()) {
      case 'pro':
        return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
      case 'unlimited':
        return 'bg-gradient-to-r from-purple-500/20 to-pink-500/20 text-purple-300 border-purple-500/30';
      default:
        return 'bg-bg-tertiary text-text-secondary border-border-secondary';
    }
  };

  const getPlanDisplayName = (plan: string) => {
    if (plan === 'unlimited') return 'Unlimited';
    if (plan === 'basic') return 'Free';
    return plan || 'Free';
  };

  // Get usage for selected period
  const usage = allUsage ? allUsage[selectedPeriod] : null;
  const periods: UsagePeriod[] = ['today', 'monthly', 'yearly', 'all_time'];

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-text-primary">Plan & Usage</h2>

      {/* Plan Card */}
      <Card className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-purple-500/5 to-pink-500/5" />
        <div className="relative">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-text-tertiary text-sm">Current Plan</p>
              <div className="flex items-center gap-2 mt-1">
                <h3 className="text-2xl font-bold text-text-primary">
                  {getPlanDisplayName(subscription?.plan || '')}
                </h3>
                {subscription?.is_unlimited && (
                  <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium border', getPlanBadgeColor('unlimited'))}>
                    PRO
                  </span>
                )}
              </div>
            </div>
            {!subscription?.is_unlimited && (
              <button
                className={cn(
                  'px-4 py-2 rounded-xl font-medium',
                  'bg-purple-500 text-white',
                  'hover:bg-purple-600 transition-colors'
                )}
              >
                Upgrade
              </button>
            )}
          </div>
        </div>
      </Card>

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

      {/* Usage Chart */}
      <UsageChart history={usage?.history} period={selectedPeriod} />

      {/* Usage Stats - 2x2 Grid */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-blue-500/10">
              <Clock className="w-5 h-5 text-blue-400" />
            </div>
            <span className="text-text-tertiary text-sm">Listening</span>
          </div>
          <p className="text-3xl font-bold text-blue-400">
            {usage ? formatDuration(usage.transcription_seconds) : '0m'}
          </p>
          <p className="text-text-quaternary text-sm mt-1">Time listening</p>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-green-500/10">
              <MessageSquare className="w-5 h-5 text-green-400" />
            </div>
            <span className="text-text-tertiary text-sm">Understanding</span>
          </div>
          <p className="text-3xl font-bold text-green-400">
            {usage ? formatNumber(usage.words_transcribed) : '0'}
          </p>
          <p className="text-text-quaternary text-sm mt-1">Words transcribed</p>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-orange-500/10">
              <BarChart3 className="w-5 h-5 text-orange-400" />
            </div>
            <span className="text-text-tertiary text-sm">Insights</span>
          </div>
          <p className="text-3xl font-bold text-orange-400">
            {usage?.insights_gained || 0}
          </p>
          <p className="text-text-quaternary text-sm mt-1">Insights gained</p>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-purple-500/10">
              <Brain className="w-5 h-5 text-purple-400" />
            </div>
            <span className="text-text-tertiary text-sm">Memories</span>
          </div>
          <p className="text-3xl font-bold text-purple-400">
            {usage?.memories_created || 0}
          </p>
          <p className="text-text-quaternary text-sm mt-1">Memories created</p>
        </Card>
      </div>
    </div>
  );
}

// ============================================================================
// Integrations Section
// ============================================================================

function IntegrationsSection({ integrations }: { integrations: Integration[] }) {
  const getIntegrationIcon = (icon: string) => {
    switch (icon) {
      case 'notion':
        return <div className="w-6 h-6 bg-white rounded flex items-center justify-center text-black text-xs font-bold">N</div>;
      case 'github':
        return <Github className="w-6 h-6" />;
      case 'calendar':
        return <Calendar className="w-6 h-6 text-blue-400" />;
      case 'twitter':
        return <Twitter className="w-6 h-6 text-blue-400" />;
      default:
        return <Puzzle className="w-6 h-6" />;
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-text-primary">Integrations</h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {integrations.map((integration) => (
          <Card key={integration.id} className={cn(integration.coming_soon && 'opacity-60')}>
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-bg-tertiary flex items-center justify-center">
                {getIntegrationIcon(integration.icon)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="text-text-primary font-medium">{integration.name}</h3>
                  {integration.coming_soon && (
                    <span className="px-2 py-0.5 rounded-full text-xs bg-bg-tertiary text-text-tertiary">
                      Soon
                    </span>
                  )}
                </div>
                <p className="text-sm text-text-tertiary truncate">{integration.description}</p>
              </div>
              {!integration.coming_soon && (
                <Toggle
                  enabled={integration.connected}
                  onChange={() => {}}
                  disabled={integration.coming_soon}
                />
              )}
            </div>
          </Card>
        ))}
      </div>
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
                  className="w-full px-4 py-3 rounded-xl bg-bg-tertiary border border-border-secondary text-text-primary placeholder:text-text-quaternary focus:outline-none focus:border-purple-500"
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
                  className="w-full px-4 py-3 rounded-xl bg-bg-tertiary border border-border-secondary text-text-primary placeholder:text-text-quaternary focus:outline-none focus:border-purple-500"
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
      <h2 className="text-xl font-semibold text-text-primary">Developer</h2>

      {/* Data Management */}
      <div className="space-y-3">
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

      {/* Developer API Keys */}
      <div className="space-y-3">
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
      <div className="space-y-3">
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
          <div className="p-4 rounded-xl bg-[#0d0d0d] border border-border-secondary font-mono text-xs overflow-x-auto">
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
                className="w-full flex items-center justify-between p-3 rounded-xl bg-[#0d0d0d] border border-border-secondary hover:border-purple-500/50 transition-colors"
              >
                <code className="text-sm text-text-primary font-mono">{mcpServerUrl}</code>
                {copiedUrl ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4 text-text-quaternary" />}
              </button>
            </div>

            <div className="border-t border-border-secondary pt-4">
              <p className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">API Key Auth</p>
              <div className="flex items-center gap-4 text-sm">
                <span className="text-text-tertiary">Header</span>
                <code className="text-text-quaternary font-mono text-xs">Authorization: Bearer &lt;key&gt;</code>
              </div>
            </div>

            <div className="border-t border-border-secondary pt-4">
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
      <div className="space-y-3">
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
                  {index > 0 && <div className="border-t border-border-secondary my-4" />}
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
                          className="w-full px-3 py-2 rounded-lg bg-bg-tertiary border border-border-secondary text-text-primary text-sm placeholder:text-text-quaternary focus:outline-none focus:border-purple-500"
                        />
                        {webhook.hasDelay && (
                          <input
                            type="number"
                            value={audioBytesDelay}
                            onChange={(e) => setAudioBytesDelay(e.target.value)}
                            onBlur={() => onWebhookChange(webhook.id, true, webhookUrls[webhook.id], audioBytesDelay)}
                            placeholder="Interval (seconds)"
                            className="w-full px-3 py-2 rounded-lg bg-bg-tertiary border border-border-secondary text-text-primary text-sm placeholder:text-text-quaternary focus:outline-none focus:border-purple-500"
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

      {/* Experimental Features */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">Experimental</h3>
          <FlaskConical className="w-4 h-4 text-purple-400" />
        </div>
        <Card>
          <div className="space-y-1">
            {/* Transcription Diagnostics */}
            <div className="flex items-center justify-between py-3 border-b border-border-secondary">
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
            <div className="flex items-center justify-between py-3 border-b border-border-secondary">
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
            <div className="flex items-center justify-between py-3 border-b border-border-secondary">
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
            <div className="flex items-center justify-between py-3 border-b border-border-secondary">
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
  onSignOut,
  onDeleteAccount,
}: {
  onSignOut: () => void;
  onDeleteAccount: () => void;
}) {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-text-primary">Account</h2>

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

      {/* External Links */}
      <Card>
        <a
          href="https://feedback.omi.me"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-between py-3 border-b border-border-secondary text-text-primary hover:text-purple-400 transition-colors"
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
  );
}

// ============================================================================
// Main Settings Page Component
// ============================================================================

export function SettingsPage() {
  const router = useRouter();
  const { user, signOut } = useAuth();
  const [activeSection, setActiveSection] = useState<SettingsSection>('profile');

  // Track which sections have been loaded (using ref to avoid dependency issues)
  const loadedSectionsRef = useRef<Set<SettingsSection>>(new Set(['profile', 'account']));
  const [sectionLoading, setSectionLoading] = useState<SettingsSection | null>(null);

  // Settings state - each section's data
  const [language, setLanguage] = useState('en');
  const [vocabulary, setVocabulary] = useState<string[]>([]);
  const [dailySummary, setDailySummary] = useState<DailySummarySettings>({ enabled: true, hour: 22 });
  const [recordingPermission, setRecordingPermissionState] = useState(false);
  const [trainingDataOptIn, setTrainingDataOptInState] = useState(false);
  const [allUsage, setAllUsage] = useState<AllUsageData | null>(null);
  const [subscription, setSubscription] = useState<UserSubscription | null>(null);
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
          case 'language':
            const [lang, vocab] = await Promise.all([
              getUserLanguage().catch(() => 'en'),
              getCustomVocabulary().catch(() => []),
            ]);
            setLanguage(lang);
            setVocabulary(vocab);
            break;
          case 'notifications':
            const summary = await getDailySummarySettings().catch(() => ({ enabled: true, hour: 22 }));
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
          case 'usage':
            const [usageData, sub] = await Promise.all([
              getAllUsageData().catch(() => null),
              getUserSubscription().catch(() => null),
            ]);
            setAllUsage(usageData);
            setSubscription(sub);
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
        return <ProfileSection user={user} onCopyUserId={handleCopyUserId} />;
      case 'language':
        return (
          <LanguageSection
            language={language}
            vocabulary={vocabulary}
            onLanguageChange={handleLanguageChange}
            onAddWord={handleAddWord}
            onRemoveWord={handleRemoveWord}
          />
        );
      case 'notifications':
        return (
          <NotificationsSection
            dailySummary={dailySummary}
            onToggle={handleDailySummaryToggle}
            onHourChange={handleDailySummaryHourChange}
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
      case 'usage':
        return <UsageSection allUsage={allUsage} subscription={subscription} />;
      case 'integrations':
        return <IntegrationsSection integrations={integrations} />;
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
            onSignOut={() => setShowSignOutDialog(true)}
            onDeleteAccount={() => setShowDeleteDialog(true)}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="h-full flex">
      {/* Sidebar Navigation - Hidden on mobile */}
      <aside className="hidden lg:block w-64 flex-shrink-0 border-r border-border-secondary p-6">
        <h1 className="text-xl font-bold text-text-primary mb-6 flex items-center gap-2">
          <Settings className="w-6 h-6" />
          Settings
        </h1>
        <SectionNav activeSection={activeSection} onSectionChange={setActiveSection} />
      </aside>

      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-20 bg-bg-primary border-b border-border-secondary p-4">
        <select
          value={activeSection}
          onChange={(e) => setActiveSection(e.target.value as SettingsSection)}
          className="w-full px-4 py-3 rounded-xl bg-bg-secondary border border-border-secondary text-text-primary"
        >
          {SECTIONS.map((section) => (
            <option key={section.id} value={section.id}>
              {section.label}
            </option>
          ))}
        </select>
      </div>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto p-6 lg:p-10 pt-20 lg:pt-10">
        <div className="max-w-2xl">
          {renderSection()}
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

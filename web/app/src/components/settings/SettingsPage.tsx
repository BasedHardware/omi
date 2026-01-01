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
} from '@/lib/api';
import { SUPPORTED_LANGUAGES } from '@/types/user';
import type { DailySummarySettings } from '@/types/user';

// Toggle Switch Component
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
        'relative w-12 h-7 rounded-full transition-all',
        enabled ? 'bg-purple-400' : 'bg-gray-600',
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

// Section Component
function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
          {icon}
        </div>
        <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
      </div>
      <div className="space-y-3 pl-11">{children}</div>
    </section>
  );
}

// Setting Row Component
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
    <div className="flex items-center justify-between p-4 bg-bg-secondary rounded-xl border border-border-secondary">
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

// Custom Dropdown Component
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

// Hour Picker Component
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

// Confirm Dialog Component
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

export function SettingsPage() {
  const router = useRouter();
  const { user, signOut } = useAuth();
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [copiedUserId, setCopiedUserId] = useState(false);

  // Settings state
  const [language, setLanguage] = useState('en');
  const [dailySummary, setDailySummary] = useState<DailySummarySettings>({
    enabled: true,
    hour: 22,
  });
  const [recordingPermission, setRecordingPermissionState] = useState(false);
  const [trainingDataOptIn, setTrainingDataOptInState] = useState(false);

  // Dialog states
  const [showSignOutDialog, setShowSignOutDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Load settings
  useEffect(() => {
    async function loadSettings() {
      setIsLoading(true);
      try {
        const [lang, summary, recording, training] = await Promise.all([
          getUserLanguage().catch(() => 'en'),
          getDailySummarySettings().catch(() => ({ enabled: true, hour: 22 })),
          getRecordingPermission().catch(() => ({ enabled: false })),
          getTrainingDataOptIn().catch(() => ({ opted_in: false })),
        ]);
        setLanguage(lang);
        setDailySummary(summary);
        setRecordingPermissionState(recording.enabled);
        setTrainingDataOptInState(training.opted_in);
      } catch (error) {
        console.error('Failed to load settings:', error);
      } finally {
        setIsLoading(false);
      }
    }
    loadSettings();
  }, []);

  // Handlers
  const handleLanguageChange = async (newLanguage: string) => {
    const oldLanguage = language;
    setLanguage(newLanguage);
    try {
      await setUserLanguage(newLanguage);
    } catch (error) {
      console.error('Failed to update language:', error);
      setLanguage(oldLanguage);
    }
  };

  const handleDailySummaryToggle = async (enabled: boolean) => {
    const oldSettings = dailySummary;
    setDailySummary({ ...dailySummary, enabled });
    try {
      await updateDailySummarySettings({ ...dailySummary, enabled });
    } catch (error) {
      console.error('Failed to update daily summary:', error);
      setDailySummary(oldSettings);
    }
  };

  const handleDailySummaryHourChange = async (hour: number) => {
    const oldSettings = dailySummary;
    setDailySummary({ ...dailySummary, hour });
    try {
      await updateDailySummarySettings({ ...dailySummary, hour });
    } catch (error) {
      console.error('Failed to update daily summary hour:', error);
      setDailySummary(oldSettings);
    }
  };

  const handleRecordingPermissionChange = async (enabled: boolean) => {
    const oldValue = recordingPermission;
    setRecordingPermissionState(enabled);
    try {
      await setRecordingPermission(enabled);
    } catch (error) {
      console.error('Failed to update recording permission:', error);
      setRecordingPermissionState(oldValue);
    }
  };

  const handleTrainingDataChange = async (optIn: boolean) => {
    const oldValue = trainingDataOptIn;
    setTrainingDataOptInState(optIn);
    try {
      await setTrainingDataOptIn(optIn);
    } catch (error) {
      console.error('Failed to update training data opt-in:', error);
      setTrainingDataOptInState(oldValue);
    }
  };

  const handleCopyUserId = () => {
    if (user?.uid) {
      navigator.clipboard.writeText(user.uid);
      setCopiedUserId(true);
      setTimeout(() => setCopiedUserId(false), 2000);
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
    } catch (error) {
      console.error('Failed to delete account:', error);
      setIsDeleting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-purple-primary animate-spin" />
      </div>
    );
  }

  const languageOptions = SUPPORTED_LANGUAGES.map((l) => ({
    value: l.code,
    label: l.name,
  }));

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-8">
      {/* Header */}
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
      </div>

      {/* Profile Section */}
      <Section title="Profile" icon={<User className="w-5 h-5" />}>
        {/* User Info Card */}
        <div className="p-4 bg-bg-secondary rounded-xl border border-border-secondary">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full overflow-hidden bg-bg-tertiary ring-2 ring-purple-500/20">
              {user?.photoURL ? (
                <Image
                  src={user.photoURL}
                  alt={user.displayName || 'User'}
                  width={64}
                  height={64}
                  className="object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-text-tertiary text-xl font-medium">
                  {user?.displayName?.charAt(0) || 'U'}
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-lg font-semibold text-text-primary truncate">
                {user?.displayName || 'User'}
              </p>
              <p className="text-sm text-text-tertiary truncate">{user?.email}</p>
            </div>
          </div>
        </div>

        {/* User ID */}
        <div className="flex items-center justify-between p-4 bg-bg-secondary rounded-xl border border-border-secondary">
          <div className="flex-1 min-w-0 mr-4">
            <p className="text-text-primary font-medium">User ID</p>
            <p className="text-sm text-text-tertiary font-mono truncate">
              {user?.uid}
            </p>
          </div>
          <button
            onClick={handleCopyUserId}
            className={cn(
              'p-2 rounded-lg transition-colors',
              copiedUserId
                ? 'bg-green-500/10 text-green-400'
                : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary'
            )}
          >
            {copiedUserId ? (
              <Check className="w-5 h-5" />
            ) : (
              <Copy className="w-5 h-5" />
            )}
          </button>
        </div>

        {/* Language */}
        <SettingRow
          label="Primary Language"
          description="Language used for transcription"
        >
          <Dropdown
            value={language}
            options={languageOptions}
            onChange={handleLanguageChange}
          />
        </SettingRow>
      </Section>

      {/* Notifications Section */}
      <Section title="Notifications" icon={<Bell className="w-5 h-5" />}>
        <SettingRow
          label="Daily Summary"
          description="Receive a daily digest of your action items"
        >
          <Toggle
            enabled={dailySummary.enabled}
            onChange={handleDailySummaryToggle}
          />
        </SettingRow>

        {dailySummary.enabled && (
          <SettingRow
            label="Delivery Time"
            description="When to receive your daily summary"
          >
            <HourPicker
              value={dailySummary.hour}
              onChange={handleDailySummaryHourChange}
            />
          </SettingRow>
        )}
      </Section>

      {/* Privacy Section */}
      <Section title="Privacy" icon={<Shield className="w-5 h-5" />}>
        <SettingRow
          label="Store Recordings"
          description="Allow storing audio recordings for improved accuracy"
        >
          <Toggle
            enabled={recordingPermission}
            onChange={handleRecordingPermissionChange}
          />
        </SettingRow>

        <SettingRow
          label="Training Data"
          description="Help improve Omi by contributing anonymous usage data"
        >
          <Toggle
            enabled={trainingDataOptIn}
            onChange={handleTrainingDataChange}
          />
        </SettingRow>
      </Section>

      {/* Developer Section */}
      <Section title="Developer" icon={<Code className="w-5 h-5" />}>
        <a
          href="https://docs.omi.me"
          target="_blank"
          rel="noopener noreferrer"
          className={cn(
            'flex items-center justify-between p-4 bg-bg-secondary rounded-xl border border-border-secondary',
            'hover:bg-bg-tertiary transition-colors'
          )}
        >
          <div>
            <p className="text-text-primary font-medium">API Documentation</p>
            <p className="text-sm text-text-tertiary">
              Learn how to integrate with Omi
            </p>
          </div>
          <ExternalLink className="w-5 h-5 text-text-tertiary" />
        </a>

        <a
          href="https://feedback.omi.me"
          target="_blank"
          rel="noopener noreferrer"
          className={cn(
            'flex items-center justify-between p-4 bg-bg-secondary rounded-xl border border-border-secondary',
            'hover:bg-bg-tertiary transition-colors'
          )}
        >
          <div>
            <p className="text-text-primary font-medium">Feedback & Bug Reports</p>
            <p className="text-sm text-text-tertiary">
              Help us improve Omi
            </p>
          </div>
          <ExternalLink className="w-5 h-5 text-text-tertiary" />
        </a>

        <a
          href="https://help.omi.me"
          target="_blank"
          rel="noopener noreferrer"
          className={cn(
            'flex items-center justify-between p-4 bg-bg-secondary rounded-xl border border-border-secondary',
            'hover:bg-bg-tertiary transition-colors'
          )}
        >
          <div>
            <p className="text-text-primary font-medium">Help Center</p>
            <p className="text-sm text-text-tertiary">
              Get help with Omi
            </p>
          </div>
          <ExternalLink className="w-5 h-5 text-text-tertiary" />
        </a>
      </Section>

      {/* Account Section */}
      <Section title="Account" icon={<User className="w-5 h-5" />}>
        <button
          onClick={() => setShowSignOutDialog(true)}
          className={cn(
            'w-full flex items-center justify-between p-4 bg-bg-secondary rounded-xl border border-border-secondary',
            'hover:bg-bg-tertiary transition-colors'
          )}
        >
          <div className="flex items-center gap-3">
            <LogOut className="w-5 h-5 text-text-secondary" />
            <p className="text-text-primary font-medium">Sign Out</p>
          </div>
        </button>

        <button
          onClick={() => setShowDeleteDialog(true)}
          className={cn(
            'w-full flex items-center justify-between p-4 rounded-xl',
            'bg-red-500/10 border border-red-500/20',
            'hover:bg-red-500/20 transition-colors'
          )}
        >
          <div className="flex items-center gap-3">
            <Trash2 className="w-5 h-5 text-red-400" />
            <div className="text-left">
              <p className="text-red-400 font-medium">Delete Account</p>
              <p className="text-sm text-red-400/70">
                Permanently delete your account and all data
              </p>
            </div>
          </div>
        </button>
      </Section>

      {/* Spacer */}
      <div className="h-8" />

      {/* Sign Out Dialog */}
      <ConfirmDialog
        isOpen={showSignOutDialog}
        title="Sign Out"
        message="Are you sure you want to sign out?"
        confirmLabel="Sign Out"
        onConfirm={handleSignOut}
        onCancel={() => setShowSignOutDialog(false)}
      />

      {/* Delete Account Dialog */}
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

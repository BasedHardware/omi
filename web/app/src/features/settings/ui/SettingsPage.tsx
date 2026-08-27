'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from '@tschk/moonshine-next/navigation';
import { Loader2, AlertTriangle, Settings } from 'lucide-react';
import { useAuth } from '@/features/auth';
import { useToast } from '@/components/ui/Toast';
import { PageHeader } from '@/components/layout/PageHeader';
import {
  SECTION_INFO,
  SIGNED_OUT_DESTINATION,
  isSettingsSectionId,
  type SettingsSectionId,
  toWebhookApiType,
  ACCOUNT_QUICK_NAV,
  DEVELOPER_QUICK_NAV,
} from '../model';
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
  getAvailablePlans,
} from '../api';
import { deleteKnowledgeGraph } from '@/features/memories';
import type {
  DailySummarySettings,
  UserSubscription,
  AllUsageData,
  DeveloperWebhooks,
  DeveloperApiKey,
  McpApiKey,
  PricingOption,
} from '@/types/user';

import { ProfileSection } from './ProfileSection';
import { PrivacySection } from './PrivacySection';
import { AccountSection } from './AccountSection';
import { DeveloperSection } from './DeveloperSection';
import { ConfirmDialog } from './settingsPrimitives';

type SettingsSection = SettingsSectionId;

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
  const [vocabulary, setVocabulary] = useState<string[]>([]);
  const [dailySummary, setDailySummary] = useState<DailySummarySettings>({
    enabled: true,
    hour: 22,
  });
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
              getCustomVocabulary().catch(() => []),
              getDailySummarySettings().catch(() => ({ enabled: true, hour: 22 })),
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
    const webhookType = toWebhookApiType(type);
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
          url: url || webhooks[type as keyof DeveloperWebhooks]?.url || '',
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
        <div className="h-64 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-text-primary animate-spin" />
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
        return [...ACCOUNT_QUICK_NAV];
      case 'developer':
        return [...DEVELOPER_QUICK_NAV];
      default:
        return [];
    }
  };

  const quickNavSections = getQuickNavSections();

  return (
    <div className="h-full flex flex-col">
      {/* Export in-progress dialog */}
      {isExporting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" />
          <div className="relative bg-bg-secondary rounded-2xl p-6 max-w-sm w-full mx-4 shadow-2xl border border-white/[0.06]">
            <div className="flex flex-col items-center text-center gap-4">
              <div className="p-3 rounded-full bg-white/[0.08]">
                <Loader2 className="w-8 h-8 text-text-secondary animate-spin" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text-primary">
                  Exporting Your Data
                </h3>
                <p className="text-text-secondary mt-2 text-sm">
                  This may take a moment depending on the amount of data in your account.
                </p>
              </div>
              <div className="flex items-center gap-2 bg-yellow-500/10 rounded-xl px-4 py-2">
                <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0" />
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
        <div className="max-w-4xl mx-auto px-6 lg:px-8 pt-6">
          <div className="flex gap-6">
            {/* Main content */}
            <div className="flex-1 min-w-0">{renderSection()}</div>

            {/* Quick Nav Sidebar - only show on desktop when there are sections */}
            {quickNavSections.length > 0 && (
              <div className="hidden lg:block w-32 flex-shrink-0">
                <div className="sticky top-4">
                  <p className="text-xs font-medium text-text-quaternary uppercase tracking-wider mb-3">
                    On this page
                  </p>
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

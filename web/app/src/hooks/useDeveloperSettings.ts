'use client';

import { useEffect, useState } from 'react';
import { useToast } from '@/components/ui/Toast';
import {
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
} from '@/lib/api';
import type { DeveloperWebhooks, DeveloperApiKey, McpApiKey } from '@/types/user';

/**
 * State and handlers behind the Developers page: Developer API keys, MCP keys,
 * webhooks, and data export. Moved out of Settings when Developer became its
 * own destination; the behavior is unchanged.
 */
export function useDeveloperSettings() {
  const { showToast } = useToast();
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [apiKeys, setApiKeys] = useState<DeveloperApiKey[]>([]);
  const [mcpKeys, setMcpKeys] = useState<McpApiKey[]>([]);
  const [apiKeysError, setApiKeysError] = useState(false);
  const [mcpKeysError, setMcpKeysError] = useState(false);
  const [webhooks, setWebhooks] = useState<DeveloperWebhooks>({});

  const loadApiKeys = async () => {
    try {
      setApiKeys(await getDeveloperApiKeys({ throwOnError: true }));
      setApiKeysError(false);
    } catch {
      setApiKeysError(true);
    }
  };
  const loadMcpKeys = async () => {
    try {
      setMcpKeys(await getMcpApiKeys({ throwOnError: true }));
      setMcpKeysError(false);
    } catch {
      setMcpKeysError(true);
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        // Fetch API keys, MCP keys, webhook status, and individual webhook URLs in parallel
        // Note: Status API returns boolean fields, URL API returns {url: string}
        const [
          ,
          ,
          webhookStatus,
          memoryUrl,
          transcriptUrl,
          audioBytesUrl,
          daySummaryUrl,
        ] = await Promise.all([
          loadApiKeys(),
          loadMcpKeys(),
          getDeveloperWebhooksStatus().catch(() => ({})),
          getDeveloperWebhook('memory_created').catch(() => ({ url: '' })),
          getDeveloperWebhook('realtime_transcript').catch(() => ({ url: '' })),
          getDeveloperWebhook('audio_bytes').catch(() => ({ url: '' })),
          getDeveloperWebhook('day_summary').catch(() => ({ url: '' })),
        ]);
        // Full MCP key is only returned at creation time; keep secrets in memory for this session only.
        if (typeof window !== 'undefined') {
          localStorage.removeItem('omi_mcp_api_key_secrets');
        }
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
      } catch (error) {
        console.error('Failed to load developer settings:', error);
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  const handleCreateApiKey = async (
    name: string,
    scopes: string[],
  ): Promise<DeveloperApiKey | null> => {
    try {
      const newKey = await createDeveloperApiKey(name, scopes);
      setApiKeys((keys) => [...keys, newKey]);
      // A create after a failed list load must recover the list: clear the
      // error only when a fresh refresh succeeds, so a still-broken list
      // keeps its retry affordance instead of hiding the appended key.
      try {
        await loadApiKeys();
      } catch {
        // loadApiKeys already re-latched the error state.
      }
      return newKey;
    } catch (error) {
      console.error('Failed to create API key:', error);
      showToast('Failed to create API key. Please try again.', 'error');
      return null;
    }
  };

  const handleDeleteApiKey = async (keyId: string) => {
    try {
      await deleteDeveloperApiKey(keyId);
      setApiKeys((keys) => keys.filter((k) => k.id !== keyId));
    } catch (error) {
      console.error('Failed to delete API key:', error);
      showToast('Failed to delete API key. Please try again.', 'error');
    }
  };

  const handleCreateMcpKey = async (name: string): Promise<McpApiKey | null> => {
    try {
      const newKey = await createMcpApiKey(name);
      setMcpKeys((keys) => [...keys, newKey]);
      // Same recovery contract as developer keys: a successful create
      // retries the list and clears its error only on a successful refresh.
      try {
        await loadMcpKeys();
      } catch {
        // loadMcpKeys already re-latched the error state.
      }
      return newKey;
    } catch (error) {
      console.error('Failed to create MCP key:', error);
      showToast('Failed to create MCP key. Please try again.', 'error');
      return null;
    }
  };

  const handleDeleteMcpKey = async (keyId: string) => {
    try {
      await deleteMcpApiKey(keyId);
      setMcpKeys((keys) => keys.filter((k) => k.id !== keyId));
    } catch (error) {
      console.error('Failed to delete MCP key:', error);
      showToast('Failed to delete MCP key. Please try again.', 'error');
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

  return {
    isLoading,
    isExporting,
    apiKeys,
    apiKeysError,
    mcpKeys,
    mcpKeysError,
    webhooks,
    loadApiKeys,
    loadMcpKeys,
    handleCreateApiKey,
    handleDeleteApiKey,
    handleCreateMcpKey,
    handleDeleteMcpKey,
    handleExportData,
    handleDeleteKnowledgeGraph,
    handleWebhookChange,
  };
}

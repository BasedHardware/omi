'use client';

import { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';
import type { ExtractedAdvice } from '@/lib/proactiveAnalysis';
import type { FocusHistoryItem, FocusStatus } from '@/lib/focusAnalysis';

// Types
export type ProactiveState = 'idle' | 'monitoring' | 'analyzing';

export interface AssistantSettings {
    enabled: boolean;
    systemPrompt: string;
}

export interface ProactiveSettings {


    // Shared
    analysisIntervalMs: number;
    cooldownMs: number;

    // Advice Assistant
    advice: AssistantSettings & {
        confidenceThreshold: number;
    };

    // Focus Assistant
    focus: AssistantSettings;

    // Legacy support (to avoid full break during transition)
    enabled: boolean;
    confidenceThreshold?: number; // deprecated
    systemPrompt?: string; // deprecated
}

// Default settings
const DEFAULT_SETTINGS: ProactiveSettings = {
    analysisIntervalMs: 30000,
    cooldownMs: 30000,

    advice: {
        enabled: true,
        confidenceThreshold: 0.6,
        systemPrompt: '',
    },

    focus: {
        enabled: false,
        systemPrompt: '',
    },

    // Legacy
    enabled: false,
};

// Storage key
const SETTINGS_STORAGE_KEY = 'omi-proactive-settings';
const MAX_PREVIOUS_ADVICE = 10;

function deepMerge<T extends Record<string, any>>(target: T, source: Partial<T>): T {
    const result = { ...target };
    for (const key in source) {
        if (source.hasOwnProperty(key)) {
            const sourceValue = source[key];
            const targetValue = result[key];
            if (
                sourceValue &&
                typeof sourceValue === 'object' &&
                !Array.isArray(sourceValue) &&
                targetValue &&
                typeof targetValue === 'object' &&
                !Array.isArray(targetValue)
            ) {
                result[key] = deepMerge(targetValue, sourceValue);
            } else if (sourceValue !== undefined) {
                result[key] = sourceValue as any;
            }
        }
    }
    return result;
}

function loadSettings(): ProactiveSettings {
    if (typeof window === 'undefined') return DEFAULT_SETTINGS;

    try {
        const stored = localStorage.getItem(SETTINGS_STORAGE_KEY);
        if (!stored) return DEFAULT_SETTINGS;
        const parsed = JSON.parse(stored);

        // Migration: If old setting exists but new ones don't, map them
        if (parsed.enabled !== undefined && !parsed.advice) {
            return {
                ...DEFAULT_SETTINGS,
                analysisIntervalMs: parsed.analysisIntervalMs || 30000,
                cooldownMs: parsed.cooldownMs || 30000,
                advice: {
                    enabled: parsed.enabled,
                    confidenceThreshold: parsed.confidenceThreshold || 0.6,
                    systemPrompt: parsed.systemPrompt || '',
                },
                enabled: parsed.enabled, // Keep for legacy check
            };
        }

        return deepMerge(DEFAULT_SETTINGS, parsed);
    } catch {
        return DEFAULT_SETTINGS;
    }
}

function saveSettings(settings: ProactiveSettings): void {
    if (typeof window === 'undefined') return;

    try {
        localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    } catch (error) {
        console.error('Failed to save proactive settings:', error);
    }
}

interface ProactiveContextValue {
    // State
    state: ProactiveState;
    settings: ProactiveSettings;

    // Data
    previousAdvice: ExtractedAdvice[];
    focusHistory: FocusHistoryItem[];
    currentFocusStatus: FocusStatus | 'unknown';

    lastNotificationTime: number;
    error: string | null;

    // Actions
    setState: (state: ProactiveState) => void;
    updateSettings: (updates: Partial<ProactiveSettings> | ((prev: ProactiveSettings) => Partial<ProactiveSettings>)) => void;
    addAdvice: (advice: ExtractedAdvice) => void;
    addFocusEntry: (entry: FocusHistoryItem) => void;
    clearHistory: () => void;
    setPreviousAdvice: React.Dispatch<React.SetStateAction<ExtractedAdvice[]>>;
    setFocusHistory: React.Dispatch<React.SetStateAction<FocusHistoryItem[]>>;
    setLastNotificationTime: (time: number) => void;
    setError: (error: string | null) => void;

    // Refs for hook integration
    startMonitoringRef: React.MutableRefObject<(() => Promise<void>) | null>;
    stopMonitoringRef: React.MutableRefObject<(() => void) | null>;
}

const ProactiveContext = createContext<ProactiveContextValue | null>(null);

export function ProactiveProvider({ children }: { children: ReactNode }) {
    // State
    const [state, setState] = useState<ProactiveState>('idle');
    const [settings, setSettings] = useState<ProactiveSettings>(loadSettings);
    const [previousAdvice, setPreviousAdvice] = useState<ExtractedAdvice[]>([]);
    const [focusHistory, setFocusHistory] = useState<FocusHistoryItem[]>([]);
    const [currentFocusStatus, setCurrentFocusStatus] = useState<FocusStatus | 'unknown'>('unknown');
    const [lastNotificationTime, setLastNotificationTime] = useState(0);
    const [error, setError] = useState<string | null>(null);

    // Refs for hook integration
    const startMonitoringRef = useRef<(() => Promise<void>) | null>(null);
    const stopMonitoringRef = useRef<(() => void) | null>(null);

    // Update settings and persist
    const updateSettings = useCallback((updates: Partial<ProactiveSettings> | ((prev: ProactiveSettings) => Partial<ProactiveSettings>)) => {
        setSettings((prev) => {
            const newUpdates = typeof updates === 'function' ? updates(prev) : updates;
            const updated = { ...prev, ...newUpdates };

            if (newUpdates.advice) updated.advice = { ...prev.advice, ...newUpdates.advice };
            if (newUpdates.focus) updated.focus = { ...prev.focus, ...newUpdates.focus };

            saveSettings(updated);
            return updated;
        });
    }, []);

    // Add advice to history
    const addAdvice = useCallback((advice: ExtractedAdvice) => {
        setPreviousAdvice((prev) => [advice, ...prev].slice(0, MAX_PREVIOUS_ADVICE));
    }, []);

    // Add focus entry
    const addFocusEntry = useCallback((entry: FocusHistoryItem) => {
        setFocusHistory((prev) => [entry, ...prev].slice(0, MAX_PREVIOUS_ADVICE));
        setCurrentFocusStatus(entry.status);
    }, []);

    const clearHistory = useCallback(() => {
        setPreviousAdvice([]);
        setFocusHistory([]);
        setCurrentFocusStatus('unknown');
    }, []);

    return (
        <ProactiveContext.Provider
            value={{
                state,
                settings,
                previousAdvice,
                focusHistory,
                currentFocusStatus,
                lastNotificationTime,
                error,
                setState,
                updateSettings,
                addAdvice,
                addFocusEntry,
                clearHistory,
                setPreviousAdvice,
                setFocusHistory,
                setLastNotificationTime,
                setError,
                startMonitoringRef,
                stopMonitoringRef,
            }}
        >
            {children}
        </ProactiveContext.Provider>
    );
}

export function useProactiveContext() {
    const context = useContext(ProactiveContext);
    if (!context) {
        throw new Error('useProactiveContext must be used within a ProactiveProvider');
    }
    return context;
}

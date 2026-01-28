'use client';

import { useState } from 'react';
import { useProactiveNotifications } from '@/hooks/useProactiveNotifications';
import { DEFAULT_ANALYSIS_PROMPT } from '@/lib/proactiveAnalysis';

interface ProactiveSettingsProps {
    onClose?: () => void;
}

export function ProactiveSettings({ onClose }: ProactiveSettingsProps) {
    const { settings, updateSettings, clearAdviceHistory, previousAdvice } = useProactiveNotifications();

    const [showPrompt, setShowPrompt] = useState(false);

    // Format interval for display
    function formatInterval(ms: number): string {
        const seconds = ms / 1000;
        return seconds >= 60 ? `${seconds / 60} min` : `${seconds} sec`;
    }

    function handleResetPrompt() {
        updateSettings({ systemPrompt: '' });
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-white">Proactive Notifications</h2>
                {onClose && (
                    <button onClick={onClose} className="text-gray-400 hover:text-white">
                        ✕
                    </button>
                )}
            </div>

            <p className="text-sm text-gray-400">
                Get contextual advice based on what&apos;s on your screen. Requires screen sharing and
                browser notification permissions.
            </p>

            {/* Enable toggle */}
            <div className="flex items-center justify-between">
                <label id="proactive-toggle-label" className="text-sm font-medium text-gray-200">Enable Proactive Monitoring</label>
                <button
                    role="switch"
                    aria-checked={settings.enabled}
                    aria-labelledby="proactive-toggle-label"
                    onClick={() => updateSettings({ enabled: !settings.enabled })}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${settings.enabled ? 'bg-blue-600' : 'bg-gray-600'
                        }`}
                >
                    <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${settings.enabled ? 'translate-x-6' : 'translate-x-1'
                            }`}
                    />
                </button>
            </div>



            {/* Analysis Interval */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-gray-200">Analysis Interval</label>
                    <span className="text-sm text-gray-400">
                        {formatInterval(settings.analysisIntervalMs)}
                    </span>
                </div>
                <input
                    type="range"
                    min="5000"
                    max="60000"
                    step="5000"
                    value={settings.analysisIntervalMs}
                    onChange={(e) => updateSettings({ analysisIntervalMs: Number(e.target.value) })}
                    className="w-full"
                />
                <p className="text-xs text-gray-500">How often to capture and analyze your screen</p>
            </div>

            {/* Confidence Threshold */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-gray-200">Confidence Threshold</label>
                    <span className="text-sm text-gray-400">
                        {Math.round(settings.confidenceThreshold * 100)}%
                    </span>
                </div>
                <input
                    type="range"
                    min="0.5"
                    max="1.0"
                    step="0.05"
                    value={settings.confidenceThreshold}
                    onChange={(e) => updateSettings({ confidenceThreshold: Number(e.target.value) })}
                    className="w-full"
                />
                <p className="text-xs text-gray-500">
                    Only show advice above this confidence level. Higher = fewer, more relevant notifications
                </p>
            </div>

            {/* Cooldown */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-gray-200">Notification Cooldown</label>
                    <span className="text-sm text-gray-400">{formatInterval(settings.cooldownMs)}</span>
                </div>
                <input
                    type="range"
                    min="10000"
                    max="120000"
                    step="10000"
                    value={settings.cooldownMs}
                    onChange={(e) => updateSettings({ cooldownMs: Number(e.target.value) })}
                    className="w-full"
                />
                <p className="text-xs text-gray-500">Minimum time between notifications</p>
            </div>

            {/* Custom Prompt */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-gray-200">Custom System Prompt</label>
                    <button
                        onClick={() => setShowPrompt(!showPrompt)}
                        className="text-xs text-blue-400 hover:underline"
                    >
                        {showPrompt ? 'Hide' : 'Show'}
                    </button>
                </div>
                {showPrompt && (
                    <>
                        <textarea
                            value={settings.systemPrompt || DEFAULT_ANALYSIS_PROMPT}
                            onChange={(e) => updateSettings({ systemPrompt: e.target.value })}
                            rows={10}
                            className="w-full rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none font-mono"
                        />
                        <button onClick={handleResetPrompt} className="text-xs text-gray-400 hover:text-white">
                            Reset to default
                        </button>
                    </>
                )}
            </div>

            {/* Advice History */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-gray-200">
                        Advice History ({previousAdvice.length})
                    </label>
                    <button
                        onClick={clearAdviceHistory}
                        className="text-xs text-gray-400 hover:text-white"
                        disabled={previousAdvice.length === 0}
                    >
                        Clear
                    </button>
                </div>
                {previousAdvice.length > 0 && (
                    <div className="max-h-32 overflow-y-auto rounded-md border border-gray-700 bg-gray-900 p-2">
                        {previousAdvice.map((advice, i) => (
                            <div key={i} className="text-xs text-gray-400 py-1 border-b border-gray-800 last:border-0">
                                <span className="text-gray-500">[{Math.round(advice.confidence * 100)}%]</span>{' '}
                                {advice.advice}
                            </div>
                        ))}
                    </div>
                )}
            </div>
            {/* Debugging Section */}
            <div className="space-y-2 border-t border-gray-700 pt-4">
                <h3 className="text-sm font-medium text-gray-200">Debugging</h3>
                <div className="flex gap-2">
                    <button
                        onClick={() => {
                            if (typeof window !== 'undefined' && 'Notification' in window) {
                                if (Notification.permission === 'granted') {
                                    new Notification('Test Notification', {
                                        body: 'If you see this, notifications are working!',
                                        icon: '/logo.png',
                                        tag: 'test-notification',
                                    });
                                } else {
                                    Notification.requestPermission().then((permission) => {
                                        if (permission === 'granted') {
                                            new Notification('Test Notification', {
                                                body: 'If you see this, notifications are working!',
                                                icon: '/logo.png',
                                                tag: 'test-notification',
                                            });
                                        } else {
                                            alert(`Permission status: ${permission}`);
                                        }
                                    });
                                }
                            } else {
                                alert('Notifications not supported in this environment');
                            }
                        }}
                        className="px-3 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-xs text-white transition-colors"
                    >
                        Test Notification
                    </button>
                </div>

                {/* Last Analysis Log */}
                <div className="mt-2 text-xs text-gray-500 font-mono bg-black/20 p-2 rounded max-h-32 overflow-y-auto">
                    <div>API Key: Configured server-side (.env.local)</div>
                    <div>Settings: {settings.enabled ? 'Enabled' : 'Disabled'}</div>
                    <div>Interval: {settings.analysisIntervalMs}ms</div>
                    <div>Threshold: {settings.confidenceThreshold}</div>
                </div>
            </div>

        </div>
    );
}

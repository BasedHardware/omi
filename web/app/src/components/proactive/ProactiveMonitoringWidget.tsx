'use client';

import { useState } from 'react';
import { useProactiveNotifications } from '@/hooks/useProactiveNotifications';
import { ProactiveSettings } from './ProactiveSettings';

export function ProactiveMonitoringWidget() {
    const { state, error, isMonitoring, startMonitoring, stopMonitoring, settings, clearError } =
        useProactiveNotifications();
    const [showSettings, setShowSettings] = useState(false);

    // Determine status display
    function getStatusInfo(): { color: string; text: string; pulse: boolean } {
        switch (state) {
            case 'monitoring':
                return { color: 'bg-green-500', text: 'Monitoring', pulse: true };
            case 'analyzing':
                return { color: 'bg-blue-500', text: 'Analyzing...', pulse: true };
            default:
                return { color: 'bg-gray-500', text: 'Off', pulse: false };
        }
    }

    const status = getStatusInfo();

    async function handleToggle() {
        if (isMonitoring) {
            stopMonitoring();
        } else {
            await startMonitoring();
        }
    }

    // Don't render if not enabled in settings
    if (!settings.enabled && !showSettings) {
        return (
            <button
                onClick={() => setShowSettings(true)}
                className="flex items-center gap-2 rounded-full bg-gray-800 px-3 py-1.5 text-xs text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
                title="Configure Proactive Notifications"
            >
                <span className="text-sm">🔔</span>
                <span>Proactive</span>
            </button>
        );
    }

    return (
        <div className="relative">
            {/* Main widget button */}
            <button
                onClick={handleToggle}
                onContextMenu={(e) => {
                    e.preventDefault();
                    setShowSettings(true);
                }}
                className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-xs transition-colors ${isMonitoring
                        ? 'bg-green-900/50 text-green-400 hover:bg-green-900/70'
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'
                    }`}
                title={isMonitoring ? 'Click to stop monitoring' : 'Click to start monitoring'}
            >
                {/* Status indicator */}
                <span className="relative flex h-2 w-2">
                    {status.pulse && (
                        <span
                            className={`absolute inline-flex h-full w-full animate-ping rounded-full ${status.color} opacity-75`}
                        />
                    )}
                    <span className={`relative inline-flex h-2 w-2 rounded-full ${status.color}`} />
                </span>

                {/* Label */}
                <span>{status.text}</span>

                {/* Settings gear */}
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        setShowSettings(!showSettings);
                    }}
                    className="ml-1 text-gray-500 hover:text-white"
                >
                    ⚙️
                </button>
            </button>

            {/* Error tooltip */}
            {error && (
                <div className="absolute top-full left-0 mt-2 z-50 max-w-xs rounded-md bg-red-900/90 px-3 py-2 text-xs text-red-200 shadow-lg">
                    <div className="flex items-start gap-2">
                        <span className="text-red-400">⚠️</span>
                        <div>
                            <p>{error}</p>
                            <button onClick={clearError} className="mt-1 text-red-400 hover:underline">
                                Dismiss
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Settings popup */}
            {showSettings && (
                <>
                    {/* Backdrop */}
                    <div
                        className="fixed inset-0 z-40 bg-black/50"
                        onClick={() => setShowSettings(false)}
                    />

                    {/* Settings panel */}
                    <div className="absolute right-0 top-full mt-2 z-50 w-80 rounded-lg bg-gray-900 border border-gray-700 p-4 shadow-xl">
                        <ProactiveSettings onClose={() => setShowSettings(false)} />
                    </div>
                </>
            )}
        </div>
    );
}

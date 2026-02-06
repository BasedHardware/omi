import { useProactiveContext } from '@/components/proactive/ProactiveContext';
import { Card, Toggle, SettingRow, Dropdown } from '@/components/ui/settings-common';
import { Sparkles, Brain, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';
import { DEFAULT_ANALYSIS_PROMPT } from '@/lib/proactiveAnalysis';
import { DEFAULT_FOCUS_SYSTEM_PROMPT } from '@/lib/focusAnalysis';

export function ProactiveSection() {
    const {
        settings,
        updateSettings,
        currentFocusStatus,
        lastNotificationTime
    } = useProactiveContext();

    return (
        <div className="space-y-8">
            {/* Header / Intro */}
            <div className="flex items-center gap-3 mb-2">
                <div className="p-3 rounded-xl bg-purple-500/20">
                    <Sparkles className="w-6 h-6 text-purple-400" />
                </div>
                <div>
                    <h3 className="text-lg font-semibold text-text-primary">Proactive Assistant</h3>
                    <p className="text-sm text-text-tertiary">
                        AI-powered screen analysis to give you advice and help you stay focused.
                    </p>
                </div>
            </div>

            {/* General Settings */}
            <div className="space-y-3">
                <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">Configuration</h3>
                <Card>
                    <SettingRow
                        label="Analysis Interval"
                        description="How often to capture screen and analyze (milliseconds)"
                    >
                        <Dropdown
                            value={String(settings.analysisIntervalMs)}
                            options={[
                                { value: '5000', label: '5 Seconds (Fast)' },
                                { value: '10000', label: '10 Seconds (Normal)' },
                                { value: '20000', label: '20 Seconds' },
                                { value: '30000', label: '30 Seconds (Slow)' },
                                { value: '60000', label: '1 Minute (Power Save)' },
                            ]}
                            onChange={(val) => updateSettings({ analysisIntervalMs: parseInt(val) })}
                        />
                    </SettingRow>

                    <SettingRow
                        label="Notification Cooldown"
                        description="Minimum time between notifications"
                    >
                        <Dropdown
                            value={String(settings.cooldownMs)}
                            options={[
                                { value: '5000', label: '5 Seconds' },
                                { value: '10000', label: '10 Seconds' },
                                { value: '20000', label: '20 Seconds' },
                                { value: '30000', label: '30 Seconds' },
                                { value: '60000', label: '1 Minute' },
                            ]}
                            onChange={(val) => updateSettings({ cooldownMs: parseInt(val) })}
                        />
                    </SettingRow>

                    <div className="mt-4 pt-4 border-t border-white/[0.06]">
                        {/* Status section removed */}
                    </div>
                </Card>
            </div>

            {/* Advice Assistant */}
            <div className="space-y-3">
                <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">Advice Assistant</h3>
                    <Brain className="w-4 h-4 text-purple-400" />
                </div>
                <Card>
                    <div className="flex items-center justify-between mb-4">
                        <div>
                            <p className="text-text-primary font-medium">Enable Advice</p>
                            <p className="text-xs text-text-tertiary">Get contextual suggestions based on your screen</p>
                        </div>
                        <Toggle
                            enabled={settings.advice.enabled}
                            onChange={(enabled) => updateSettings(prev => ({
                                ...prev,
                                advice: { ...prev.advice, enabled }
                            }))}
                        />
                    </div>

                    {settings.advice.enabled && (
                        <div className="space-y-4 pt-4 border-t border-white/[0.06] animate-in slide-in-from-top-2 fade-in duration-200">
                            <SettingRow
                                label="Confidence Threshold"
                                description="Only show advice with high confidence score"
                            >
                                <div className="flex items-center gap-3">
                                    <span className="text-sm font-mono text-text-secondary">{(settings.advice.confidenceThreshold * 100).toFixed(0)}%</span>
                                    <input
                                        type="range"
                                        min="0.1"
                                        max="0.95"
                                        step="0.05"
                                        value={settings.advice.confidenceThreshold}
                                        onChange={(e) => updateSettings(prev => ({
                                            ...prev,
                                            advice: { ...prev.advice, confidenceThreshold: parseFloat(e.target.value) }
                                        }))}
                                        className="w-32 accent-purple-500"
                                    />
                                </div>
                            </SettingRow>

                            <div>
                                <label className="block text-sm font-medium text-text-primary mb-2">Custom System Prompt</label>
                                <textarea
                                    value={settings.advice.systemPrompt || DEFAULT_ANALYSIS_PROMPT}
                                    onChange={(e) => updateSettings(prev => ({
                                        ...prev,
                                        advice: { ...prev.advice, systemPrompt: e.target.value }
                                    }))}
                                    placeholder="Enter system prompt..."
                                    className="w-full h-24 px-4 py-3 rounded-xl bg-bg-tertiary border border-white/[0.06] text-text-primary text-sm placeholder:text-text-quaternary focus:outline-none focus:border-purple-500 resize-none font-mono"
                                />
                            </div>
                        </div>
                    )}
                </Card>
            </div>

            {/* Focus Assistant */}
            <div className="space-y-3">
                <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">Focus Assistant</h3>
                    <Zap className="w-4 h-4 text-amber-400" />
                </div>
                <Card>
                    <div className="flex items-center justify-between mb-4">
                        <div>
                            <p className="text-text-primary font-medium">Enable Focus Assistant</p>
                            <p className="text-xs text-text-tertiary">Get nudged when you get distracted</p>
                        </div>
                        <Toggle
                            enabled={settings.focus.enabled}
                            onChange={(enabled) => updateSettings(prev => ({
                                ...prev,
                                focus: { ...prev.focus, enabled }
                            }))}
                        />
                    </div>

                    {settings.focus.enabled && (
                        <div className="space-y-4 pt-4 border-t border-white/[0.06] animate-in slide-in-from-top-2 fade-in duration-200">
                            <div>
                                <label className="block text-sm font-medium text-text-primary mb-2">Custom Focus Prompt</label>
                                <textarea
                                    value={settings.focus.systemPrompt || DEFAULT_FOCUS_SYSTEM_PROMPT}
                                    onChange={(e) => updateSettings(prev => ({
                                        ...prev,
                                        focus: { ...prev.focus, systemPrompt: e.target.value }
                                    }))}
                                    placeholder="Enter focus prompt..."
                                    className="w-full h-24 px-4 py-3 rounded-xl bg-bg-tertiary border border-white/[0.06] text-text-primary text-sm placeholder:text-text-quaternary focus:outline-none focus:border-purple-500 resize-none font-mono"
                                />
                            </div>

                            <div className="flex items-center gap-2 p-3 bg-bg-tertiary rounded-xl">
                                <div className={cn(
                                    "w-3 h-3 rounded-full",
                                    currentFocusStatus === 'focused' ? "bg-green-500" :
                                        currentFocusStatus === 'distracted' ? "bg-red-500" : "bg-gray-500"
                                )} />
                                <span className="text-sm text-text-secondary">
                                    Current Status: <span className="font-medium text-text-primary capitalize">{currentFocusStatus === 'unknown' ? 'Inactive' : currentFocusStatus}</span>
                                </span>
                            </div>
                        </div>
                    )}
                </Card>
            </div>
        </div>
    );
}

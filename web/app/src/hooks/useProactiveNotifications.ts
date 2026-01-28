'use client';

import { useEffect, useCallback, useRef } from 'react';
import { useProactiveContext } from '@/components/proactive/ProactiveContext';
import { blobToBase64 } from '@/lib/geminiClient';
import {
    createFrameCapture,
    type FrameCapture,
} from '@/lib/screenCapture';
import {
    analyzeFrame,
    meetsConfidenceThreshold,
    DEFAULT_ANALYSIS_PROMPT,
} from '@/lib/proactiveAnalysis';
import { analyzeFocus } from '@/lib/focusAnalysis';
import { useRecordingContext } from '@/components/recording/RecordingContext';

/**
 * Hook to manage proactive screen monitoring and notifications.
 * Must be used within a ProactiveProvider.
 */
export function useProactiveNotifications() {
    const context = useProactiveContext();
    const {
        state: recordingState,
        audioMode,
        audioCaptureRef,
        segments,
    } = useRecordingContext(); // Import this at top

    const {
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
        setLastNotificationTime,
        setError,
        startMonitoringRef,
        stopMonitoringRef,
    } = context;

    // Local refs
    const frameCaptureRef = useRef<FrameCapture | null>(null);
    const isAnalyzingRef = useRef(false);
    const lastNotificationContentRef = useRef<string>('');

    // Request notification permission
    const requestNotificationPermission = useCallback(async (): Promise<boolean> => {
        if (!('Notification' in window)) {
            setError('Browser notifications are not supported');
            return false;
        }

        if (Notification.permission === 'granted') {
            return true;
        }

        if (Notification.permission === 'denied') {
            setError('Notification permission was denied. Please enable in browser settings.');
            return false;
        }

        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
            setError('Notification permission is required for proactive advice');
            return false;
        }

        return true;
    }, [setError]);

    // Send browser notification
    const sendNotification = useCallback(
        (title: string, body: string, tag: string) => {
            const now = Date.now();

            // Client-side spam protection: Don't repeat identical messages
            if (body === lastNotificationContentRef.current) {
                console.log('Proactive: Skipped notification (duplicate content)');
                return;
            }

            // Check global cooldown (simple implementation for now, shared across assistants)
            if (now - lastNotificationTime < settings.cooldownMs) {
                console.log('Proactive: Skipped notification (cooldown)');
                return;
            }

            // Send browser notification
            if (Notification.permission === 'granted') {
                const notification = new Notification(title, {
                    body: body,
                    icon: '/logo.png',
                    tag: tag,
                });

                notification.onclick = () => {
                    window.focus();
                    notification.close();
                };

                // Auto-close after 10 seconds
                setTimeout(() => notification.close(), 10000);
            }

            setLastNotificationTime(now);
            lastNotificationContentRef.current = body;
        },
        [lastNotificationTime, settings.cooldownMs, setLastNotificationTime]
    );

    // Get recent transcript text
    const getRecentTranscript = useCallback(() => {
        if (!segments || segments.length === 0) return undefined;
        // Last 10 segments or so
        const recent = segments.slice(-10);
        return recent
            .map(s => `${s.isUser ? 'User' : 'Speaker ' + s.speaker}: ${s.text}`)
            .join('\n');
    }, [segments]);

    // Handle frame capture
    const handleFrame = useCallback(
        async (jpegBlob: Blob) => {
            // Prevent concurrent analysis
            if (isAnalyzingRef.current) {
                return;
            }

            isAnalyzingRef.current = true;
            setState('analyzing');

            try {
                const transcript = getRecentTranscript();
                const imageBase64 = await blobToBase64(jpegBlob);

                // Run enabled assistants in parallel
                const promises = [];

                // 1. Advice Assistant
                if (settings.advice.enabled) {
                    promises.push(
                        analyzeFrame({
                            imageBase64,
                            previousAdvice: previousAdvice.map(a => ({ advice: a.advice, reasoning: a.reasoning })),
                            systemPrompt: settings.advice.systemPrompt || '',
                            transcript,
                        }).then(result => {
                            if (result?.has_advice && result.advice) {
                                if (meetsConfidenceThreshold(result.advice, settings.advice.confidenceThreshold)) {
                                    console.log(`Proactive Advice: [${Math.round(result.advice.confidence * 100)}%] "${result.advice.advice}"`);
                                    addAdvice(result.advice);
                                    sendNotification('Omi Advice', result.advice.advice, 'proactive-advice');
                                } else {
                                    console.log(`Proactive Advice: Filtered (low confidence)`);
                                }
                            }
                        })
                    );
                }

                // 2. Focus Assistant
                if (settings.focus.enabled) {
                    promises.push(
                        analyzeFocus({
                            imageBase64,
                            analysisHistory: focusHistory.map(h => ({
                                status: h.status,
                                app_or_site: h.app_or_site,
                                description: h.description,
                                message: h.message
                            })),
                            systemPrompt: settings.focus.systemPrompt || '',
                            transcript,
                        }).then(result => {
                            if (result) {
                                console.log(`Proactive Focus: [${result.status}] ${result.description}`);
                                addFocusEntry({ ...result, timestamp: Date.now() });

                                // Logic for notifying: when status changes to distracted, or refocuses
                                const isDistracted = result.status === 'distracted';
                                const wasDistracted = currentFocusStatus === 'distracted';

                                if (isDistracted && result.message) {
                                    // Always notify if distracted (cooldown handles spam)
                                    sendNotification('Distraction Alert', `${result.app_or_site}: ${result.message}`, 'focus-alert');
                                } else if (!isDistracted && wasDistracted && result.message) {
                                    // Notify on refocus
                                    sendNotification('Back on Track', result.message, 'focus-refocus');
                                }
                            }
                        })
                    );
                }

                await Promise.all(promises);

            } catch (err) {
                console.error('Proactive analysis error:', err);
            } finally {
                isAnalyzingRef.current = false;
                setState('monitoring');
            }
        },
        [
            settings.advice,
            settings.focus,
            previousAdvice,
            focusHistory,
            currentFocusStatus,
            setState,
            addAdvice,
            addFocusEntry,
            sendNotification,
            getRecentTranscript
        ]
    );

    // Stop monitoring implementation
    const stopMonitoring = useCallback(() => {
        if (frameCaptureRef.current) {
            frameCaptureRef.current.stop();
            frameCaptureRef.current = null;
        }

        // We do NOT stop the stream tracks as they belong to AudioCapture

        setState('idle');
        isAnalyzingRef.current = false;
        console.log('Proactive: Monitoring stopped');

        // Notify user if enabled
        sendNotification('Proactive Assistant', 'Monitoring paused', 'proactive-status');
    }, [setState, sendNotification]);


    // Start monitoring implementation
    const startMonitoring = useCallback(async () => {
        if (state !== 'idle') {
            console.warn('Proactive: Already monitoring');
            return;
        }

        // Check if recording is active and has system audio (implies stream exists)
        if (recordingState !== 'recording' && recordingState !== 'paused') {
            setError('Please start recording with "Mic + System Audio" first');
            return;
        }

        if (audioMode !== 'mic-and-system') {
            setError('Proactive assistant requires "Mic + System Audio" mode');
            return;
        }

        const hasNotificationPermission = await requestNotificationPermission();
        if (!hasNotificationPermission) {
            return;
        }

        setError(null);

        try {
            // Get stream from AudioCapture
            const systemStream = audioCaptureRef?.current?.getSystemStream();

            if (!systemStream) {
                throw new Error('No system stream available. Ensure you are sharing your screen.');
            }

            const videoTracks = systemStream.getVideoTracks();
            if (videoTracks.length === 0 || videoTracks[0].readyState === 'ended') {
                throw new Error('No video track available in recording stream.');
            }

            setState('monitoring');

            const frameCapture = createFrameCapture(videoTracks[0], {
                intervalMs: settings.analysisIntervalMs,
                onFrame: handleFrame,
                onError: (err) => console.error('Frame capture error:', err),
            });

            frameCaptureRef.current = frameCapture;
            frameCapture.start();

            console.log('Proactive: Monitoring started via unified stream');
            sendNotification('Proactive Assistant', 'Monitoring started', 'proactive-status');

        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to start proactive monitoring';
            setError(message);
            setState('idle');
        }
    }, [
        state,
        recordingState,
        audioMode,
        audioCaptureRef,
        settings.analysisIntervalMs,
        setState,
        setError,
        requestNotificationPermission,
        handleFrame,
        sendNotification
    ]);

    // Auto-stop if recording stops
    useEffect(() => {
        if (state !== 'idle' && recordingState === 'idle') {
            console.log('Proactive: Recording stopped, auto-stopping monitoring');
            stopMonitoring();
        }
    }, [recordingState, state, stopMonitoring]);

    // Register handlers
    useEffect(() => {
        startMonitoringRef.current = startMonitoring;
        stopMonitoringRef.current = stopMonitoring;
    }, [startMonitoring, stopMonitoring, startMonitoringRef, stopMonitoringRef]);

    // Cleanup
    useEffect(() => {
        return () => {
            if (frameCaptureRef.current) frameCaptureRef.current.stop();
        };
    }, []);

    return {
        state,
        settings,
        previousAdvice,
        focusHistory,
        currentFocusStatus,
        error,
        isMonitoring: state !== 'idle',
        isAnalyzing: state === 'analyzing',
        startMonitoring,
        stopMonitoring,
        updateSettings,
        clearHistory,
        clearError: () => setError(null),
    };
}

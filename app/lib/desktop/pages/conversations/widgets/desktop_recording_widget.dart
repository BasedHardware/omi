import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:shared_preferences/shared_preferences.dart';

class DesktopRecordingWidget extends StatefulWidget {
  final VoidCallback? onBack;
  final VoidCallback? onStartRecording;
  final bool hasConversations;
  final bool showTranscript;

  const DesktopRecordingWidget({
    super.key,
    this.onBack,
    this.onStartRecording,
    this.hasConversations = false,
    this.showTranscript = false,
  });

  @override
  State<DesktopRecordingWidget> createState() => _DesktopRecordingWidgetState();
}

class _DesktopRecordingWidgetState extends State<DesktopRecordingWidget> {
  bool _isHovered = false;
  List<Map<String, String>> _availableAudioDevices = [];
  String? _selectedDeviceId;
  final GlobalKey _micKey = GlobalKey();
  OverlayEntry? _audioDeviceOverlayEntry;

  @override
  void initState() {
    super.initState();
    _loadSavedDeviceId();
  }

  Future<void> _loadSavedDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    final savedDeviceId = prefs.getString('selected_audio_device_id');
    if (savedDeviceId == null || savedDeviceId.isEmpty) return;

    _setSelectedDeviceId(savedDeviceId);
  }

  void _setSelectedDeviceId(String deviceId) {
    if (mounted) {
      setState(() {
        _selectedDeviceId = deviceId;
      });
    }
  }

  Future<void> _toggleRecording(BuildContext context, CaptureProvider provider) async {
    var recordingState = provider.recordingState;

    if (PlatformService.isDesktop) {
      final onboardingProvider = context.read<OnboardingProvider>();
      if (!onboardingProvider.hasMicrophonePermission) {
        bool granted = await onboardingProvider.askForMicrophonePermissions();
        if (!granted) {
          return;
        }
      }

      // If we have an onStartRecording callback and not currently recording, use navigation
      if (widget.onStartRecording != null && recordingState != RecordingState.systemAudioRecord && !provider.isPaused) {
        // Start recording and then navigate
        await provider.streamSystemAudioRecording();
        widget.onStartRecording!();
      } else {
        // Handle recording controls (for when already on recording page)
        if (recordingState == RecordingState.systemAudioRecord) {
          await provider.pauseSystemAudioRecording();
        } else if (provider.isPaused) {
          await provider.resumeSystemAudioRecording();
        } else {
          await provider.streamSystemAudioRecording();
        }
      }
    }
  }

  Future<void> _stopRecording(BuildContext context, CaptureProvider provider) async {
    if (PlatformService.isDesktop) {
      await provider.stopSystemAudioRecording();
      // Force processing and shrink container
      await provider.forceProcessingCurrentConversation();
    }
  }

  Widget _buildProminentStartButton(
      bool isInitializing, RecordingState recordingState, CaptureProvider captureProvider) {
    return SizedBox(
      width: double.infinity,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Main prominent record button
          MouseRegion(
            onEnter: (_) => setState(() => _isHovered = true),
            onExit: (_) => setState(() => _isHovered = false),
            child: GestureDetector(
              onTap: isInitializing ? null : () => _toggleRecording(context, captureProvider),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                curve: Curves.easeInOut,
                width: 120,
                height: 120,
                decoration: BoxDecoration(
                  color: ResponsiveHelper.purplePrimary,
                  borderRadius: BorderRadius.circular(60),
                  boxShadow: _isHovered
                      ? [
                          BoxShadow(
                            color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                            blurRadius: 25,
                            offset: const Offset(0, 10),
                          ),
                        ]
                      : [
                          BoxShadow(
                            color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
                            blurRadius: 15,
                            offset: const Offset(0, 5),
                          ),
                        ],
                ),
                child: Center(
                  child: isInitializing
                      ? const SizedBox(
                          width: 32,
                          height: 32,
                          child: CircularProgressIndicator(
                            strokeWidth: 3,
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                        )
                      : const Icon(
                          Icons.mic_rounded,
                          size: 48,
                          color: Colors.white,
                        ),
                ),
              ),
            ),
          ),

          const SizedBox(height: 20),

          // Call-to-action text
          Column(
            children: [
              Text(
                isInitializing ? 'Setting up...' : 'Start Your First Recording',
                style: const TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                  color: ResponsiveHelper.textPrimary,
                  letterSpacing: -0.3,
                ),
              ),
              const SizedBox(height: 6),
              SelectableText(
                isInitializing
                    ? 'Preparing system audio capture'
                    : 'Click the button to capture audio for live transcripts, AI insights, and automatic saving.',
                style: const TextStyle(
                  fontSize: 15,
                  color: ResponsiveHelper.textTertiary,
                  height: 1.3,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),

          const SizedBox(height: 16),
        ],
      ),
    );
  }

  Widget _buildImprovedCompactRecording(
      bool isInitializing, RecordingState recordingState, CaptureProvider captureProvider) {
    final isRecording = recordingState == RecordingState.systemAudioRecord;
    final isPaused = captureProvider.isPaused;
    final isRecordingOrPaused = isRecording || isPaused;
    final hasTranscripts = captureProvider.segments.isNotEmpty;
    final latestTranscript = hasTranscripts ? captureProvider.segments.last.text.trim() : '';

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isRecordingOrPaused
            ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.08)
            : ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isRecordingOrPaused
              ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.2)
              : ResponsiveHelper.backgroundQuaternary.withValues(alpha: 0.6),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: isRecordingOrPaused
                ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.06)
                : Colors.black.withValues(alpha: 0.03),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          // Recording controls
          if (isRecordingOrPaused) ...[
            _controlButton(
              icon: isPaused ? Icons.play_arrow_rounded : Icons.pause_rounded,
              color: isPaused ? ResponsiveHelper.purplePrimary : Colors.orange,
              onPressed: isInitializing || captureProvider.isAutoReconnecting
                  ? null
                  : () => _toggleRecording(context, captureProvider),
            ),
            if (hasTranscripts) ...[
              const SizedBox(width: 12),
              _controlButton(
                icon: Icons.stop_rounded,
                color: Colors.red,
                onPressed: captureProvider.isAutoReconnecting ? null : () => _stopRecording(context, captureProvider),
              ),
            ],
          ] else ...[
            _controlButton(
              icon: Icons.mic_rounded,
              color: ResponsiveHelper.purplePrimary,
              size: 48,
              onPressed: isInitializing || captureProvider.isAutoReconnecting
                  ? null
                  : () => _toggleRecording(context, captureProvider),
            ),
          ],

          const SizedBox(width: 16),

          // Status and transcript text
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  captureProvider.isAutoReconnecting
                      ? 'Reconnecting...'
                      : isRecordingOrPaused
                          ? (isPaused ? 'Recording Paused' : 'Recording Active')
                          : (isInitializing ? 'Setting up...' : 'Start Recording'),
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: isRecordingOrPaused ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textPrimary,
                  ),
                ),
                const SizedBox(height: 4),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      captureProvider.isAutoReconnecting
                          ? 'Resuming in ${captureProvider.reconnectCountdown}s...'
                          : isRecordingOrPaused
                              ? (latestTranscript.isNotEmpty
                                  ? (latestTranscript.length > 60
                                      ? '${latestTranscript.substring(0, 60)}...'
                                      : latestTranscript)
                                  : (isPaused ? 'Tap play to resume' : 'Listening for audio...'))
                              : (isInitializing ? 'Preparing audio capture' : 'Click to begin recording'),
                      style: TextStyle(
                        fontSize: 14,
                        color: isRecordingOrPaused ? ResponsiveHelper.textSecondary : ResponsiveHelper.textTertiary,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    // Show latest translation if available
                    if (isRecordingOrPaused &&
                        hasTranscripts &&
                        captureProvider.segments.last.translations.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        _tryDecodingText(captureProvider.segments.last.translations.first.text),
                        style: const TextStyle(
                          fontSize: 12,
                          color: ResponsiveHelper.textTertiary,
                          fontStyle: FontStyle.italic,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      const Opacity(
                        opacity: 0.6,
                        child: Text(
                          'translated',
                          style: TextStyle(
                            fontSize: 10,
                            color: ResponsiveHelper.textQuaternary,
                            fontStyle: FontStyle.italic,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),

          // Expand to recording page button (only when recording)
          if (isRecordingOrPaused) ...[
            const SizedBox(width: 12),
            MouseRegion(
              cursor: SystemMouseCursors.click,
              child: GestureDetector(
                onTap: widget.onStartRecording,
                child: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(
                    Icons.open_in_full_rounded,
                    size: 16,
                    color: ResponsiveHelper.textSecondary,
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer3<CaptureProvider, DeviceProvider, ConnectivityProvider>(
      builder: (context, captureProvider, deviceProvider, connectivityProvider, child) {
        final recordingState = captureProvider.recordingState;
        final isRecording = recordingState == RecordingState.systemAudioRecord;
        final isInitializing = recordingState == RecordingState.initialising;
        final isPaused = captureProvider.isPaused;
        final hasTranscripts = captureProvider.segments.isNotEmpty;

        return Container(
          width: double.infinity,
          height: widget.showTranscript ? double.infinity : null,
          margin: widget.showTranscript ? const EdgeInsets.all(12) : EdgeInsets.zero,
          decoration: BoxDecoration(
            color: widget.showTranscript
                ? ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.95)
                : widget.hasConversations
                    ? Colors.transparent
                    : ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(widget.showTranscript
                ? 16
                : widget.hasConversations
                    ? 0
                    : 16),
            border: widget.showTranscript || !widget.hasConversations
                ? Border.all(
                    color: isRecording
                        ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.2)
                        : ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                    width: 1,
                  )
                : null,
            boxShadow: widget.showTranscript || !widget.hasConversations
                ? [
                    BoxShadow(
                      color: isRecording
                          ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.08)
                          : Colors.black.withValues(alpha: 0.04),
                      blurRadius: widget.showTranscript ? 20 : 15,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : null,
          ),
          child: widget.showTranscript
              ? _buildFullRecordingView(
                  isRecording, isInitializing, isPaused, hasTranscripts, recordingState, captureProvider)
              : _buildCompactRecordingView(isInitializing, recordingState, captureProvider),
        );
      },
    );
  }

  Widget _buildAnimatedTranscript(List<TranscriptSegment> segments, bool isRecording, bool isFullScreen) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Transcript header
        Container(
          padding: const EdgeInsets.only(bottom: 12),
          child: Row(
            children: [
              Container(
                width: isFullScreen ? 8 : 6,
                height: isFullScreen ? 8 : 6,
                decoration: BoxDecoration(
                  color: isRecording ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textQuaternary,
                  borderRadius: BorderRadius.circular(isFullScreen ? 4 : 3),
                ),
              ),
              const SizedBox(width: 12),
              Text(
                'Live Transcript',
                style: TextStyle(
                  fontSize: isFullScreen ? 16 : 14,
                  fontWeight: FontWeight.w500,
                  color: ResponsiveHelper.textSecondary,
                  letterSpacing: 0.2,
                ),
              ),
              if (segments.isNotEmpty) ...[
                const Spacer(),
                Text(
                  '${segments.length} segment${segments.length == 1 ? '' : 's'}',
                  style: const TextStyle(
                    fontSize: 12,
                    color: ResponsiveHelper.textQuaternary,
                  ),
                ),
              ],
            ],
          ),
        ),

        // Transcript content container
        Expanded(
          child: Container(
            width: double.infinity,
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
                width: 1,
              ),
            ),
            child: segments.isEmpty
                ? Container(
                    padding: EdgeInsets.all(isFullScreen ? 32 : 16),
                    child: Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.transcribe_rounded,
                            color: ResponsiveHelper.textQuaternary,
                            size: isFullScreen ? 32 : 20,
                          ),
                          SizedBox(height: isFullScreen ? 12 : 6),
                          Text(
                            isRecording ? 'Listening for audio...' : 'Start recording to see live transcript',
                            style: TextStyle(
                              fontSize: isFullScreen ? 16 : 12,
                              color: ResponsiveHelper.textTertiary,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    ),
                  )
                : SingleChildScrollView(
                    reverse: false, // Show from top instead of bottom
                    padding: const EdgeInsets.all(16),
                    child: _buildLiveTranscriptContent(segments),
                  ),
          ),
        ),
      ],
    );
  }

  String _getStatusText(RecordingState state, bool isPaused, CaptureProvider captureProvider) {
    if (captureProvider.isAutoReconnecting) return 'Reconnecting...';
    if (isPaused) return 'Paused';
    switch (state) {
      case RecordingState.initialising:
        return 'Initializing...';
      case RecordingState.systemAudioRecord:
        return 'Recording';
      default:
        return 'Start Recording';
    }
  }

  String _getSubtitleText(RecordingState state, bool isPaused, CaptureProvider captureProvider) {
    if (captureProvider.isAutoReconnecting) {
      return 'Microphone changed. Resuming in ${captureProvider.reconnectCountdown}s';
    }
    if (isPaused) return 'Click play to resume or stop to finish';
    switch (state) {
      case RecordingState.initialising:
        return 'Setting up system audio capture';
      case RecordingState.systemAudioRecord:
        return 'Capturing audio and generating transcript';
      default:
        return 'Click to begin recording system audio';
    }
  }

  Widget _buildLiveTranscriptContent(List<TranscriptSegment> segments) {
    final displaySegments = segments;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: displaySegments.asMap().entries.map((entry) {
        final index = entry.key;
        final segment = entry.value;
        final isLatest = index == displaySegments.length - 1;

        return Container(
          margin: EdgeInsets.only(bottom: index == displaySegments.length - 1 ? 0 : 8),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Speaker indicator
              Container(
                margin: const EdgeInsets.only(top: 2),
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  color: segment.isUser
                      ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.9)
                      : ResponsiveHelper.textTertiary.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(3),
                ),
              ),

              const SizedBox(width: 12),

              // Transcript content
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      segment.isUser ? 'You' : 'Speaker ${segment.speakerId}',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
                        color: segment.isUser ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
                      ),
                    ),
                    const SizedBox(height: 2),
                    AnimatedOpacity(
                      opacity: isLatest && segments.length > 1 ? 0.7 : 1.0,
                      duration: const Duration(milliseconds: 300),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // Original text
                          SelectableText(
                            _tryDecodingText(segment.text.trim()),
                            style: const TextStyle(
                              fontSize: 14,
                              height: 1.4,
                              color: ResponsiveHelper.textPrimary,
                            ),
                          ),
                          // Translations if available
                          if (segment.translations.isNotEmpty) ...[
                            const SizedBox(height: 6),
                            ...segment.translations.map((translation) => Padding(
                                  padding: const EdgeInsets.only(top: 2),
                                  child: SelectableText(
                                    _tryDecodingText(translation.text),
                                    style: const TextStyle(
                                      fontSize: 14,
                                      height: 1.4,
                                      color: ResponsiveHelper.textSecondary,
                                      fontStyle: FontStyle.italic,
                                    ),
                                  ),
                                )),
                            const SizedBox(height: 4),
                            _buildTranslationNotice(),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      }).toList(),
    );
  }

  // Helper method to decode text (same as mobile version)
  String _tryDecodingText(String text) {
    try {
      return utf8.decode(text.toString().codeUnits);
    } catch (e) {
      return text;
    }
  }

  Widget _buildTranslationNotice() {
    return const Opacity(
      opacity: 0.5,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.check_circle,
            size: 10,
            color: ResponsiveHelper.textTertiary,
          ),
          SizedBox(width: 4),
          SelectableText(
            'translated by omi',
            style: TextStyle(
              fontSize: 10,
              color: ResponsiveHelper.textTertiary,
              fontStyle: FontStyle.italic,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAudioLevelBar(double level, Color color) {
    final double normalizedLevel = (level / 0.05).clamp(0.0, 1.0);
    const double maxHeight = 16.0;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 100),
      curve: Curves.easeOut,
      height: (maxHeight * normalizedLevel).clamp(2.0, maxHeight),
      width: 4,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(2),
      ),
    );
  }

  Widget _buildFullRecordingView(
    bool isRecording,
    bool isInitializing,
    bool isPaused,
    bool hasTranscripts,
    RecordingState recordingState,
    CaptureProvider captureProvider,
  ) {
    return Column(
      children: [
        // Recording header
        Container(
          padding: const EdgeInsets.all(32),
          child: Column(
            children: [
              // Header with back button
              if (widget.onBack != null)
                Container(
                  width: double.infinity,
                  margin: const EdgeInsets.only(bottom: 24),
                  child: Row(
                    children: [
                      MouseRegion(
                        cursor: SystemMouseCursors.click,
                        child: GestureDetector(
                          onTap: widget.onBack,
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                            decoration: BoxDecoration(
                              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                                width: 1,
                              ),
                            ),
                            child: const Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.arrow_back_rounded,
                                  size: 16,
                                  color: ResponsiveHelper.textSecondary,
                                ),
                                SizedBox(width: 6),
                                Text(
                                  'Back to Conversations',
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w500,
                                    color: ResponsiveHelper.textSecondary,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const Spacer(),
                    ],
                  ),
                ),

              // Recording controls row
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // Pause / Resume
                  if (isRecording || isPaused)
                    _controlButton(
                      icon: isPaused ? Icons.play_arrow_rounded : Icons.pause_rounded,
                      color: isPaused ? ResponsiveHelper.purplePrimary : Colors.orange,
                      size: 48,
                      onPressed: isInitializing || captureProvider.isAutoReconnecting
                          ? null
                          : () => _toggleRecording(context, captureProvider),
                    ),

                  if ((isRecording || isPaused) && hasTranscripts) ...[
                    const SizedBox(width: 16),
                    _controlButton(
                      icon: Icons.stop_rounded,
                      color: Colors.red,
                      size: 48,
                      onPressed:
                          captureProvider.isAutoReconnecting ? null : () => _stopRecording(context, captureProvider),
                    ),
                  ],

                  // Initial recording button (not recording)
                  if (!isRecording && !isPaused)
                    _controlButton(
                      icon: Icons.mic_rounded,
                      color: ResponsiveHelper.purplePrimary,
                      size: 48,
                      onPressed: isInitializing || captureProvider.isAutoReconnecting
                          ? null
                          : () => _toggleRecording(context, captureProvider),
                    ),
                ],
              ),

              const SizedBox(height: 32),

              // Status text
              Text(
                _getStatusText(recordingState, isPaused, captureProvider),
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w600,
                  color: isRecording ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
                  letterSpacing: -0.5,
                ),
              ),

              const SizedBox(height: 8),

              Text(
                _getSubtitleText(recordingState, isPaused, captureProvider),
                style: const TextStyle(
                  fontSize: 16,
                  color: ResponsiveHelper.textTertiary,
                ),
                textAlign: TextAlign.center,
              ),

              const SizedBox(height: 24),
              if (isRecording || isPaused) _buildAudioSourceStatus(captureProvider),
            ],
          ),
        ),

        // Live transcript section
        Expanded(
          child: Container(
            margin: const EdgeInsets.fromLTRB(32, 0, 32, 32),
            child: _buildAnimatedTranscript(captureProvider.segments, isRecording, true),
          ),
        ),
      ],
    );
  }

  Widget _buildAudioSourceStatus(CaptureProvider captureProvider) {
    final micName = captureProvider.microphoneName;
    final micLevel = captureProvider.microphoneLevel;
    final systemLevel = captureProvider.systemAudioLevel;

    if (micName == null) {
      return const SizedBox.shrink();
    }

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        _buildMicrophoneSection(micName, micLevel),
        const SizedBox(width: 24),
        Row(
          children: [
            const Icon(Icons.volume_up_rounded, size: 16, color: ResponsiveHelper.textSecondary),
            const SizedBox(width: 8),
            const Text(
              'System',
              style: TextStyle(fontSize: 13, color: ResponsiveHelper.textSecondary),
            ),
            const SizedBox(width: 8),
            _buildAudioLevelBar(systemLevel, Colors.orange.shade600),
          ],
        ),
      ],
    );
  }

  Widget _buildMicrophoneSection(String micName, double micLevel) {
    return GestureDetector(
      key: _micKey,
      onTap: _toggleAudioDeviceDropdown,
      child: Tooltip(
        message: micName,
        child: Row(
          children: [
            const Icon(Icons.mic_rounded, size: 16, color: ResponsiveHelper.textSecondary),
            const SizedBox(width: 8),
            const Text(
              'Mic',
              style: TextStyle(fontSize: 13, color: ResponsiveHelper.textSecondary),
            ),
            const SizedBox(width: 4),
            Icon(
              _audioDeviceOverlayEntry != null ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
              size: 14,
              color: ResponsiveHelper.textSecondary,
            ),
            const SizedBox(width: 8),
            _buildAudioLevelBar(micLevel, ResponsiveHelper.purplePrimary),
          ],
        ),
      ),
    );
  }

  void _toggleAudioDeviceDropdown() {
    if (_audioDeviceOverlayEntry != null) {
      _removeAudioDeviceOverlay();
    } else {
      if (_availableAudioDevices.isEmpty) {
        _loadAvailableAudioDevices();
      }
      _audioDeviceOverlayEntry = _createAudioDeviceOverlayEntry();
      Overlay.of(context).insert(_audioDeviceOverlayEntry!);
      setState(() {});
    }
  }

  void _removeAudioDeviceOverlay() {
    _audioDeviceOverlayEntry?.remove();
    _audioDeviceOverlayEntry = null;
    setState(() {});
  }

  OverlayEntry _createAudioDeviceOverlayEntry() {
    final renderBox = _micKey.currentContext?.findRenderObject() as RenderBox?;
    if (renderBox == null) {
      return OverlayEntry(builder: (context) => const SizedBox.shrink());
    }

    final size = renderBox.size;
    final offset = renderBox.localToGlobal(Offset.zero);

    return OverlayEntry(
      builder: (context) => GestureDetector(
        onTap: _removeAudioDeviceOverlay,
        behavior: HitTestBehavior.translucent,
        child: Stack(
          children: [
            _overlayBackground(),
            Positioned(
              top: offset.dy + size.height + 5,
              left: offset.dx - 100 + (size.width / 2),
              child: _overlayDropdown(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _overlayBackground() => Positioned.fill(
        child: Container(color: Colors.transparent),
      );

  Widget _overlayDropdown() => GestureDetector(
        onTap: () {},
        child: _buildFloatingAudioDeviceDropdown(),
      );

  Future<void> _selectAudioDevice(Map<String, String> device) async {
    setState(() {
      _selectedDeviceId = device['id'];
    });

    _removeAudioDeviceOverlay();

    SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString('selected_audio_device_id', device['id'] ?? '');

    try {
      final result = await const MethodChannel('screenCapturePlatform')
          .invokeMethod('selectAudioDevice', {'deviceId': device['id']});

      if (mounted && result == true) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Audio input set to ${device['name']}'),
            duration: const Duration(seconds: 2),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error switching audio device: $e'),
            duration: const Duration(seconds: 3),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Widget _buildFloatingAudioDeviceDropdown() {
    return Material(
      elevation: 8,
      borderRadius: BorderRadius.circular(12),
      color: const Color(0xFF2C2C2E),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 280, minWidth: 220),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white.withOpacity(0.1)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 12, 16, 8),
              child: Text('Select Audio Input',
                  style: TextStyle(fontSize: 13, color: Colors.white70, fontWeight: FontWeight.w600)),
            ),
            Divider(height: 1, color: Colors.white.withOpacity(0.1)),
            const SizedBox(height: 4),
            if (_availableAudioDevices.isNotEmpty)
              ..._availableAudioDevices.map(_buildFloatingAudioDeviceItem)
            else
              const Padding(
                  padding: EdgeInsets.all(16),
                  child: Center(
                      child: Text('Loading devices...',
                          style: TextStyle(fontSize: 12, color: ResponsiveHelper.textSecondary)))),
            const SizedBox(height: 4),
          ],
        ),
      ),
    );
  }

  Widget _buildFloatingAudioDeviceItem(Map<String, String> device) {
    final isSelected = device['id'] == _selectedDeviceId;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => _selectAudioDevice(device),
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(
            children: [
              Container(
                width: 18,
                height: 18,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: isSelected ? ResponsiveHelper.purplePrimary : Colors.grey[500]!,
                    width: 2,
                  ),
                  color: Colors.transparent,
                ),
                child: isSelected
                    ? Center(
                        child: Container(
                          width: 10,
                          height: 10,
                          decoration: const BoxDecoration(
                            shape: BoxShape.circle,
                            color: ResponsiveHelper.purplePrimary,
                          ),
                        ),
                      )
                    : null,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  device['name'] ?? 'Unknown Device',
                  style: TextStyle(
                    fontSize: 14,
                    color: isSelected ? Colors.white : Colors.white70,
                    fontWeight: isSelected ? FontWeight.w500 : FontWeight.normal,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String? _validateSelectedDevice(List<Map<String, String>> devices, String? currentId) {
    if (currentId == null || currentId.isEmpty) {
      return _findCurrentDeviceId(devices);
    }

    final exists = devices.any((d) => d['id'] == currentId);
    return exists ? currentId : _findCurrentDeviceId(devices);
  }

  Future<void> _loadAvailableAudioDevices() async {
    final result = await const MethodChannel('screenCapturePlatform').invokeMethod('getAvailableAudioDevices');

    if (result is List && mounted) {
      final devices = result
          .map((device) => {
                'id': device['id']?.toString() ?? '',
                'name': device['name']?.toString() ?? 'Unknown Device',
              })
          .toList();

      setState(() {
        _availableAudioDevices = devices;
        _selectedDeviceId = _validateSelectedDevice(devices, _selectedDeviceId);
      });
    }
  }

  String? _findCurrentDeviceId(List<Map<String, String>> devices) {
    if (devices.isEmpty) return null;

    final currentMicName = context.read<CaptureProvider>().microphoneName;
    if (currentMicName != null) {
      final matchingDevice = devices.firstWhere(
        (device) => device['name'] == currentMicName,
        orElse: () => devices.first,
      );
      return matchingDevice['id'];
    }
    return devices.first['id'];
  }

  Widget _buildCompactRecordingView(
      bool isInitializing, RecordingState recordingState, CaptureProvider captureProvider) {
    return Container(
      padding: EdgeInsets.all(widget.hasConversations ? 0 : 20),
      child: widget.hasConversations
          ? _buildImprovedCompactRecording(isInitializing, recordingState, captureProvider)
          : _buildProminentStartButton(isInitializing, recordingState, captureProvider),
    );
  }

  Widget _controlButton({
    required IconData icon,
    required Color color,
    required VoidCallback? onPressed,
    double size = 36,
  }) {
    return OmiIconButton(
      icon: icon,
      onPressed: onPressed,
      color: color,
      size: size,
      solid: true,
      borderRadius: size / 2,
    );
  }
}

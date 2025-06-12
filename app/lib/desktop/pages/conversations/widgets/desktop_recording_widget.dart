import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

class DesktopPremiumRecordingWidget extends StatefulWidget {
  final VoidCallback? onMinimize;
  final bool hasConversations;

  const DesktopPremiumRecordingWidget({
    super.key,
    this.onMinimize,
    this.hasConversations = false,
  });

  @override
  State<DesktopPremiumRecordingWidget> createState() => _DesktopPremiumRecordingWidgetState();
}

class _DesktopPremiumRecordingWidgetState extends State<DesktopPremiumRecordingWidget> {
  bool _isHovered = false;

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

      if (recordingState == RecordingState.systemAudioRecord) {
        await provider.pauseSystemAudioRecording();
      } else if (provider.isPaused) {
        await provider.resumeSystemAudioRecording();
      } else {
        await provider.streamSystemAudioRecording();
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
                transform: Matrix4.identity()..scale(_isHovered ? 1.03 : 1.0),
                child: Container(
                  width: 120,
                  height: 120,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        ResponsiveHelper.purplePrimary,
                        ResponsiveHelper.purplePrimary.withOpacity(0.8),
                        const Color(0xFF6366F1),
                      ],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(60),
                    boxShadow: [
                      BoxShadow(
                        color: ResponsiveHelper.purplePrimary.withOpacity(0.25),
                        blurRadius: 20,
                        offset: const Offset(0, 8),
                        spreadRadius: 2,
                      ),
                      BoxShadow(
                        color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
                        blurRadius: 40,
                        offset: const Offset(0, 16),
                        spreadRadius: 0,
                      ),
                    ],
                  ),
                  child: Stack(
                    children: [
                      // Pulsing ring effect
                      if (!isInitializing)
                        Positioned.fill(
                          child: AnimatedContainer(
                            duration: const Duration(seconds: 2),
                            curve: Curves.easeInOut,
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(60),
                              border: Border.all(
                                color: Colors.white.withOpacity(0.2),
                                width: 2,
                              ),
                            ),
                          ),
                        ),

                      // Center content
                      Center(
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
                    ],
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
              Text(
                isInitializing
                    ? 'Preparing system audio capture'
                    : 'Click the button above to begin capturing audio and create live transcripts',
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

          // Feature highlights
          if (!isInitializing)
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _buildFeatureChip(Icons.transcribe_rounded, 'Live Transcript'),
                const SizedBox(width: 12),
                _buildFeatureChip(Icons.psychology_rounded, 'AI Insights'),
                const SizedBox(width: 12),
                _buildFeatureChip(Icons.cloud_sync_rounded, 'Auto Save'),
              ],
            ),
        ],
      ),
    );
  }

  Widget _buildImprovedCompactRecording(
      bool isInitializing, RecordingState recordingState, CaptureProvider captureProvider) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: ResponsiveHelper.backgroundQuaternary.withOpacity(0.6),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.03),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          // Simple recording button
          MouseRegion(
            onEnter: (_) => setState(() => _isHovered = true),
            onExit: (_) => setState(() => _isHovered = false),
            child: GestureDetector(
              onTap: isInitializing ? null : () => _toggleRecording(context, captureProvider),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                transform: Matrix4.identity()..scale(_isHovered ? 1.05 : 1.0),
                child: Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.purplePrimary,
                    borderRadius: BorderRadius.circular(24),
                    boxShadow: [
                      BoxShadow(
                        color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
                        blurRadius: 6,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  child: Center(
                    child: isInitializing
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : const Icon(
                            Icons.mic_rounded,
                            size: 20,
                            color: Colors.white,
                          ),
                  ),
                ),
              ),
            ),
          ),

          const SizedBox(width: 16),

          // Simple status text
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isInitializing ? 'Setting up...' : 'Start Recording',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: ResponsiveHelper.textPrimary,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  isInitializing ? 'Preparing audio capture' : 'Click to begin recording',
                  style: const TextStyle(
                    fontSize: 14,
                    color: ResponsiveHelper.textTertiary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFeatureChip(IconData icon, String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: ResponsiveHelper.backgroundQuaternary.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: 14,
            color: ResponsiveHelper.purplePrimary,
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: ResponsiveHelper.textSecondary,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final screenSize = MediaQuery.of(context).size;

    return Consumer3<CaptureProvider, DeviceProvider, ConnectivityProvider>(
      builder: (context, captureProvider, deviceProvider, connectivityProvider, child) {
        final recordingState = captureProvider.recordingState;
        final isRecording = recordingState == RecordingState.systemAudioRecord;
        final isInitializing = recordingState == RecordingState.initialising;
        final isPaused = captureProvider.isPaused;
        final hasTranscripts = captureProvider.segments.isNotEmpty;
        final isRecordingOrInitializing = isRecording || isInitializing || isPaused;

        return Container(
          width: isRecordingOrInitializing
              ? screenSize.width - 280 - 24 // Full width minus sidebar and padding
              : double.infinity,
          height: isRecordingOrInitializing
              ? screenSize.height - 24 // Full height minus padding
              : null,
          margin: isRecordingOrInitializing ? const EdgeInsets.all(12) : EdgeInsets.zero,
          decoration: BoxDecoration(
            color: isRecordingOrInitializing
                ? ResponsiveHelper.backgroundSecondary.withOpacity(0.95)
                : widget.hasConversations
                    ? Colors.transparent
                    : ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(isRecordingOrInitializing
                ? 16
                : widget.hasConversations
                    ? 0
                    : 16),
            border: isRecordingOrInitializing || !widget.hasConversations
                ? Border.all(
                    color: isRecording
                        ? ResponsiveHelper.purplePrimary.withOpacity(0.2)
                        : ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
                    width: 1,
                  )
                : null,
            boxShadow: isRecordingOrInitializing || !widget.hasConversations
                ? [
                    BoxShadow(
                      color: isRecording
                          ? ResponsiveHelper.purplePrimary.withOpacity(0.08)
                          : Colors.black.withOpacity(0.04),
                      blurRadius: isRecordingOrInitializing ? 20 : 15,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : null,
          ),
          child: Column(
            children: [
              // Recording header
              Container(
                padding: EdgeInsets.all(isRecordingOrInitializing
                    ? 32
                    : widget.hasConversations
                        ? 0
                        : 20),
                child: isRecordingOrInitializing
                    ? Column(
                        children: [
                          // Header with minimize button
                          if (widget.onMinimize != null)
                            Container(
                              width: double.infinity,
                              margin: const EdgeInsets.only(bottom: 24),
                              child: Row(
                                children: [
                                  const Spacer(),
                                  MouseRegion(
                                    cursor: SystemMouseCursors.click,
                                    child: GestureDetector(
                                      onTap: widget.onMinimize,
                                      child: Container(
                                        width: 36,
                                        height: 36,
                                        decoration: BoxDecoration(
                                          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                                          borderRadius: BorderRadius.circular(18),
                                          border: Border.all(
                                            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                                            width: 1,
                                          ),
                                        ),
                                        child: const Icon(
                                          Icons.minimize_rounded,
                                          size: 20,
                                          color: ResponsiveHelper.textSecondary,
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),

                          // Recording controls row
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              // Pause/Resume button
                              if (isRecording || isPaused)
                                MouseRegion(
                                  onEnter: (_) => setState(() => _isHovered = true),
                                  onExit: (_) => setState(() => _isHovered = false),
                                  child: GestureDetector(
                                    onTap: isInitializing ? null : () => _toggleRecording(context, captureProvider),
                                    child: Transform.scale(
                                      scale: _isHovered ? 1.05 : 1.0,
                                      child: Container(
                                        width: 48,
                                        height: 48,
                                        decoration: BoxDecoration(
                                          gradient: isPaused
                                              ? LinearGradient(
                                                  colors: [
                                                    ResponsiveHelper.purplePrimary,
                                                    ResponsiveHelper.purplePrimary.withOpacity(0.9),
                                                  ],
                                                  begin: Alignment.topLeft,
                                                  end: Alignment.bottomRight,
                                                )
                                              : LinearGradient(
                                                  colors: [
                                                    Colors.orange,
                                                    Colors.orange.withOpacity(0.9),
                                                  ],
                                                ),
                                          borderRadius: BorderRadius.circular(24),
                                          boxShadow: [
                                            BoxShadow(
                                              color: isPaused
                                                  ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
                                                  : Colors.orange.withOpacity(0.15),
                                              blurRadius: 12,
                                              offset: const Offset(0, 1),
                                            ),
                                          ],
                                        ),
                                        child: isInitializing
                                            ? const Center(
                                                child: SizedBox(
                                                  width: 16,
                                                  height: 16,
                                                  child: CircularProgressIndicator(
                                                    strokeWidth: 2,
                                                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                                  ),
                                                ),
                                              )
                                            : Icon(
                                                isPaused ? Icons.play_arrow_rounded : Icons.pause_rounded,
                                                size: 20,
                                                color: Colors.white,
                                              ),
                                      ),
                                    ),
                                  ),
                                ),

                              if ((isRecording || isPaused) && hasTranscripts) ...[
                                const SizedBox(width: 16),

                                // Stop button
                                MouseRegion(
                                  child: GestureDetector(
                                    onTap: () => _stopRecording(context, captureProvider),
                                    child: Container(
                                      width: 48,
                                      height: 48,
                                      decoration: BoxDecoration(
                                        gradient: LinearGradient(
                                          colors: [
                                            Colors.red,
                                            Colors.red.withOpacity(0.9),
                                          ],
                                        ),
                                        borderRadius: BorderRadius.circular(24),
                                        boxShadow: [
                                          BoxShadow(
                                            color: Colors.red.withOpacity(0.15),
                                            blurRadius: 12,
                                            offset: const Offset(0, 1),
                                          ),
                                        ],
                                      ),
                                      child: const Icon(
                                        Icons.stop_rounded,
                                        size: 20,
                                        color: Colors.white,
                                      ),
                                    ),
                                  ),
                                ),
                              ],

                              // Initial recording button (when not recording)
                              if (!isRecording && !isPaused)
                                MouseRegion(
                                  onEnter: (_) => setState(() => _isHovered = true),
                                  onExit: (_) => setState(() => _isHovered = false),
                                  child: GestureDetector(
                                    onTap: isInitializing ? null : () => _toggleRecording(context, captureProvider),
                                    child: Transform.scale(
                                      scale: _isHovered ? 1.05 : 1.0,
                                      child: Container(
                                        width: 48,
                                        height: 48,
                                        decoration: BoxDecoration(
                                          gradient: LinearGradient(
                                            colors: [
                                              ResponsiveHelper.backgroundTertiary,
                                              ResponsiveHelper.backgroundTertiary.withOpacity(0.9),
                                            ],
                                          ),
                                          borderRadius: BorderRadius.circular(24),
                                          boxShadow: [
                                            BoxShadow(
                                              color: Colors.black.withOpacity(0.06),
                                              blurRadius: 6,
                                              offset: const Offset(0, 1),
                                            ),
                                          ],
                                        ),
                                        child: const Icon(
                                          Icons.mic_rounded,
                                          size: 20,
                                          color: ResponsiveHelper.textSecondary,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                            ],
                          ),

                          const SizedBox(height: 32),

                          // Status text
                          Text(
                            _getStatusText(recordingState, isPaused),
                            style: TextStyle(
                              fontSize: 24,
                              fontWeight: FontWeight.w600,
                              color: isRecording ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
                              letterSpacing: -0.5,
                            ),
                          ),

                          const SizedBox(height: 8),

                          Text(
                            _getSubtitleText(recordingState, isPaused),
                            style: const TextStyle(
                              fontSize: 16,
                              color: ResponsiveHelper.textTertiary,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      )
                    : widget.hasConversations
                        ? _buildImprovedCompactRecording(isInitializing, recordingState, captureProvider)
                        : _buildProminentStartButton(isInitializing, recordingState, captureProvider),
              ),

              // Live transcript section
              if (isRecordingOrInitializing)
                Expanded(
                  child: Container(
                    margin: const EdgeInsets.fromLTRB(32, 0, 32, 32),
                    child: _buildAnimatedTranscript(captureProvider.segments, isRecording, isRecordingOrInitializing),
                  ),
                ),
            ],
          ),
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
              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
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
                              fontStyle: FontStyle.italic,
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

  String _getStatusText(RecordingState state, bool isPaused) {
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

  String _getSubtitleText(RecordingState state, bool isPaused) {
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
    // Show recent segments with smooth streaming effect
    final displaySegments = segments.length > 15 ? segments.sublist(segments.length - 15) : segments;

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
                      ? ResponsiveHelper.purplePrimary.withOpacity(0.9)
                      : ResponsiveHelper.textTertiary.withOpacity(0.6),
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
                      child: Text(
                        segment.text.trim(),
                        style: const TextStyle(
                          fontSize: 14,
                          height: 1.4,
                          color: ResponsiveHelper.textPrimary,
                        ),
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
}

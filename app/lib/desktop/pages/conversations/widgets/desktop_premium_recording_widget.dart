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
  const DesktopPremiumRecordingWidget({super.key});

  @override
  State<DesktopPremiumRecordingWidget> createState() => _DesktopPremiumRecordingWidgetState();
}

class _DesktopPremiumRecordingWidgetState extends State<DesktopPremiumRecordingWidget> with TickerProviderStateMixin {
  late AnimationController _pulseController;
  late AnimationController _waveController;
  late Animation<double> _pulseAnimation;
  late Animation<double> _scaleAnimation;

  Timer? _transcriptUpdateTimer;
  bool _isHovered = false;

  @override
  void initState() {
    super.initState();

    // Pulse animation for recording state
    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    );

    _pulseAnimation = Tween<double>(
      begin: 1.0,
      end: 1.08,
    ).animate(CurvedAnimation(
      parent: _pulseController,
      curve: Curves.easeInOut,
    ));

    _scaleAnimation = Tween<double>(
      begin: 1.0,
      end: 0.95,
    ).animate(CurvedAnimation(
      parent: _pulseController,
      curve: Curves.easeInOut,
    ));

    // Wave animation for audio visualization
    _waveController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
  }

  @override
  void dispose() {
    _pulseController.dispose();
    _waveController.dispose();
    _transcriptUpdateTimer?.cancel();
    super.dispose();
  }

  void _startRecordingAnimations() {
    _pulseController.repeat(reverse: true);
    _waveController.repeat();
  }

  void _stopRecordingAnimations() {
    _pulseController.stop();
    _waveController.stop();
    _pulseController.reset();
    _waveController.reset();
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

      if (recordingState == RecordingState.systemAudioRecord) {
        await provider.stopSystemAudioRecording();
        _stopRecordingAnimations();
      } else if (recordingState == RecordingState.initialising) {
        debugPrint('initialising, have to wait');
      } else {
        await provider.streamSystemAudioRecording();
        _startRecordingAnimations();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer3<CaptureProvider, DeviceProvider, ConnectivityProvider>(
      builder: (context, captureProvider, deviceProvider, connectivityProvider, child) {
        final recordingState = captureProvider.recordingState;
        final isRecording = recordingState == RecordingState.systemAudioRecord;
        final isInitializing = recordingState == RecordingState.initialising;
        final hasTranscripts = captureProvider.segments.isNotEmpty;

        // Control animations based on recording state
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (isRecording && !_pulseController.isAnimating) {
            _startRecordingAnimations();
          } else if (!isRecording && _pulseController.isAnimating) {
            _stopRecordingAnimations();
          }
        });

        return Container(
          width: double.infinity,
          margin: const EdgeInsets.symmetric(horizontal: 32),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: isRecording
                  ? ResponsiveHelper.purplePrimary.withOpacity(0.4)
                  : ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: isRecording ? ResponsiveHelper.purplePrimary.withOpacity(0.08) : Colors.black.withOpacity(0.04),
                blurRadius: 20,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            children: [
              // Recording header with button and status
              _buildRecordingHeader(
                recordingState,
                isRecording,
                isInitializing,
                () => _toggleRecording(context, captureProvider),
              ),

              // Live transcript section - always shown for better UX
              _buildLiveTranscriptSection(captureProvider.segments, isRecording),
            ],
          ),
        );
      },
    );
  }

  Widget _buildRecordingHeader(
    RecordingState recordingState,
    bool isRecording,
    bool isInitializing,
    VoidCallback onToggle,
  ) {
    return Container(
      padding: const EdgeInsets.all(20),
      child: Row(
        children: [
          // Smaller recording button with premium styling
          MouseRegion(
            onEnter: (_) => setState(() => _isHovered = true),
            onExit: (_) => setState(() => _isHovered = false),
            child: GestureDetector(
              onTap: isInitializing ? null : onToggle,
              child: AnimatedBuilder(
                animation: Listenable.merge([_pulseAnimation, _scaleAnimation]),
                builder: (context, child) {
                  return Transform.scale(
                    scale: isRecording ? _pulseAnimation.value * (_isHovered ? 1.02 : 1.0) : (_isHovered ? 1.05 : 1.0),
                    child: Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(
                        gradient: isRecording
                            ? LinearGradient(
                                colors: [
                                  ResponsiveHelper.purplePrimary,
                                  ResponsiveHelper.purplePrimary.withOpacity(0.8),
                                ],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              )
                            : LinearGradient(
                                colors: [
                                  ResponsiveHelper.backgroundTertiary,
                                  ResponsiveHelper.backgroundTertiary.withOpacity(0.8),
                                ],
                              ),
                        borderRadius: BorderRadius.circular(24),
                        boxShadow: [
                          BoxShadow(
                            color: isRecording
                                ? ResponsiveHelper.purplePrimary.withOpacity(0.3)
                                : Colors.black.withOpacity(0.1),
                            blurRadius: isRecording ? 16 : 8,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: isInitializing
                          ? Center(
                              child: SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(
                                    isRecording ? Colors.white : ResponsiveHelper.textSecondary,
                                  ),
                                ),
                              ),
                            )
                          : Icon(
                              isRecording ? Icons.stop_rounded : Icons.mic_rounded,
                              size: 20,
                              color: isRecording ? Colors.white : ResponsiveHelper.textSecondary,
                            ),
                    ),
                  );
                },
              ),
            ),
          ),

          const SizedBox(width: 16),

          // Status info and visualization
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      _getStatusText(recordingState),
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                        color: isRecording ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
                        letterSpacing: -0.2,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  _getSubtitleText(recordingState),
                  style: TextStyle(
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

  Widget _buildAudioVisualization() {
    return AnimatedBuilder(
      animation: _waveController,
      builder: (context, child) {
        return Container(
          height: 40,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(5, (index) {
              final delay = index * 0.2;
              final animationValue = (_waveController.value + delay) % 1.0;
              final height = 8 + (math.sin(animationValue * 2 * math.pi) * 16);

              return Container(
                width: 3,
                height: height,
                margin: const EdgeInsets.symmetric(horizontal: 2),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.purplePrimary.withOpacity(0.8),
                  borderRadius: BorderRadius.circular(2),
                ),
              );
            }),
          ),
        );
      },
    );
  }

  Widget _buildTranscriptSection(List<TranscriptSegment> segments) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withOpacity(0.4),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  color: ResponsiveHelper.purplePrimary,
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                'Live Transcript',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: ResponsiveHelper.textSecondary,
                  letterSpacing: 0.2,
                ),
              ),
            ],
          ),

          const SizedBox(height: 16),

          // Transcript content with scrollable area
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 200),
            child: SingleChildScrollView(
              reverse: true, // Auto-scroll to bottom for latest content
              child: _buildTranscriptContent(segments),
            ),
          ),
        ],
      ),
    );
  }

  String _getStatusText(RecordingState state) {
    switch (state) {
      case RecordingState.initialising:
        return 'Initializing...';
      case RecordingState.systemAudioRecord:
        return 'Recording';
      default:
        return 'Start Recording';
    }
  }

  String _getSubtitleText(RecordingState state) {
    switch (state) {
      case RecordingState.initialising:
        return 'Setting up system audio capture';
      case RecordingState.systemAudioRecord:
        return 'Capturing audio and generating transcript';
      default:
        return 'Click to begin recording system audio';
    }
  }

  Widget _buildTranscriptContent(List<TranscriptSegment> segments) {
    if (segments.isEmpty) {
      return Container(
        padding: const EdgeInsets.symmetric(vertical: 32),
        child: Center(
          child: Text(
            'Transcript will appear here...',
            style: TextStyle(
              fontSize: 14,
              color: ResponsiveHelper.textTertiary,
              fontStyle: FontStyle.italic,
            ),
          ),
        ),
      );
    }

    // Show the most recent segments (last 10)
    final recentSegments = segments.length > 10 ? segments.sublist(segments.length - 10) : segments;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: recentSegments.map((segment) {
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Speaker info
              Row(
                children: [
                  Container(
                    width: 4,
                    height: 4,
                    decoration: BoxDecoration(
                      color: segment.isUser
                          ? ResponsiveHelper.purplePrimary.withOpacity(0.8)
                          : ResponsiveHelper.textTertiary,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    segment.isUser ? 'You' : 'Speaker ${segment.speakerId}',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: segment.isUser ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 4),

              // Transcript text
              Text(
                segment.text.trim(),
                style: TextStyle(
                  fontSize: 14,
                  height: 1.4,
                  color: ResponsiveHelper.textPrimary,
                ),
              ),
            ],
          ),
        );
      }).toList(),
    );
  }

  Widget _buildLiveTranscriptSection(List<TranscriptSegment> segments, bool isRecording) {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Transcript header with status
          Container(
            padding: const EdgeInsets.only(bottom: 12),
            child: Row(
              children: [
                Container(
                  width: 6,
                  height: 6,
                  decoration: BoxDecoration(
                    color: isRecording ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textQuaternary,
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  'Live Transcript',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: ResponsiveHelper.textSecondary,
                    letterSpacing: 0.2,
                  ),
                ),
                if (segments.isNotEmpty) ...[
                  const Spacer(),
                  Text(
                    '${segments.length} segment${segments.length == 1 ? '' : 's'}',
                    style: TextStyle(
                      fontSize: 12,
                      color: ResponsiveHelper.textQuaternary,
                    ),
                  ),
                ],
              ],
            ),
          ),

          // Live transcript content
          Container(
            width: double.infinity,
            constraints: const BoxConstraints(
              minHeight: 80,
              maxHeight: 240,
            ),
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
                    padding: const EdgeInsets.all(24),
                    child: Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.transcribe_rounded,
                            color: ResponsiveHelper.textQuaternary,
                            size: 24,
                          ),
                          const SizedBox(height: 8),
                          Text(
                            isRecording ? 'Listening for audio...' : 'Start recording to see live transcript',
                            style: TextStyle(
                              fontSize: 14,
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
                    reverse: true,
                    padding: const EdgeInsets.all(16),
                    child: _buildLiveTranscriptContent(segments),
                  ),
          ),
        ],
      ),
    );
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
                      ? ResponsiveHelper.purplePrimary.withOpacity(0.8)
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
                        style: TextStyle(
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

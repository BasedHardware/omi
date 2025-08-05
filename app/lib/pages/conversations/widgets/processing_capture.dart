import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversations/widgets/capture.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/processing_conversations/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';

import 'package:omi/widgets/gradient_waveform.dart';
import 'package:provider/provider.dart';

class ConversationCaptureWidget extends StatefulWidget {
  const ConversationCaptureWidget({super.key});

  @override
  State<ConversationCaptureWidget> createState() => _ConversationCaptureWidgetState();
}

class _ConversationCaptureWidgetState extends State<ConversationCaptureWidget> with SingleTickerProviderStateMixin {
  bool _isPhoneMicPaused = false;
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 1000),
      vsync: this,
    );
    _pulseAnimation = Tween<double>(
      begin: 0.4,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _pulseController,
      curve: Curves.easeInOut,
    ));
    _pulseController.repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  Widget _buildPulsatingDot({required Color color, bool isPulsating = true}) {
    if (!isPulsating) {
      return Container(
        width: 6,
        height: 6,
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
        ),
      );
    }

    return AnimatedBuilder(
      animation: _pulseAnimation,
      builder: (context, child) {
        return Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(
            color: color.withValues(alpha: _pulseAnimation.value),
            shape: BoxShape.circle,
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer3<CaptureProvider, DeviceProvider, ConnectivityProvider>(
        builder: (context, provider, deviceProvider, connectivityProvider, child) {
      var topConvoId = (provider.conversationProvider?.conversations ?? []).isNotEmpty
          ? provider.conversationProvider!.conversations.first.id
          : null;

      var header = _getConversationHeader(context);
      if (header == null) {
        return const SizedBox.shrink();
      }

      return GestureDetector(
        onTap: () async {
          if (provider.outOfCredits || (provider.segments.isEmpty && provider.photos.isEmpty)) return;
          routeToPage(context, ConversationCapturingPage(topConversationId: topConvoId));
        },
        child: Container(
          margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          width: double.maxFinite,
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(10, 18, 10, 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Use unified recording UI for all recording types
                _buildUnifiedRecordingUI(provider, header),
              ],
            ),
          ),
        ),
      );
    });
  }

  _toggleRecording(BuildContext context, CaptureProvider provider) async {
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
      } else if (recordingState == RecordingState.initialising) {
        debugPrint('initialising, have to wait');
      } else {
        await provider.streamSystemAudioRecording();
      }
    } else if (provider.havingRecordingDevice) {
      // Device recording logic - add pause/resume for device recording
      if (recordingState == RecordingState.deviceRecord && !provider.isPaused) {
        // Pause device recording
        await provider.pauseDeviceRecording();
      } else if (provider.isPaused && recordingState == RecordingState.pause) {
        // Resume device recording
        await provider.resumeDeviceRecording();
      }
    } else {
      // Phone mic logic - use local state to track pause
      if (recordingState == RecordingState.record && !_isPhoneMicPaused) {
        // Pause recording
        setState(() {
          _isPhoneMicPaused = true;
        });
        await provider.stopStreamRecording();
        MixpanelManager().phoneMicRecordingStopped();
      } else if (_isPhoneMicPaused) {
        // Resume recording
        setState(() {
          _isPhoneMicPaused = false;
        });
        await provider.streamRecording();
        MixpanelManager().phoneMicRecordingStarted();
      } else if (recordingState == RecordingState.initialising) {
        debugPrint('initialising, have to wait');
      } else {
        setState(() {
          _isPhoneMicPaused = false;
        });
        await provider.streamRecording();
        MixpanelManager().phoneMicRecordingStarted();
      }
    }
  }

  Widget? _getConversationHeader(BuildContext context) {
    var captureProvider = context.read<CaptureProvider>();
    var connectivityProvider = context.read<ConnectivityProvider>();

    bool internetConnectionStateOk = connectivityProvider.isConnected;
    bool deviceServiceStateOk = captureProvider.recordingDeviceServiceReady;
    bool transcriptServiceStateOk = captureProvider.transcriptServiceReady;
    bool isHavingTranscript = captureProvider.segments.isNotEmpty;
    bool isHavingPhotos = captureProvider.photos.isNotEmpty;
    bool isHavingDesireDevice = SharedPreferencesUtil().btDevice.id.isNotEmpty;
    bool isHavingRecordingDevice = captureProvider.havingRecordingDevice;

    bool isUsingPhoneMic = captureProvider.recordingState == RecordingState.record ||
        captureProvider.recordingState == RecordingState.initialising ||
        captureProvider.recordingState == RecordingState.pause;

    // Check if any recording is active (phone mic, system audio, or device recording)
    bool isAnyRecordingActive = captureProvider.recordingState == RecordingState.record ||
        captureProvider.recordingState == RecordingState.systemAudioRecord ||
        captureProvider.recordingState == RecordingState.deviceRecord ||
        captureProvider.recordingState == RecordingState.initialising ||
        captureProvider.recordingState == RecordingState.pause ||
        captureProvider.isPaused ||
        _isPhoneMicPaused;

    // Hide the widget when no recording is active and there are no segments or photos
    if (!isAnyRecordingActive && !isHavingTranscript && !isHavingPhotos && !isHavingRecordingDevice) {
      return null;
    }

    // Left
    Widget? left;
    if (isUsingPhoneMic || !isHavingDesireDevice) {
      left = Center(
        child: getPhoneMicRecordingButton(
          context,
          () => _toggleRecording(context, captureProvider),
          captureProvider.recordingState,
          isPhoneMicPaused: _isPhoneMicPaused,
        ),
      );
    } else if (!isAnyRecordingActive &&
        !deviceServiceStateOk &&
        !transcriptServiceStateOk &&
        !isHavingTranscript &&
        !isHavingDesireDevice) {
      return null; // not recording and not ready
    } else if (!deviceServiceStateOk) {
      left = Row(
        children: [
          const Icon(Icons.record_voice_over),
          const SizedBox(width: 12),
          Container(
            decoration: BoxDecoration(
              color: Color(0xFF35343B),
              borderRadius: BorderRadius.circular(16),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Text(
              'Waiting for device...',
              style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
              maxLines: 1,
            ),
          ),
        ],
      );
    } else {
      left = Row(
        children: [
          const SizedBox(width: 14),
          const Icon(Icons.record_voice_over),
          const SizedBox(width: 12),
          Container(
            decoration: BoxDecoration(
              color: Color(0xFF35343B),
              borderRadius: BorderRadius.circular(16),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Text(
              (isHavingTranscript || isHavingPhotos) ? 'In progress...' : 'Say something...',
              style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
              maxLines: 1,
            ),
          ),
        ],
      );
    }

    // Right
    Widget? statusIndicator;
    var stateText = "";

    // Always check pause state first with highest priority (both desktop and phone)
    if (captureProvider.isPaused || _isPhoneMicPaused) {
      stateText = "Paused";
      statusIndicator = const PausedStatusIndicator();
    } else if (!isHavingRecordingDevice && !isUsingPhoneMic) {
      stateText = "";
    } else if (transcriptServiceStateOk && (isUsingPhoneMic || isHavingRecordingDevice)) {
      var lastEvent = captureProvider.transcriptionServiceStatuses.lastOrNull;
      if (lastEvent is MessageServiceStatusEvent) {
        if (lastEvent.status == "ready") {
          stateText = "Listening";
          statusIndicator = const RecordingStatusIndicator();
        } else {
          bool transcriptionDiagnosticEnabled = SharedPreferencesUtil().transcriptionDiagnosticEnabled;
          stateText = transcriptionDiagnosticEnabled ? (lastEvent.statusText ?? "") : "Connecting";
        }
      } else {
        stateText = "Connecting";
      }
    } else if (!internetConnectionStateOk) {
      stateText = "Waiting for network";
    } else if (!transcriptServiceStateOk) {
      stateText = "Connecting";
    }
    Widget right = stateText.isNotEmpty || statusIndicator != null
        ? Expanded(
            child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Text(
                stateText,
                style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                maxLines: 1,
                textAlign: TextAlign.end,
              ),
              if (statusIndicator != null) ...[
                const SizedBox(width: 8),
                SizedBox(
                  width: 16,
                  height: 16,
                  child: statusIndicator,
                )
              ],
            ],
          ))
        : const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(left: 0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          left,
          right,
        ],
      ),
    );
  }

  Widget _buildUnifiedRecordingUI(CaptureProvider provider, Widget? header) {
    bool isDeviceRecording = provider.havingRecordingDevice &&
        (provider.recordingState == RecordingState.deviceRecord || provider.recordingState == RecordingState.pause);
    bool isPhoneRecording = provider.recordingState == RecordingState.record ||
        provider.recordingState == RecordingState.systemAudioRecord ||
        provider.recordingState == RecordingState.initialising ||
        _isPhoneMicPaused;

    // Determine pause state based on recording type
    bool isPaused = false;
    if (isDeviceRecording) {
      isPaused = provider.isPaused && provider.recordingState == RecordingState.pause;
    } else if (isPhoneRecording) {
      isPaused = _isPhoneMicPaused || provider.isPaused;
    }

    // When recording is active, show the unified UI design
    if (isDeviceRecording || isPhoneRecording) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 4),
          // Top row with status tag and controls
          Padding(
            padding: const EdgeInsets.only(left: 8, right: 6),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                // Left: Status tag
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: const Color(0xFF35343B),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        isPaused ? (isDeviceRecording ? 'Muted' : 'Paused') : 'Listening',
                        style: const TextStyle(
                          color: Color(0xFFC9CBCF),
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(width: 6),
                      _buildPulsatingDot(
                        color: isPaused ? const Color(0xFFFF9500) : const Color(0xFFFE5D50),
                        isPulsating: !isPaused,
                      ),
                    ],
                  ),
                ),
                // Right: Control buttons for both device and phone recording
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Pause/Resume button
                    GestureDetector(
                      onTap: () {
                        HapticFeedback.mediumImpact();
                        _toggleRecording(context, provider);
                      },
                      child: Container(
                        width: 28,
                        height: 28,
                        decoration: BoxDecoration(
                          color: isPaused
                              ? isDeviceRecording
                                  ? const Color(0xFFFE5D50)
                                  : const Color(0xFF7C3AED)
                              : isDeviceRecording
                                  ? const Color(0xFF35343B)
                                  : const Color(0xFFFF9500),
                          shape: BoxShape.circle,
                        ),
                        child: Center(
                          child: FaIcon(
                            isPaused
                                ? isDeviceRecording
                                    ? FontAwesomeIcons.microphoneSlash
                                    : FontAwesomeIcons.play
                                : isDeviceRecording
                                    ? FontAwesomeIcons.microphone
                                    : FontAwesomeIcons.pause,
                            color: Colors.white,
                            size: 12,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 4),
          // Show transcript below controls during recording
          if (provider.segments.isNotEmpty) ...[
            Container(
              width: double.infinity,
              margin: const EdgeInsets.only(top: 12, bottom: 4),
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: _AutoScrollingText(
                text: provider.segments.map((segment) => segment.text).join(' '),
              ),
            ),
          ],
          // Show photos widget if there are photos
          if (provider.photos.isNotEmpty) ...[
            const SizedBox(height: 8),
            const LiteCaptureWidget(),
          ],
        ],
      );
    } else {
      // For non-recording states, show the original header-based UI
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (header != null) header,
          // Show content when there are segments/photos
          if (provider.segments.isNotEmpty || provider.photos.isNotEmpty) ...[
            const SizedBox(height: 24),
            if (provider.segments.isNotEmpty) ...[
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: _AutoScrollingText(
                  text: provider.segments.map((segment) => segment.text).join(' '),
                ),
              ),
            ],
            // Show photos widget if there are photos
            if (provider.photos.isNotEmpty) ...[
              const SizedBox(height: 8),
              const LiteCaptureWidget(),
            ],
          ],
        ],
      );
    }
  }
}

class _AutoScrollingText extends StatefulWidget {
  final String text;

  const _AutoScrollingText({required this.text});

  @override
  State<_AutoScrollingText> createState() => _AutoScrollingTextState();
}

class _AutoScrollingTextState extends State<_AutoScrollingText> {
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(_AutoScrollingText oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.text != oldWidget.text) {
      // Auto scroll to the end when text changes
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scrollController.hasClients) {
          _scrollController.animateTo(
            _scrollController.position.maxScrollExtent,
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeOut,
          );
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      controller: _scrollController,
      scrollDirection: Axis.horizontal,
      child: Text(
        widget.text,
        style: const TextStyle(
          color: Color(0xFF6A6B71),
          fontSize: 16,
          height: 1.4,
        ),
        maxLines: 1,
        overflow: TextOverflow.visible,
      ),
    );
  }
}

class RecordingStatusIndicator extends StatefulWidget {
  const RecordingStatusIndicator({super.key});

  @override
  State<RecordingStatusIndicator> createState() => _RecordingStatusIndicatorState();
}

class _RecordingStatusIndicatorState extends State<RecordingStatusIndicator> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _opacityAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1000), // Blink every half second
      vsync: this,
    )..repeat(reverse: true);
    _opacityAnim = Tween<double>(begin: 1.0, end: 0.2).animate(_controller);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacityAnim,
      child: const Icon(Icons.fiber_manual_record, color: Colors.red, size: 16.0),
    );
  }
}

class PausedStatusIndicator extends StatefulWidget {
  const PausedStatusIndicator({super.key});

  @override
  State<PausedStatusIndicator> createState() => _PausedStatusIndicatorState();
}

class _PausedStatusIndicatorState extends State<PausedStatusIndicator> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _opacityAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1000), // Blink every half second
      vsync: this,
    )..repeat(reverse: true);
    _opacityAnim = Tween<double>(begin: 1.0, end: 0.2).animate(_controller);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacityAnim,
      child: const Icon(Icons.fiber_manual_record, color: Colors.orange, size: 16.0),
    );
  }
}

getPhoneMicRecordingButton(BuildContext context, VoidCallback toggleRecordingCb, RecordingState currentActualState,
    {bool isPhoneMicPaused = false}) {
  if (SharedPreferencesUtil().btDevice.id.isNotEmpty && (!PlatformService.isDesktop)) {
    // If a BT device is configured and we are NOT on desktop, don't show this button.
    return const SizedBox.shrink();
  }
  // If on desktop, AND a BT device is connected, this button should still be hidden
  // as the primary interaction should be via the BT device, not system audio as a fallback to phone mic.
  // This button is primarily for when NO BT device is the target.
  final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
  if (PlatformService.isDesktop &&
      deviceProvider.connectedDevice != null &&
      SharedPreferencesUtil().btDevice.id == deviceProvider.connectedDevice!.id) {
    return const SizedBox.shrink();
  }

  final bool isDesktop = PlatformService.isDesktop;
  String text;
  Widget icon;
  bool isLoading = currentActualState == RecordingState.initialising;

  if (isDesktop) {
    if (isLoading) {
      text = 'Initialising System Audio';
      icon = const SizedBox(
        height: 8,
        width: 8,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          color: Colors.white,
        ),
      );
    } else if (currentActualState == RecordingState.systemAudioRecord) {
      text = 'Stop Recording';
      icon = const Icon(Icons.stop, color: Colors.red, size: 12);
    } else {
      text = 'Continue Recording';
      icon = const Icon(Icons.mic, size: 18);
    }
  } else {
    // Phone Mic
    if (isLoading) {
      text = 'Initialising Recorder';
      icon = const SizedBox(
        height: 8,
        width: 8,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          color: Colors.white,
        ),
      );
    } else if (currentActualState == RecordingState.record) {
      text = 'Pause Recording';
      icon = Container(
        margin: const EdgeInsets.only(right: 4),
        width: 24,
        height: 24,
        decoration: const BoxDecoration(
          color: Colors.orange,
          shape: BoxShape.circle,
        ),
        child: const Center(
          child: Icon(Icons.pause, color: Colors.white, size: 14),
        ),
      );
    } else if (isPhoneMicPaused) {
      text = 'Resume Recording';
      icon = Container(
        margin: const EdgeInsets.only(right: 4),
        width: 24,
        height: 24,
        decoration: const BoxDecoration(
          color: Color(0xFF7C3AED), // Deep purple
          shape: BoxShape.circle,
        ),
        child: const Center(
          child: Icon(Icons.play_arrow, color: Colors.white, size: 14),
        ),
      );
    } else {
      text = 'Continue Recording';
      icon = const Icon(Icons.mic, size: 18);
    }
  }

  return MaterialButton(
    onPressed: isLoading ? null : toggleRecordingCb,
    child: Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.start,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        icon,
        const SizedBox(width: 4),
        Text(
          text,
          style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white, fontWeight: FontWeight.w500),
        ),
        const SizedBox(width: 4),
      ],
    ),
  );
}

Widget getProcessingConversationsWidget(List<ServerConversation> conversations) {
  // FIXME, this has to be a single one always, and also a conversation obj
  if (conversations.isEmpty) {
    return const SliverToBoxAdapter(child: SizedBox.shrink());
  }
  return SliverList(
    delegate: SliverChildBuilderDelegate(
      (context, index) {
        var pm = conversations[index];
        return Padding(
          padding: const EdgeInsets.fromLTRB(0, 20, 0, 0),
          child: ProcessingConversationWidget(conversation: pm),
        );
      },
      childCount: conversations.length,
    ),
  );
}

// PROCESSING CONVERSATION

class ProcessingConversationWidget extends StatefulWidget {
  final ServerConversation conversation;

  const ProcessingConversationWidget({
    super.key,
    required this.conversation,
  });

  @override
  State<ProcessingConversationWidget> createState() => _ProcessingConversationWidgetState();
}

class _ProcessingConversationWidgetState extends State<ProcessingConversationWidget> {
  @override
  Widget build(BuildContext context) {
    return Consumer3<CaptureProvider, DeviceProvider, ConnectivityProvider>(
        builder: (context, provider, deviceProvider, connectivityProvider, child) {
      return GestureDetector(
          onTap: () async {
            routeToPage(
              context,
              ProcessingConversationPage(
                conversation: widget.conversation,
              ),
            );
          },
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 16),
            width: double.maxFinite,
            decoration: BoxDecoration(
              color: const Color(0xFF1F1F25),
              borderRadius: BorderRadius.circular(16.0),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _getConversationHeader(context),
                  (widget.conversation.transcriptSegments.isNotEmpty || widget.conversation.photos.isNotEmpty)
                      ? Column(
                          children: [
                            const SizedBox(height: 8),
                            getLiteTranscriptWidget(
                              widget.conversation.transcriptSegments,
                              widget.conversation.photos,
                              null,
                            ),
                            const SizedBox(height: 8),
                          ],
                        )
                      : const SizedBox.shrink(),
                ],
              ),
            ),
          ));
    });
  }

  _getConversationHeader(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                ),
              ),
              const SizedBox(width: 20),
              Container(
                decoration: BoxDecoration(
                  color: Color(0xFF35343B),
                  borderRadius: BorderRadius.circular(16),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                child: Text(
                  'Processing',
                  style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                  maxLines: 1,
                ),
              ),
            ],
          )
        ],
      ),
    );
  }
}

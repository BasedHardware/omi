import 'dart:async';

import 'package:flutter/material.dart';

import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/pages/speech_profile/percentage_bar_progress.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/device_widget.dart';

class SpeechProfileWidget extends StatefulWidget {
  final VoidCallback goNext;
  final VoidCallback onSkip;

  const SpeechProfileWidget({super.key, required this.goNext, required this.onSkip});

  @override
  State<SpeechProfileWidget> createState() => _SpeechProfileWidgetState();
}

class _SpeechProfileWidgetState extends State<SpeechProfileWidget> with TickerProviderStateMixin {
  late AnimationController _questionAnimationController;
  late Animation<double> _questionFadeAnimation;
  SpeechProfileProvider? _speechProvider;
  // Guards the pre-flight availability check itself, which runs before
  // provider.isInitialising ever becomes true — without this, a rapid double
  // tap during that network round-trip could start two concurrent sessions.
  bool _isCheckingAvailability = false;

  @override
  void initState() {
    super.initState();
    _questionAnimationController = AnimationController(duration: const Duration(milliseconds: 500), vsync: this);
    _questionFadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _questionAnimationController, curve: Curves.easeInOut));

    // Onboarding completion is now handled by the completion screen
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // This now reads the shared app-root SpeechProfileProvider (see main.dart)
    // rather than a fresh instance built just for onboarding, so a stale
    // question/transcript/completed-profile from an earlier Settings-triggered
    // recording (e.g. a prior account in the same app session) must be reset
    // before this step is shown, not just on the Settings page's own entry.
    if (_speechProvider == null) {
      _speechProvider = context.read<SpeechProfileProvider>();
      // Only reset a leftover Settings session. A remount mid-Get-Started
      // used to call close() here and bounce back to the quiet-place intro.
      if (!_speechProvider!.startedRecording && !_speechProvider!.isInitialising && !_speechProvider!.isInitialised) {
        _speechProvider!.close();
      }
    }
  }

  @override
  void dispose() {
    _speechProvider?.forceCompletionTimer?.cancel();
    _speechProvider?.forceCompletionTimer = null;

    _scrollController.dispose();
    _questionAnimationController.dispose();

    super.dispose();
  }

  final ScrollController _scrollController = ScrollController();

  void scrollDown() async {
    if (!_scrollController.hasClients) return;
    await Future.delayed(const Duration(milliseconds: 250));
    if (!mounted || !_scrollController.hasClients) return;
    _scrollController.animateTo(
      _scrollController.position.maxScrollExtent,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
    );
  }

  String _getLoadingText(BuildContext context, SpeechProfileLoadingState state) {
    switch (state) {
      case SpeechProfileLoadingState.uploading:
        return context.l10n.uploadingVoiceProfile;
      case SpeechProfileLoadingState.memorizing:
        return context.l10n.memorizingYourVoice;
      case SpeechProfileLoadingState.personalizing:
        return context.l10n.personalizingExperience;
      case SpeechProfileLoadingState.allSet:
        return context.l10n.youreAllSet;
    }
  }

  @override
  Widget build(BuildContext context) {
    Future restartDeviceRecording() async {
      Logger.debug("restartDeviceRecording $mounted");

      // Restart device recording, clear transcripts
      if (mounted) {
        Provider.of<CaptureProvider>(context, listen: false).clearTranscripts();
        final device = Provider.of<SpeechProfileProvider>(context, listen: false).deviceProvider?.connectedDevice;
        if (device != null) {
          Provider.of<CaptureProvider>(context, listen: false).streamDeviceRecording(device: device);
        }
      }
    }

    Future stopAllRecording() async {
      Logger.debug("stopAllRecording $mounted");
      if (mounted) {
        final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
        // Stop any active device recording
        await captureProvider.stopStreamDeviceRecording();
      }
    }

    return PopScope(
      canPop: true,
      onPopInvokedWithResult: (didPop, result) async {
        final speechProvider = context.read<SpeechProfileProvider>();
        speechProvider.close();
        restartDeviceRecording();
      },
      child: Consumer2<SpeechProfileProvider, CaptureProvider>(
        builder: (context, provider, _, child) {
          return MessageListener<SpeechProfileProvider>(
            showInfo: (info) {
              if (info == 'SCROLL_DOWN') {
                scrollDown();
              } else if (info == 'NEXT_QUESTION') {
                if (!mounted) return;

                _questionAnimationController
                  ..reset()
                  ..forward();
              } else if (info == 'SKIP_UNAVAILABLE') {
                AppSnackbar.showSnackbarError(context.l10n.reconnecting);
              }
            },
            showError: (error) {
              if (error == 'SOCKET_INIT_FAILED') {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () => Navigator.pop(context),
                    () {},
                    context.l10n.connectionError,
                    context.l10n.connectionErrorDesc,
                    okButtonText: context.l10n.ok,
                    singleButton: true,
                  ),
                  barrierDismissible: false,
                );
              } else if (error == 'MULTIPLE_SPEAKERS') {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () {
                      provider.close();
                      Navigator.pop(context);
                    },
                    () {},
                    context.l10n.invalidRecordingMultipleSpeakers,
                    context.l10n.multipleSpeakersDesc,
                    okButtonText: context.l10n.tryAgain,
                    singleButton: true,
                  ),
                  barrierDismissible: false,
                );
              } else if (error == 'TOO_SHORT') {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () {
                      Navigator.pop(context);
                      //  Navigator.pop(context);
                    },
                    () {},
                    context.l10n.invalidRecordingMultipleSpeakers,
                    context.l10n.tooShortDesc,
                    okButtonText: context.l10n.ok,
                    singleButton: true,
                  ),
                  barrierDismissible: false,
                );
              } else if (error == 'UPLOAD_FAILED') {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () {
                      Navigator.pop(context);
                    },
                    () {},
                    context.l10n.connectionError,
                    context.l10n.connectionErrorDesc,
                    okButtonText: context.l10n.ok,
                    singleButton: true,
                  ),
                  barrierDismissible: false,
                );
              } else if (error == 'INVALID_RECORDING') {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () {
                      Navigator.pop(context);
                      //  Navigator.pop(context);
                    },
                    () {},
                    // TODO: improve this
                    context.l10n.invalidRecordingMultipleSpeakers,
                    context.l10n.invalidRecordingDesc,
                    okButtonText: context.l10n.ok,
                    singleButton: true,
                  ),
                  barrierDismissible: false,
                );
              } else if (error == "NO_SPEECH") {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () {
                      Navigator.pop(context);
                    },
                    () {},
                    context.l10n.areYouThere,
                    context.l10n.noSpeechDesc,
                    okButtonText: context.l10n.ok,
                    singleButton: true,
                  ),
                  barrierDismissible: false,
                );
              } else if (error == 'SOCKET_DISCONNECTED' || error == 'SOCKET_ERROR') {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () {
                      provider.close();
                      Navigator.pop(context);
                    },
                    () {},
                    context.l10n.connectionLost,
                    context.l10n.connectionLostDesc,
                    okButtonText: context.l10n.tryAgain,
                    singleButton: true,
                  ),
                  barrierDismissible: false,
                );
              } else if (error == 'STT_UNAVAILABLE') {
                // The provider already gave up reconnecting after repeated
                // 1011 closes with no captured speech, so offer the same
                // way out as the "Skip for now" link instead of a "Try
                // again" that would only restart the same failing loop.
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () {
                      provider.close();
                      Navigator.pop(context);
                      widget.onSkip();
                    },
                    () {},
                    context.l10n.connectionLost,
                    context.l10n.connectionLostDesc,
                    okButtonText: context.l10n.skipForNow,
                    singleButton: true,
                  ),
                  barrierDismissible: false,
                );
              }
            },
            child: Column(
              children: [
                Expanded(
                  child: Align(
                    alignment: Alignment.bottomCenter,
                    child: Padding(
                      padding: const EdgeInsets.only(bottom: 24),
                      child: Stack(
                        alignment: Alignment.center,
                        children: [
                          if (provider.startedRecording && !provider.profileCompleted && !provider.uploadingProfile)
                            // Mic feedback: a plain white glow behind the device graphic
                            // that grows brighter/larger with mic level, matching the
                            // Settings speech-profile redo page.
                            AnimatedContainer(
                              duration: const Duration(milliseconds: 150),
                              width: 180 + provider.micLevel * 140,
                              height: 180 + provider.micLevel * 140,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.white.withValues(alpha: 0.12 + provider.micLevel * 0.35),
                                    blurRadius: 50 + provider.micLevel * 60,
                                    spreadRadius: 8 + provider.micLevel * 36,
                                  ),
                                ],
                              ),
                            ),
                          DeviceAnimationWidget(
                            animatedBackground: true,
                            deviceType: provider.device?.type,
                            deviceName: provider.device?.name,
                            modelNumber: provider.device?.modelNumber,
                            isConnected: provider.device != null,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                Container(
                  width: double.infinity,
                  padding: EdgeInsets.fromLTRB(32, 0, 32, MediaQuery.of(context).padding.bottom + 8),
                  decoration: const BoxDecoration(
                    color: Colors.black,
                    borderRadius: BorderRadius.only(topLeft: Radius.circular(40), topRight: Radius.circular(40)),
                  ),
                  child: SafeArea(
                    top: false,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const SizedBox(height: 32),

                        // Title — hidden once the profile is complete or
                        // uploading, matching the Settings redo page (which has
                        // no title in those states, only the All-Done/loading UI).
                        if (!provider.profileCompleted && !provider.uploadingProfile) ...[
                          Text(
                            provider.startedRecording ? 'Answer with your voice:' : 'Please find a quiet place',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 28,
                              fontWeight: FontWeight.bold,
                              height: 1.2,
                              fontFamily: 'Manrope',
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 16),
                        ],

                        // Content area changes based on state
                        if (!provider.startedRecording) ...[
                          // Intro text
                          Text(
                            'Omi needs to learn your goals and your voice. Answer questions with your voice. You\'ll be able to modify it later.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.6),
                              fontSize: 16,
                              height: 1.5,
                              fontFamily: 'Manrope',
                            ),
                          ),

                          const SizedBox(height: 32),

                          // Get Started button
                          (provider.isInitialising || _isCheckingAvailability)
                              ? const CircularProgressIndicator(color: Colors.white)
                              : SizedBox(
                                  width: double.infinity,
                                  height: 56,
                                  child: ElevatedButton(
                                    onPressed: () async {
                                      if (_isCheckingAvailability) return;
                                      setState(() => _isCheckingAvailability = true);

                                      // Pre-flight: don't enter the recording UI at all if
                                      // the streaming primary is known down — otherwise the
                                      // socket connects and audio uploads, but no
                                      // question/progress ever arrives.
                                      final available = await isSttAvailable();
                                      if (mounted) setState(() => _isCheckingAvailability = false);
                                      if (!available) {
                                        if (!context.mounted) return;
                                        await showDialog(
                                          context: context,
                                          builder: (c) => getDialog(
                                            context,
                                            () => Navigator.pop(context),
                                            () {},
                                            context.l10n.connectionError,
                                            context.l10n.connectionErrorDesc,
                                            okButtonText: context.l10n.ok,
                                            singleButton: true,
                                          ),
                                          barrierDismissible: false,
                                        );
                                        return;
                                      }

                                      if (!context.mounted) return;
                                      await stopAllRecording();

                                      // Initialize speech profile with phone mic as input source
                                      bool success = await provider.initialise(
                                        usePhoneMic: true,
                                        isOnboardingFlow: true,
                                        processConversationCallback: () {
                                          Provider.of<CaptureProvider>(
                                            context,
                                            listen: false,
                                          ).forceProcessingCurrentConversation();
                                        },
                                      );

                                      if (!success) {
                                        return;
                                      }

                                      provider.forceCompletionTimer = Timer(
                                        Duration(seconds: provider.maxDuration),
                                        () async {
                                          provider.finalize();
                                        },
                                      );

                                      if (!mounted) return;
                                      _questionAnimationController.forward();
                                    },
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: Colors.white,
                                      foregroundColor: Colors.black,
                                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                                      elevation: 0,
                                    ),
                                    child: Text(
                                      context.l10n.getStarted,
                                      style: const TextStyle(
                                        fontSize: 18,
                                        fontWeight: FontWeight.w600,
                                        fontFamily: 'Manrope',
                                      ),
                                    ),
                                  ),
                                ),
                          // Only relevant while actually recording with the phone mic —
                          // matches the Settings speech-profile page's disclaimer.
                          if (provider.device == null)
                            Padding(
                              padding: const EdgeInsets.only(top: 16),
                              child: Text(
                                context.l10n.noDeviceConnectedUseMic,
                                style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                                textAlign: TextAlign.center,
                              ),
                            ),
                        ] else if (provider.profileCompleted) ...[
                          // All Done state
                          const SizedBox(height: 16),
                          SizedBox(
                            width: double.infinity,
                            height: 56,
                            child: ElevatedButton(
                              onPressed: () => widget.goNext(),
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.white,
                                foregroundColor: Colors.black,
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                                elevation: 0,
                              ),
                              child: Text(
                                context.l10n.allDone,
                                style: const TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.w600,
                                  fontFamily: 'Manrope',
                                ),
                              ),
                            ),
                          ),
                        ] else if (provider.uploadingProfile) ...[
                          // Uploading state
                          const SizedBox(height: 16),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const SizedBox(
                                height: 24,
                                width: 24,
                                child: Center(
                                  child: CircularProgressIndicator(
                                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 16),
                              Text(
                                _getLoadingText(context, provider.loadingState),
                                style: const TextStyle(color: Colors.white, fontSize: 16, fontFamily: 'Manrope'),
                              ),
                            ],
                          ),
                          const SizedBox(height: 16),
                        ] else ...[
                          // Recording state - transcript + question + progress
                          // Transcript styling matches the Settings speech-profile page
                          // exactly (fontSize 20, full-white, taller viewport), hidden
                          // entirely until the first words arrive.
                          if (provider.text.isNotEmpty) ...[
                            ShaderMask(
                              shaderCallback: (bounds) {
                                if (provider.text.split(' ').length < 10) {
                                  return const LinearGradient(
                                    colors: [Colors.white, Colors.white],
                                  ).createShader(bounds);
                                }
                                return const LinearGradient(
                                  colors: [Colors.transparent, Colors.white],
                                  stops: [0.0, 0.5],
                                  begin: Alignment.topCenter,
                                  end: Alignment.bottomCenter,
                                ).createShader(bounds);
                              },
                              blendMode: BlendMode.dstIn,
                              child: SizedBox(
                                height: 130,
                                child: ListView(
                                  controller: _scrollController,
                                  shrinkWrap: true,
                                  physics: const NeverScrollableScrollPhysics(),
                                  children: [
                                    Text(
                                      provider.text,
                                      textAlign: TextAlign.center,
                                      style: const TextStyle(
                                        color: Colors.white,
                                        fontSize: 20,
                                        fontWeight: FontWeight.w400,
                                        height: 1.5,
                                        fontFamily: 'Manrope',
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            const SizedBox(height: 8),
                          ],

                          // Current question
                          FadeTransition(
                            opacity: _questionFadeAnimation,
                            child: Text(
                              provider.currentQuestion,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 24,
                                height: 1.3,
                                fontFamily: 'Manrope',
                                fontWeight: FontWeight.w600,
                              ),
                              textAlign: TextAlign.center,
                            ),
                          ),

                          const SizedBox(height: 12),

                          // Progress bar
                          SizedBox(
                            width: double.infinity,
                            child: ProgressBarWithPercentage(
                              progressValue: provider.questionProgress,
                              showPercentageAsPlainText: true,
                            ),
                          ),

                          const SizedBox(height: 8),

                          OutlinedButton(
                            onPressed: () {
                              provider.close();
                              widget.onSkip();
                            },
                            style: OutlinedButton.styleFrom(
                              side: const BorderSide(color: Colors.white),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
                            ),
                            child: Text(
                              context.l10n.skipForNow,
                              style: const TextStyle(color: Colors.white, fontSize: 14, fontFamily: 'Manrope'),
                            ),
                          ),

                          if (provider.device == null)
                            Padding(
                              padding: const EdgeInsets.only(top: 8),
                              child: Text(
                                context.l10n.noDeviceConnectedUseMic,
                                style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                                textAlign: TextAlign.center,
                              ),
                            ),
                        ],
                      ],
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

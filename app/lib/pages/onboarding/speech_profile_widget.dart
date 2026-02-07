import 'dart:async';

import 'package:flutter/material.dart';

import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/widgets/dialog.dart';

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

  @override
  void initState() {
    super.initState();
    _questionAnimationController = AnimationController(
      duration: const Duration(milliseconds: 500),
      vsync: this,
    );
    _questionFadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _questionAnimationController, curve: Curves.easeInOut),
    );

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      // Check if user has set primary language
      if (!context.read<HomeProvider>().hasSetPrimaryLanguage) {
        await LanguageSelectionDialog.show(context);
      }
    });
    SharedPreferencesUtil().onboardingCompleted = true;
    updateUserOnboardingState(completed: true);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _speechProvider ??= context.read<SpeechProfileProvider>();
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
    if (_scrollController.hasClients) {
      await Future.delayed(const Duration(milliseconds: 250));
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    }
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
      onPopInvoked: (didPop) async {
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
              }
            },
            child: Column(
              children: [
                // Background area - takes remaining space
                Expanded(
                  child: Container(), // Just takes up space for background image
                ),

                // Bottom drawer card - wraps content
                Container(
                  width: double.infinity,
                  padding: EdgeInsets.fromLTRB(32, 24, 32, MediaQuery.of(context).padding.bottom + 8),
                  decoration: const BoxDecoration(
                    color: Colors.black,
                    borderRadius: BorderRadius.only(
                      topLeft: Radius.circular(40),
                      topRight: Radius.circular(40),
                    ),
                  ),
                  child: SafeArea(
                    top: false,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const SizedBox(height: 8),

                        // Title section
                        if (!provider.startedRecording) ...[
                          Text(
                            context.l10n.speechProfileIntro,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 32,
                              fontWeight: FontWeight.bold,
                              height: 1.2,
                              fontFamily: 'Manrope',
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 12),
                          Text(
                            'Help Omi learn your voice for a personalized experience',
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.7),
                              fontSize: 16,
                              height: 1.4,
                              fontFamily: 'Manrope',
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ] else if (provider.uploadingProfile) ...[
                          const SizedBox(
                            height: 40,
                            width: 40,
                            child: CircularProgressIndicator(
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                              strokeWidth: 3,
                            ),
                          ),
                          const SizedBox(height: 24),
                          Text(
                            _getLoadingText(context, provider.loadingState),
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 24,
                              fontWeight: FontWeight.w600,
                              fontFamily: 'Manrope',
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ] else if (provider.profileCompleted) ...[
                          Text(
                            context.l10n.youreAllSet,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 32,
                              fontWeight: FontWeight.bold,
                              height: 1.2,
                              fontFamily: 'Manrope',
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 12),
                          Text(
                            'Your voice profile has been created successfully',
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.7),
                              fontSize: 16,
                              height: 1.4,
                              fontFamily: 'Manrope',
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ] else ...[
                          // Recording in progress
                          Text(
                            provider.currentQuestion,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 24,
                              fontWeight: FontWeight.bold,
                              height: 1.3,
                              fontFamily: 'Manrope',
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 20),

                          // Simple progress indicator
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                            decoration: BoxDecoration(
                              color: Colors.grey[900],
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(
                                color: Colors.grey[700]!,
                                width: 1,
                              ),
                            ),
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  '${(provider.questionProgress * 100).toInt()}%',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 28,
                                    fontWeight: FontWeight.bold,
                                    fontFamily: 'Manrope',
                                  ),
                                ),
                                const SizedBox(height: 8),
                                ClipRRect(
                                  borderRadius: BorderRadius.circular(8),
                                  child: SizedBox(
                                    width: 200,
                                    height: 6,
                                    child: LinearProgressIndicator(
                                      value: provider.questionProgress,
                                      backgroundColor: Colors.grey[800],
                                      valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 16),

                          // Listening indicator
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Container(
                                  width: 8,
                                  height: 8,
                                  decoration: const BoxDecoration(
                                    color: Colors.greenAccent,
                                    shape: BoxShape.circle,
                                  ),
                                ),
                                const SizedBox(width: 8),
                                Text(
                                  provider.text.isEmpty ? 'Listening...' : 'Recording...',
                                  style: TextStyle(
                                    color: Colors.white.withValues(alpha: 0.9),
                                    fontSize: 14,
                                    fontFamily: 'Manrope',
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],

                        const SizedBox(height: 24),

                        // Action buttons
                        if (!provider.startedRecording) ...[
                          if (provider.isInitialising)
                            const SizedBox(
                              height: 56,
                              child: Center(
                                child: CircularProgressIndicator(
                                  color: Colors.white,
                                ),
                              ),
                            )
                          else
                            SizedBox(
                              width: double.infinity,
                              height: 56,
                              child: ElevatedButton(
                                onPressed: () async {
                                  // Check if user has set primary language, if not, show dialog
                                  if (!context.read<HomeProvider>().hasSetPrimaryLanguage) {
                                    await LanguageSelectionDialog.show(context);
                                  }

                                  await stopAllRecording();

                                  // Initialize speech profile with phone mic as input source
                                  bool success = await provider.initialise(
                                    usePhoneMic: true,
                                    processConversationCallback: () {
                                      Provider.of<CaptureProvider>(context, listen: false)
                                          .forceProcessingCurrentConversation();
                                    },
                                  );

                                  if (!success) {
                                    // Initialization failed, error dialog will be shown
                                    return;
                                  }

                                  provider.forceCompletionTimer =
                                      Timer(Duration(seconds: provider.maxDuration), () async {
                                    provider.finalize();
                                  });

                                  if (!mounted) return;
                                  _questionAnimationController.forward();
                                },
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.white,
                                  foregroundColor: Colors.black,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(28),
                                  ),
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
                          const SizedBox(height: 12),
                          TextButton(
                            onPressed: () {
                              widget.onSkip();
                            },
                            child: Text(
                              context.l10n.skipForNow,
                              style: const TextStyle(
                                color: Colors.white70,
                                decoration: TextDecoration.underline,
                                fontSize: 14,
                                fontFamily: 'Manrope',
                              ),
                            ),
                          ),
                        ] else if (provider.profileCompleted) ...[
                          SizedBox(
                            width: double.infinity,
                            height: 56,
                            child: ElevatedButton(
                              onPressed: () {
                                // Conversation processing already triggered in finalize()
                                widget.goNext();
                              },
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.white,
                                foregroundColor: Colors.black,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(28),
                                ),
                                elevation: 0,
                              ),
                              child: Text(
                                context.l10n.continueButton,
                                style: const TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.w600,
                                  fontFamily: 'Manrope',
                                ),
                              ),
                            ),
                          ),
                        ] else if (!provider.uploadingProfile) ...[
                          // Show skip button during recording
                          TextButton(
                            onPressed: () => provider.skipCurrentQuestion(),
                            child: Text(
                              context.l10n.skipThisQuestion,
                              style: const TextStyle(
                                color: Colors.white70,
                                fontSize: 14,
                                decoration: TextDecoration.underline,
                                fontFamily: 'Manrope',
                              ),
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

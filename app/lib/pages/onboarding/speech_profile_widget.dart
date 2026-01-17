import 'dart:async';

import 'package:flutter/material.dart';

import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/pages/speech_profile/percentage_bar_progress.dart';
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
  }

  @override
  void dispose() {
    final speechProvider = context.read<SpeechProfileProvider>();

    speechProvider.forceCompletionTimer?.cancel();
    speechProvider.forceCompletionTimer = null;
    speechProvider.close();

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
            child: SafeArea(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.end,
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(
                    height: 10,
                  ),
                  Padding(
                    padding: EdgeInsets.fromLTRB(40, !provider.startedRecording ? 20 : 0, 40, 20),
                    child: !provider.startedRecording
                        ? Column(
                            children: [
                              Text(
                                context.l10n.speechProfileIntro,
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 20,
                                  height: 1.4,
                                  fontWeight: FontWeight.w400,
                                ),
                              ),
                              const SizedBox(height: 14),
                              //Text("Note: This only works in English", style: TextStyle(color: Colors.white)),
                            ],
                          )
                        : LayoutBuilder(
                            builder: (context, constraints) {
                              return ShaderMask(
                                shaderCallback: (bounds) {
                                  if (provider.text.split(' ').length < 10) {
                                    return const LinearGradient(colors: [Colors.white, Colors.white])
                                        .createShader(bounds);
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
                                  height: 100,
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
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
                  ),
                  !provider.startedRecording
                      ? (provider.isInitialising
                          ? const CircularProgressIndicator(
                              color: Colors.white,
                            )
                          : Column(
                              mainAxisAlignment: MainAxisAlignment.end,
                              children: [
                                const SizedBox(height: 20),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
                                  decoration: BoxDecoration(
                                    border: const GradientBoxBorder(
                                      gradient: LinearGradient(colors: [
                                        Color.fromARGB(127, 208, 208, 208),
                                        Color.fromARGB(127, 188, 99, 121),
                                        Color.fromARGB(127, 86, 101, 182),
                                        Color.fromARGB(127, 126, 190, 236)
                                      ]),
                                      width: 2,
                                    ),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: TextButton(
                                    onPressed: () async {
                                      // Check if user has set primary language, if not, show dialog
                                      if (!context.read<HomeProvider>().hasSetPrimaryLanguage) {
                                        await LanguageSelectionDialog.show(context);
                                      }

                                      await stopAllRecording();

                                      // Initialize speech profile with phone mic as input source
                                      // Don't pass restartDeviceRecording - we don't want to restart device recording
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
                                    child: Text(
                                      context.l10n.getStarted,
                                      style: const TextStyle(color: Colors.white, fontSize: 16),
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 10),
                              ],
                            ))
                      : provider.profileCompleted
                          ? Container(
                              margin: const EdgeInsets.only(top: 40),
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                              decoration: BoxDecoration(
                                border: const GradientBoxBorder(
                                  gradient: LinearGradient(colors: [
                                    Color.fromARGB(127, 208, 208, 208),
                                    Color.fromARGB(127, 188, 99, 121),
                                    Color.fromARGB(127, 86, 101, 182),
                                    Color.fromARGB(127, 126, 190, 236)
                                  ]),
                                  width: 2,
                                ),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: TextButton(
                                onPressed: () {
                                  // Conversation processing already triggered in finalize()
                                  widget.goNext();
                                },
                                child: Text(
                                  context.l10n.allDone,
                                  style: const TextStyle(color: Colors.white, fontSize: 16),
                                ),
                              ),
                            )
                          : provider.uploadingProfile
                              ? Padding(
                                  padding: const EdgeInsets.only(top: 40.0),
                                  child: Row(
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
                                      const SizedBox(width: 24),
                                      Text(provider.loadingText,
                                          style: const TextStyle(color: Colors.white, fontSize: 18)),
                                    ],
                                  ),
                                )
                              : Column(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    const SizedBox(height: 8),
                                    FadeTransition(
                                      opacity: _questionFadeAnimation,
                                      child: Text(
                                        provider.currentQuestion,
                                        style: const TextStyle(color: Colors.white, fontSize: 22, height: 1.3),
                                        textAlign: TextAlign.center,
                                      ),
                                    ),
                                    const SizedBox(height: 8),
                                    SizedBox(
                                        width: MediaQuery.sizeOf(context).width * 0.9,
                                        child: ProgressBarWithPercentage(progressValue: provider.questionProgress)),
                                    const SizedBox(height: 8),
                                    Text(
                                      context.l10n.keepGoing,
                                      style: TextStyle(color: Colors.grey.shade300, fontSize: 14, height: 1.3),
                                      textAlign: TextAlign.center,
                                    ),
                                    const SizedBox(height: 8),
                                    TextButton(
                                      onPressed: () => provider.skipCurrentQuestion(),
                                      child: Text(
                                        context.l10n.skipThisQuestion,
                                        style: const TextStyle(
                                          color: Colors.white70,
                                          fontSize: 14,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                  (!provider.startedRecording)
                      ? TextButton(
                          onPressed: () {
                            widget.onSkip();
                          },
                          child: Text(
                            context.l10n.skipForNow,
                            style: const TextStyle(
                              color: Colors.white,
                              decoration: TextDecoration.underline,
                              fontSize: 14,
                              fontWeight: FontWeight.normal,
                            ),
                          ),
                        )
                      : const SizedBox(),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

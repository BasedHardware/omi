import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/speech_profile/percentage_bar_progress.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/speech_profile_provider.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

class SpeechProfileWidget extends StatefulWidget {
  final VoidCallback goNext;
  final VoidCallback onSkip;

  const SpeechProfileWidget({super.key, required this.goNext, required this.onSkip});

  @override
  State<SpeechProfileWidget> createState() => _SpeechProfileWidgetState();
}

class _SpeechProfileWidgetState extends State<SpeechProfileWidget> with TickerProviderStateMixin {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) async {});
    SharedPreferencesUtil().onboardingCompleted = true;
    super.initState();
  }

  @override
  void dispose() {
    // if (mounted) {
    //   context.read<SpeechProfileProvider>().close();
    // }
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
      debugPrint("restartDeviceRecording $mounted");

      // Restart device recording, clear transcripts
      if (mounted) {
        Provider.of<CaptureProvider>(context, listen: false).clearTranscripts();
        Provider.of<CaptureProvider>(context, listen: false).streamDeviceRecording(
          device: Provider.of<SpeechProfileProvider>(context, listen: false).deviceProvider?.connectedDevice,
        );
      }
    }

    Future stopDeviceRecording() async {
      debugPrint("stopDeviceRecording $mounted");

      // Restart device recording, clear transcripts
      if (mounted) {
        await Provider.of<CaptureProvider>(context, listen: false).stopStreamDeviceRecording();
      }
    }

    return PopScope(
      canPop: true,
      onPopInvoked: (didPop) async {
        context.read<SpeechProfileProvider>().close();
        restartDeviceRecording();
      },
      child: Consumer2<SpeechProfileProvider, CaptureProvider>(
        builder: (context, provider, _, child) {
          return MessageListener<SpeechProfileProvider>(
            showInfo: (info) {
              if (info == 'SCROLL_DOWN') {
                scrollDown();
              }
            },
            showError: (error) {
              if (error == 'MULTIPLE_SPEAKERS') {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () {
                      provider.resetSegments();
                      Navigator.pop(context);
                    },
                    () {},
                    'Invalid recording detected',
                    'It seems like there are multiple speakers in the recording. Please make sure you are in a quiet location and try again.',
                    okButtonText: 'Try Again',
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
                    'Invalid recording detected',
                    'There is not enough speech detected. Please speak more and try again.',
                    okButtonText: 'Ok',
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
                    'Invalid recording detected',
                    'Please make sure you speak for at least 5 seconds and not more than 90.',
                    okButtonText: 'Ok',
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
                      //  Navigator.pop(context);
                    },
                    () {},
                    'Are you there?',
                    'We could not detect any speech. Please make sure to speak for at least 10 seconds and not more than 3 minutes.',
                    okButtonText: 'Ok',
                    singleButton: true,
                  ),
                  barrierDismissible: false,
                );
              }
            },
            child: Container(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  const SizedBox(
                    height: 10,
                  ),
                  Padding(
                    padding: EdgeInsets.fromLTRB(40, !provider.startedRecording ? 20 : 0, 40, 20),
                    child: !provider.startedRecording
                        ? const Column(
                            children: [
                              Text(
                                'Omi needs to learn your voice to recognize you',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 20,
                                  height: 1.4,
                                  fontWeight: FontWeight.w400,
                                ),
                              ),
                              SizedBox(height: 14),
                              Text("Note: This only works in English", style: TextStyle(color: Colors.white)),
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
                                      await stopDeviceRecording();
                                      await provider.initialise(finalizedCallback: restartDeviceRecording);
                                      provider.forceCompletionTimer =
                                          Timer(Duration(seconds: provider.maxDuration), () async {
                                        provider.finalize();
                                      });
                                      provider.updateStartedRecording(true);
                                    },
                                    child: const Text(
                                      'Get Started',
                                      style: TextStyle(color: Colors.white, fontSize: 16),
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
                                  widget.goNext();
                                },
                                child: const Text(
                                  "All done!",
                                  style: TextStyle(color: Colors.white, fontSize: 16),
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
                                    const SizedBox(height: 20),
                                    provider.percentageCompleted > 0
                                        ? const SizedBox()
                                        : const Text(
                                            "Introduce\nyourself",
                                            style: TextStyle(color: Colors.white, fontSize: 24, height: 1.4),
                                            textAlign: TextAlign.center,
                                          ),
                                    const SizedBox(height: 10),
                                    SizedBox(
                                        width: MediaQuery.sizeOf(context).width * 0.9,
                                        child: ProgressBarWithPercentage(progressValue: provider.percentageCompleted)),
                                    const SizedBox(height: 12),
                                    Text(
                                      provider.message,
                                      style: TextStyle(color: Colors.grey.shade300, fontSize: 14, height: 1.4),
                                      textAlign: TextAlign.center,
                                    ),
                                  ],
                                ),
                  (!provider.startedRecording)
                      ? TextButton(
                          onPressed: () {
                            widget.onSkip();
                          },
                          child: const Text(
                            'Skip for now',
                            style: TextStyle(
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

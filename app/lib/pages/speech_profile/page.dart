import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/pages/speech_profile/user_speech_samples.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/device_widget.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

import 'percentage_bar_progress.dart';

class SpeechProfilePage extends StatefulWidget {
  final bool onbording;

  const SpeechProfilePage({super.key, this.onbording = false});

  @override
  State<SpeechProfilePage> createState() => _SpeechProfilePageState();
}

class _SpeechProfilePageState extends State<SpeechProfilePage> with TickerProviderStateMixin {
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

      final speechProvider = context.read<SpeechProfileProvider>();
      final homeProvider = context.read<HomeProvider>();

      speechProvider.close();
      await speechProvider.updateDevice();

      if (!mounted) return;

      if (!homeProvider.hasSetPrimaryLanguage) {
        await LanguageSelectionDialog.show(context);
      }
    });
  }

  // TODO: use connection directly
  Future<BleAudioCodec> _getAudioCodec(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return BleAudioCodec.pcm8;
    }
    return connection.getAudioCodec();
  }

  @override
  void dispose() {
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
      debugPrint("restartDeviceRecording $mounted");
      if (mounted) {
        Provider.of<CaptureProvider>(context, listen: false).clearTranscripts();
        Provider.of<CaptureProvider>(context, listen: false).streamDeviceRecording(
          device: Provider.of<SpeechProfileProvider>(context, listen: false).deviceProvider?.connectedDevice,
        );
      }
    }

    Future stopDeviceRecording() async {
      debugPrint("stopDeviceRecording $mounted");
      if (mounted) {
        await Provider.of<CaptureProvider>(context, listen: false).stopStreamDeviceRecording();
      }
    }

    return PopScope(
      canPop: true,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) {
          if (context.read<SpeechProfileProvider>().isInitialised) {
            final speechProvider = context.read<SpeechProfileProvider>();
            final captureProvider = context.read<CaptureProvider>();
            final device = speechProvider.deviceProvider?.connectedDevice;

            WidgetsBinding.instance.addPostFrameCallback((_) async {
              await speechProvider.close();

              captureProvider.clearTranscripts();
              captureProvider.streamDeviceRecording(device: device);
            });
          }
        }
      },
      child: Consumer2<SpeechProfileProvider, CaptureProvider>(builder: (context, provider, _, child) {
        return MessageListener<SpeechProfileProvider>(
          showInfo: (info) {
            if (info == 'SCROLL_DOWN') {
              scrollDown();
            } else if (info == 'NEXT_QUESTION') {
              _questionAnimationController.reset();
              _questionAnimationController.forward();
            }
          },
          showError: (error) {
            if (error == 'MULTIPLE_SPEAKERS') {
              showDialog(
                context: context,
                builder: (c) => getDialog(
                  context,
                  () {
                    provider.close();
                    Navigator.pop(context);
                  },
                  () {},
                  'Multiple speakers detected',
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
                    Navigator.pop(context);
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
                    Navigator.pop(context);
                  },
                  () {},
                  'Invalid recording detected',
                  'Please make sure you speak for at least 5 seconds and not more than 90.',
                  okButtonText: 'Ok',
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
                  'Connection Lost',
                  'The connection was interrupted. Please check your internet connection and try again.',
                  okButtonText: 'Try Again',
                  singleButton: true,
                ),
                barrierDismissible: false,
              );
            }
          },
          child: Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar: AppBar(
              backgroundColor: Theme.of(context).colorScheme.primary,
              automaticallyImplyLeading: true,
              title: const Text(
                '',
                style: TextStyle(color: Colors.white, fontSize: 20),
              ),
              actions: [
                !widget.onbording
                    ? IconButton(
                        onPressed: () {
                          showDialog(
                            context: context,
                            builder: (c) => getDialog(
                              context,
                              () => Navigator.pop(context),
                              () => Navigator.pop(context),
                              'How to take a good sample?',
                              '1. Make sure you are in a quiet place.\n2. Speak clearly and naturally.\n3. Make sure your device is in it\'s natural position, on your neck.\n\nOnce it\'s created, you can always improve it or do it again.',
                              singleButton: true,
                            ),
                          );
                        },
                        icon: const Icon(
                          Icons.question_mark,
                          size: 20,
                        ))
                    : TextButton(
                        onPressed: () {
                          routeToPage(context, const HomePageWrapper(), replace: true);
                        },
                        child: const Text(
                          'Skip',
                          style: TextStyle(color: Colors.white, decoration: TextDecoration.underline),
                        ),
                      ),
              ],
              centerTitle: true,
              elevation: 0,
              leading: widget.onbording
                  ? const SizedBox()
                  : IconButton(
                      icon: const Icon(Icons.arrow_back_ios_new),
                      onPressed: () => Navigator.pop(context),
                    ),
            ),
            body: Stack(
              children: [
                Align(
                  alignment: Alignment.topCenter,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(24, 8, 24, 0),
                    child: Column(
                      children: [
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
                Align(
                  alignment: Alignment.center,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(40, 40, 40, 48),
                    child: !provider.startedRecording
                        ? const Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              SizedBox(height: 10),
                              Text(
                                'Omi needs to learn your goals and your voice. You\'ll be able to modify it later.',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 20,
                                  height: 1.4,
                                  fontWeight: FontWeight.w400,
                                ),
                              ),
                              SizedBox(height: 20),
                            ],
                          )
                        : provider.text.isEmpty
                            ? const SizedBox.shrink()
                            : Padding(
                                padding: const EdgeInsets.only(top: 80.0),
                                child: LayoutBuilder(
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
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    );
                                  },
                                ),
                              ),
                  ),
                ),
                Align(
                  alignment: Alignment.bottomCenter,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(0, 0, 0, 48),
                    child: !provider.startedRecording
                        ? Column(
                            mainAxisAlignment: MainAxisAlignment.end,
                            children: [
                              if (provider.device == null)
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 16),
                                  child: Text(
                                    'No device connected. Will use phone microphone.',
                                    style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                                    textAlign: TextAlign.center,
                                  ),
                                ),
                              provider.isInitialising
                                  ? const CircularProgressIndicator(
                                      color: Colors.white,
                                    )
                                  : MaterialButton(
                                      onPressed: () async {
                                        // Check if user has set primary language, if not, show dialog
                                        if (!context.read<HomeProvider>().hasSetPrimaryLanguage) {
                                          await LanguageSelectionDialog.show(context);
                                        }

                                        bool usePhoneMic = false;

                                        // Check if device is connected and supports opus
                                        if (provider.device != null) {
                                          try {
                                            BleAudioCodec codec = await _getAudioCodec(provider.device!.id);
                                            if (!codec.isOpusSupported()) {
                                              // Device doesn't support opus, use phone mic
                                              usePhoneMic = true;
                                            }
                                          } catch (e) {
                                            // Device disconnected, use phone mic
                                            usePhoneMic = true;
                                          }
                                        } else {
                                          // No device connected, use phone mic
                                          usePhoneMic = true;
                                        }

                                        await stopDeviceRecording();
                                        bool success = await provider.initialise(
                                          finalizedCallback: restartDeviceRecording,
                                          processConversationCallback: () {
                                            Provider.of<CaptureProvider>(context, listen: false)
                                                .forceProcessingCurrentConversation();
                                          },
                                          usePhoneMic: usePhoneMic,
                                        );
                                        if (!success) {
                                          // Initialization failed, error dialog will be shown
                                          await restartDeviceRecording();
                                          return;
                                        }
                                        provider.forceCompletionTimer =
                                            Timer(Duration(seconds: provider.maxDuration), () {
                                          provider.finalize();
                                        });
                                        provider.updateStartedRecording(true);
                                        _questionAnimationController.forward();
                                      },
                                      color: Colors.white,
                                      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 14),
                                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                                      child: Text(
                                        SharedPreferencesUtil().hasSpeakerProfile ? 'Do it again' : 'Get Started',
                                        style: const TextStyle(color: Colors.black),
                                      ),
                                    ),
                              const SizedBox(height: 24),
                              SharedPreferencesUtil().hasSpeakerProfile
                                  ? TextButton(
                                      onPressed: () {
                                        routeToPage(context, const UserSpeechSamples());
                                      },
                                      child: const Text(
                                        'Listen to my speech profile ➡️',
                                        style: TextStyle(color: Colors.white, fontSize: 16),
                                      ))
                                  : const SizedBox(),
                              TextButton(
                                  onPressed: () {
                                    routeToPage(context, const UserPeoplePage());
                                  },
                                  child: const Text(
                                    'Recognizing others 👀',
                                    style: TextStyle(color: Colors.white, fontSize: 16),
                                  )),
                            ],
                          )
                        : provider.profileCompleted
                            ? Container(
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
                                    Navigator.pop(context);
                                  },
                                  child: const Text(
                                    "All done!",
                                    style: TextStyle(color: Colors.white, fontSize: 16),
                                  ),
                                ),
                              )
                            : provider.uploadingProfile
                                ? const CircularProgressIndicator(
                                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
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
                                        child: ProgressBarWithPercentage(progressValue: provider.questionProgress),
                                      ),
                                      const SizedBox(height: 8),
                                      Text(
                                        'Keep going, you are doing great',
                                        style: TextStyle(color: Colors.grey.shade300, fontSize: 14, height: 1.3),
                                        textAlign: TextAlign.center,
                                      ),
                                      const SizedBox(height: 8),
                                      TextButton(
                                        onPressed: () => provider.skipCurrentQuestion(),
                                        child: const Text(
                                          'Skip this question',
                                          style: TextStyle(
                                            color: Colors.white70,
                                            fontSize: 14,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                  ),
                ),
              ],
            ),
          ),
        );
      }),
    );
  }
}

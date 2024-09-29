import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/speech_profile/user_speech_samples.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/speech_profile_provider.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:provider/provider.dart';

class SpeechProfilePage extends StatefulWidget {
  final bool onbording;

  const SpeechProfilePage({super.key, this.onbording = false});

  @override
  State<SpeechProfilePage> createState() => _SpeechProfilePageState();
}

class _SpeechProfilePageState extends State<SpeechProfilePage> with TickerProviderStateMixin {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) async {
      await context.read<SpeechProfileProvider>().updateDevice();
    });

    super.initState();
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
    // if (mounted) {
    //   context.read<SpeechProfileProvider>().dispose();
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
      onPopInvoked: (didPop) {
        if (context.read<SpeechProfileProvider>().isInitialised) {
          WidgetsBinding.instance.addPostFrameCallback((timeStamp) async {
            await context.read<SpeechProfileProvider>().close();

            // Restart device recording
            restartDeviceRecording();
          });
        }
      },
      child: Consumer2<SpeechProfileProvider, CaptureProvider>(builder: (context, provider, _, child) {
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
                  // TODO: improve this
                  'Invalid recording detected',
                  'Please make sure you speak for at least 5 seconds and not more than 90.',
                  okButtonText: 'Ok',
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
                    padding: EdgeInsets.fromLTRB(16, 8, 16, 0),
                    child: Column(
                      children: [
                        const DeviceAnimationWidget(sizeMultiplier: 0.2, animatedBackground: false),
                        !provider.startedRecording
                            ? const SizedBox(height: 0)
                            : const Text(
                                'Tell your Friend\nabout yourself',
                                style: TextStyle(
                                    color: Colors.white, fontSize: 18, fontWeight: FontWeight.w500, height: 1.4),
                                textAlign: TextAlign.center,
                              ),
                      ],
                    ),
                  ),
                ),
                Align(
                  alignment: Alignment.center,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(40, 0, 40, 48),
                    child: !provider.startedRecording
                        ? const Text(
                            'Now, Omi needs to learn your voice to be able to recognise you.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              height: 1.4,
                              fontWeight: FontWeight.w400,
                            ),
                          )
                        : provider.text.isEmpty
                            ? const DeviceAnimationWidget(
                                sizeMultiplier: 0.7,
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
                                      height: 120,
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
                Align(
                  alignment: Alignment.bottomCenter,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(24, 0, 24, 48),
                    child: !provider.startedRecording
                        ? Column(
                            mainAxisAlignment: MainAxisAlignment.end,
                            children: [
                              provider.isInitialising
                                  ? CircularProgressIndicator(
                                      color: Colors.white,
                                    )
                                  : MaterialButton(
                                      onPressed: () async {
                                        BleAudioCodec codec;
                                        try {
                                          codec = await _getAudioCodec(provider.device!.id);
                                        } catch (e) {
                                          showDialog(
                                            context: context,
                                            barrierDismissible: false,
                                            builder: (c) => getDialog(
                                              context,
                                              () {
                                                Navigator.of(context).pop();
                                                Navigator.of(context).pop();
                                              },
                                              () => {},
                                              'Device Disconnected',
                                              'Please make sure your device is turned on and nearby, and try again.',
                                              singleButton: true,
                                            ),
                                          );
                                          return;
                                        }

                                        if (codec != BleAudioCodec.opus) {
                                          showDialog(
                                            context: context,
                                            builder: (c) => getDialog(
                                              context,
                                              () => Navigator.pop(context),
                                              () async {
                                                await Intercom.instance.displayArticle(
                                                    '9918118-updating-the-firmware-on-your-friend-device');
                                              },
                                              'Device Update Required',
                                              'Your current device has an old firmware version (1.0.2). Please check our guide on how to update it.',
                                              okButtonText: 'View Guide',
                                            ),
                                            barrierDismissible: false,
                                          );
                                          return;
                                        }

                                        await stopDeviceRecording();
                                        await provider.initialise(false, finalizedCallback: restartDeviceRecording);
                                        // 1.5 minutes seems reasonable
                                        provider.forceCompletionTimer =
                                            Timer(Duration(seconds: provider.maxDuration), () {
                                          provider.finalize();
                                        });
                                        provider.updateStartedRecording(true);
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
                              // TextButton(
                              //     onPressed: () {
                              //       routeToPage(context, const UserPeoplePage());
                              //     },
                              //     child: const Text(
                              //       'Recognizing others 👀',
                              //       style: TextStyle(color: Colors.white, fontSize: 16),
                              //     )),
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
                                      Text(
                                        provider.message,
                                        style: TextStyle(color: Colors.grey.shade300, fontSize: 14, height: 1.4),
                                        textAlign: TextAlign.center,
                                      ),
                                      const SizedBox(height: 24),
                                      Padding(
                                        padding: const EdgeInsets.symmetric(horizontal: 32),
                                        child: Stack(
                                          children: [
                                            // LinearProgressIndicator(
                                            //   backgroundColor: Colors.grey[300],
                                            //   valueColor: AlwaysStoppedAnimation<Color>(Colors.grey.withOpacity(0.3)),
                                            // ),
                                            LinearProgressIndicator(
                                              value: provider.percentageCompleted,
                                              backgroundColor:
                                                  Colors.grey.shade300, // Make sure background is transparent
                                              valueColor: const AlwaysStoppedAnimation<Color>(Colors.deepPurple),
                                            ),
                                          ],
                                        ),
                                      ),
                                      const SizedBox(height: 12),
                                      Text('${(provider.percentageCompleted * 100).toInt()}%',
                                          style: const TextStyle(color: Colors.white)),
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

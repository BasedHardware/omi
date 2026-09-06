import 'dart:async';

import 'package:flutter/material.dart';

import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:just_audio/just_audio.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/pages/speech_profile/speech_topics_card.dart';
import 'package:omi/pages/speech_profile/speech_progress_bar.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/device_widget.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/fade_in_words_text.dart';

class SpeechProfilePage extends StatefulWidget {
  final bool onbording;

  const SpeechProfilePage({super.key, this.onbording = false});

  @override
  State<SpeechProfilePage> createState() => _SpeechProfilePageState();
}

class _SpeechProfilePageState extends State<SpeechProfilePage> {
  // Plays the saved profile audio in place; the Play button becomes Stop.
  final AudioPlayer _profilePlayer = AudioPlayer();
  StreamSubscription<PlayerState>? _profilePlayerSub;
  bool _profilePlaying = false;
  bool _profileLoading = false;
  // Guards the pre-flight availability check itself, which runs before
  // provider.isInitialising ever becomes true — without this, a rapid double
  // tap on Redo/Get Started during that network round-trip could start two
  // concurrent sessions.
  bool _isCheckingAvailability = false;

  @override
  void initState() {
    super.initState();
    _profilePlayerSub = _profilePlayer.playerStateStream.listen((state) {
      if (state.processingState == ProcessingState.completed && mounted) {
        setState(() => _profilePlaying = false);
      }
    });
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

  Future<BleAudioCodec> _getAudioCodec() async {
    var connection = ServiceManager.instance().device.connection;
    if (connection == null) {
      return BleAudioCodec.pcm8;
    }
    return connection.getAudioCodec();
  }

  Widget _capsuleButton({String? text, IconData? icon, required VoidCallback onPressed}) {
    Widget child;
    if (icon != null && text != null) {
      child = Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: Colors.white),
          const SizedBox(width: 8),
          Text(text, style: const TextStyle(color: Colors.white)),
        ],
      );
    } else if (icon != null) {
      child = Icon(icon, color: Colors.white);
    } else {
      child = Text(text!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white));
    }

    final button = MaterialButton(
      onPressed: onPressed,
      color: Colors.black,
      padding: icon != null
          ? const EdgeInsets.symmetric(vertical: 16)
          : const EdgeInsets.symmetric(horizontal: 32, vertical: 14),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(28),
        side: const BorderSide(color: Colors.white),
      ),
      child: child,
    );
    return icon != null ? button : SizedBox(width: double.infinity, child: button);
  }

  Future<void> _toggleProfilePlayback() async {
    if (_profilePlaying) {
      await _stopProfilePlayback();
      return;
    }
    if (_profileLoading) return;
    setState(() => _profileLoading = true);
    try {
      final url = await getUserSpeechProfile();
      if (url == null || url.isEmpty) throw StateError('no speech profile url');
      await _profilePlayer.setUrl(url);
      if (!mounted) return;
      setState(() => _profilePlaying = true);
      unawaited(_profilePlayer.play());
    } catch (e) {
      Logger.debug('Speech profile playback failed: $e');
      if (mounted) AppSnackbar.showSnackbarError(context.l10n.somethingWentWrong);
    } finally {
      if (mounted) setState(() => _profileLoading = false);
    }
  }

  Future<void> _stopProfilePlayback() async {
    await _profilePlayer.stop();
    if (mounted) setState(() => _profilePlaying = false);
  }

  @override
  void dispose() {
    _scrollController.dispose();
    _profilePlayerSub?.cancel();
    _profilePlayer.dispose();
    super.dispose();
  }

  final ScrollController _scrollController = ScrollController();

  void scrollDown() async {
    await Future.delayed(const Duration(milliseconds: 250));

    if (!mounted) return;
    if (_scrollController.positions.isEmpty) return;

    _scrollController.animateTo(
      _scrollController.position.maxScrollExtent,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
    );
  }

  @override
  Widget build(BuildContext context) {
    Future restartDeviceRecording() async {
      Logger.debug("restartDeviceRecording $mounted");
      if (mounted) {
        Provider.of<CaptureProvider>(context, listen: false).clearTranscripts();
        Provider.of<CaptureProvider>(context, listen: false).streamDeviceRecording(
          device: Provider.of<SpeechProfileProvider>(context, listen: false).deviceProvider?.connectedDevice,
        );
      }
    }

    Future stopDeviceRecording() async {
      Logger.debug("stopDeviceRecording $mounted");
      if (mounted) {
        await Provider.of<CaptureProvider>(context, listen: false).stopStreamDeviceRecording();
      }
    }

    Future<void> startRecording(SpeechProfileProvider provider) async {
      if (_isCheckingAvailability || provider.isInitialising) return;
      setState(() => _isCheckingAvailability = true);

      // Pre-flight: don't enter the recording UI at all if the streaming
      // primary is known down — otherwise the socket connects and audio uploads, but no
      // question/progress ever arrives (see STT_UNAVAILABLE handling below,
      // which only fires after already sitting in a dead recording screen).
      final available = await isSttAvailable();
      // Backend STT down: transcribe on-device instead when this platform can,
      // rather than dead-ending in a dialog. The voice print comes from the
      // uploaded audio either way.
      final useLocalStt = !available && await provider.enableLocalStt();
      if (mounted) setState(() => _isCheckingAvailability = false);
      if (!available && !useLocalStt) {
        if (!context.mounted) return;
        await showDialog(
          context: context,
          builder: (c) => getDialog(
            context,
            () => Navigator.pop(context),
            () {},
            context.l10n.connectionError,
            context.l10n.speechToTextUnavailableDesc,
            okButtonText: context.l10n.ok,
            singleButton: true,
          ),
          barrierDismissible: false,
        );
        return;
      }

      if (!context.mounted) return;
      // Check if user has set primary language, if not, show dialog
      if (!context.read<HomeProvider>().hasSetPrimaryLanguage) {
        await LanguageSelectionDialog.show(context);
      }

      bool usePhoneMic = false;

      // Check if device is connected and supports opus
      final currentDevice = provider.device;
      if (currentDevice != null) {
        try {
          BleAudioCodec codec = await _getAudioCodec();
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
          Provider.of<CaptureProvider>(context, listen: false).forceProcessingCurrentConversation();
        },
        usePhoneMic: usePhoneMic,
      );
      if (!success) {
        // Initialization failed, error dialog will be shown
        await restartDeviceRecording();
        return;
      }
      provider.forceCompletionTimer = Timer(
        Duration(seconds: provider.maxDuration),
        () {
          provider.finalize();
        },
      );
      provider.updateStartedRecording(true);
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
      child: Consumer2<SpeechProfileProvider, CaptureProvider>(
        builder: (context, provider, _, child) {
          return MessageListener<SpeechProfileProvider>(
            showInfo: (info) {
              if (info == 'SCROLL_DOWN') {
                scrollDown();
              } else if (info == 'SKIP_UNAVAILABLE') {
                AppSnackbar.showSnackbarError(context.l10n.reconnecting);
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
                    context.l10n.multipleSpeakersDetected,
                    context.l10n.multipleSpeakersDescription,
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
                      Navigator.pop(context);
                    },
                    () {},
                    context.l10n.invalidRecordingDetected,
                    context.l10n.notEnoughSpeechDescription,
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
                      Navigator.pop(context);
                    },
                    () {},
                    context.l10n.invalidRecordingDetected,
                    context.l10n.speechDurationDescription,
                    okButtonText: context.l10n.ok,
                    singleButton: true,
                  ),
                  barrierDismissible: false,
                );
              } else if (error == 'SOCKET_DISCONNECTED' || error == 'SOCKET_ERROR' || error == 'STT_UNAVAILABLE') {
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
                    context.l10n.connectionLostDescription,
                    okButtonText: context.l10n.tryAgain,
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
                title: const Text('', style: TextStyle(color: Colors.white, fontSize: 20)),
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
                                context.l10n.howToTakeGoodSample,
                                context.l10n.goodSampleInstructions,
                                singleButton: true,
                              ),
                            );
                          },
                          icon: const Icon(Icons.question_mark, size: 20),
                        )
                      : TextButton(
                          onPressed: () {
                            routeToPage(context, const HomePageWrapper(), replace: true);
                          },
                          child: Text(
                            context.l10n.skip,
                            style: const TextStyle(color: Colors.white, decoration: TextDecoration.underline),
                          ),
                        ),
                ],
                centerTitle: true,
                elevation: 0,
                leading: widget.onbording
                    ? const SizedBox()
                    : IconButton(icon: const Icon(Icons.arrow_back_ios_new), onPressed: () => Navigator.pop(context)),
              ),
              body: Stack(
                children: [
                  Align(
                    alignment: Alignment.topCenter,
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(24, 8, 24, 0),
                      child: Column(
                        children: [
                          Stack(
                            alignment: Alignment.center,
                            children: [
                              if (provider.startedRecording && !provider.profileCompleted && !provider.uploadingProfile)
                                // Mic feedback: a plain white glow behind the device
                                // graphic that grows brighter/larger with mic level,
                                // instead of a separate bar meter.
                                AnimatedContainer(
                                  duration: const Duration(milliseconds: 150),
                                  width: 180 + provider.micLevel * 40,
                                  height: 180 + provider.micLevel * 40,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    boxShadow: [
                                      BoxShadow(
                                        color: Colors.white.withValues(alpha: 0.08 + provider.micLevel * 0.18),
                                        blurRadius: 32 + provider.micLevel * 24,
                                        spreadRadius: 2 + provider.micLevel * 10,
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
                        ],
                      ),
                    ),
                  ),
                  Align(
                    alignment: Alignment.center,
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(40, 40, 40, 48),
                      child: !provider.startedRecording
                          ? Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const SizedBox(height: 10),
                                if (SharedPreferencesUtil().hasSpeakerProfile)
                                  // "<Name>'s Speech Profile" always stays on one line:
                                  // it shrinks to fit rather than wrapping.
                                  FittedBox(
                                    fit: BoxFit.scaleDown,
                                    child: Text(
                                      context.l10n.speechProfileOwnerTitle(SharedPreferencesUtil().givenName),
                                      maxLines: 1,
                                      softWrap: false,
                                      textAlign: TextAlign.center,
                                      style: const TextStyle(
                                        color: Colors.white,
                                        fontSize: 24,
                                        height: 1.4,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  )
                                else
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
                                const SizedBox(height: 20),
                                // No spinner while the page loads or the pre-flight
                                // runs: the buttons stay put and startRecording()
                                // ignores taps until the check is done.
                                if (SharedPreferencesUtil().hasSpeakerProfile)
                                  Padding(
                                    padding: const EdgeInsets.symmetric(horizontal: 24),
                                    child: Row(
                                      children: [
                                        Expanded(
                                          child: _capsuleButton(
                                            icon: _profilePlaying ? Icons.stop_rounded : Icons.play_arrow_rounded,
                                            text: _profilePlaying ? context.l10n.stop : context.l10n.play,
                                            onPressed: _toggleProfilePlayback,
                                          ),
                                        ),
                                        const SizedBox(width: 16),
                                        Expanded(
                                          child: _capsuleButton(
                                            icon: Icons.replay_rounded,
                                            text: context.l10n.redo,
                                            onPressed: () {
                                              _stopProfilePlayback();
                                              startRecording(provider);
                                            },
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                              ],
                            )
                          // While recording, the transcript is laid out above the
                          // topics card in the bottom section so they cannot overlap.
                          : const SizedBox.shrink(),
                    ),
                  ),
                  Align(
                    alignment: Alignment.bottomCenter,
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(0, 0, 0, 48),
                      child: !provider.startedRecording && !SharedPreferencesUtil().hasSpeakerProfile
                          ? Column(
                              mainAxisAlignment: MainAxisAlignment.end,
                              children: [
                                _capsuleButton(
                                  text: context.l10n.getStarted,
                                  onPressed: () => startRecording(provider),
                                ),
                                // Only relevant while actually creating a profile — an
                                // existing profile's play/redo buttons live under the
                                // title instead and don't need a mic-source disclaimer.
                                if (provider.device == null)
                                  Padding(
                                    padding: const EdgeInsets.only(top: 16),
                                    child: Text(
                                      context.l10n.noDeviceConnectedUseMic,
                                      style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                                      textAlign: TextAlign.center,
                                    ),
                                  ),
                              ],
                            )
                          : !provider.startedRecording
                              // Has a profile already and hasn't started re-recording:
                              // its play/redo buttons live under the title instead, and
                              // this section (recording/question/complete UI) doesn't
                              // apply yet.
                              ? const SizedBox.shrink()
                              : provider.profileCompleted
                                  ? Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                                      decoration: BoxDecoration(
                                        border: const GradientBoxBorder(
                                          gradient: LinearGradient(
                                            colors: [
                                              Color.fromARGB(127, 208, 208, 208),
                                              Color.fromARGB(127, 188, 99, 121),
                                              Color.fromARGB(127, 86, 101, 182),
                                              Color.fromARGB(127, 126, 190, 236),
                                            ],
                                          ),
                                          width: 2,
                                        ),
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: TextButton(
                                        onPressed: () {
                                          // Conversation processing already triggered in finalize()
                                          Navigator.pop(context);
                                        },
                                        child: Text(
                                          context.l10n.allDone,
                                          style: const TextStyle(color: Colors.white, fontSize: 16),
                                        ),
                                      ),
                                    )
                                  : provider.uploadingProfile
                                      ? const CircularProgressIndicator(
                                          valueColor: AlwaysStoppedAnimation<Color>(Colors.white))
                                      : Column(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            if (provider.text.isNotEmpty)
                                              Padding(
                                                padding: const EdgeInsets.fromLTRB(32, 0, 32, 48),
                                                // The widget keeps only the last three whole lines, so
                                                // the area is never clipped: it is at least three lines
                                                // tall (so the card below stays put) and grows if the
                                                // rendered lines run taller than that estimate.
                                                child: ConstrainedBox(
                                                  constraints: BoxConstraints(
                                                    minHeight: MediaQuery.textScalerOf(context).scale(18) * 1.4 * 3,
                                                  ),
                                                  child: Align(
                                                    alignment: Alignment.bottomCenter,
                                                    child: FadeInWordsText(
                                                      text: provider.text,
                                                      visibleLines: 3,
                                                      style: const TextStyle(
                                                        color: Colors.white,
                                                        fontSize: 18,
                                                        fontWeight: FontWeight.w400,
                                                        height: 1.4,
                                                      ),
                                                    ),
                                                  ),
                                                ),
                                              ),
                                            Padding(
                                              padding: const EdgeInsets.symmetric(horizontal: 24),
                                              child: Column(
                                                children: [
                                                  const SpeechTopicsCard(),
                                                  const SizedBox(height: 12),
                                                  SpeechProgressBar(progress: provider.sentenceProgress),
                                                ],
                                              ),
                                            ),
                                            if (provider.device == null)
                                              Padding(
                                                padding: const EdgeInsets.only(top: 16),
                                                child: Text(
                                                  context.l10n.noDeviceConnectedUseMic,
                                                  style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                                                  textAlign: TextAlign.center,
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
        },
      ),
    );
  }
}

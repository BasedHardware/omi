import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/http/api/speech_profile.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/logic/websocket_mixin.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/ble/connected.dart';
import 'package:friend_private/utils/ble/scan.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

class SpeakerIdPage extends StatefulWidget {
  final bool onbording;

  const SpeakerIdPage({super.key, this.onbording = false});

  @override
  State<SpeakerIdPage> createState() => _SpeakerIdPageState();
}

class _SpeakerIdPageState extends State<SpeakerIdPage> with TickerProviderStateMixin, WebSocketMixin {
  StreamSubscription<OnConnectionStateChangedEvent>? _connectionStateListener;
  BTDeviceStruct? _device;

  List<TranscriptSegment> segments = [];
  double? streamStartedAtSecond;
  WavBytesUtil audioStorage = WavBytesUtil(codec: BleAudioCodec.opus);
  StreamSubscription? _bleBytesStream;
  bool uploadingProfile = false;
  double percentageCompleted = 0;
  bool profileCompleted = false;
  int targetWordsCount = 45;

  _init() async {
    initiateWebsocket();
    _device = await getConnectedDevice();
    // TODO: improve the UX of this.
    _device ??= await scanAndConnectDevice(timeout: true);
    if (_device != null) initiateFriendAudioStreaming(_device!);
    _initiateConnectionListener();
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) {
      if (_device == null) {
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
      }
    });
    setState(() {});
  }

  _initiateConnectionListener() async {
    if (_device == null || _connectionStateListener != null) return;
    _connectionStateListener = getConnectionStateListener(
        deviceId: _device!.id,
        onDisconnected: () => setState(() => _device = null),
        onConnected: ((device) {
          setState(() => _device = device);
          initiateFriendAudioStreaming(device);
        }));
  }

  _validateSingleSpeaker() {
    int speakersCount = segments.map((e) => e.speaker).toSet().length;
    debugPrint('_validateSingleSpeaker speakers count: $speakersCount');
    if (speakersCount > 1) {
      var speakerToWords = segments.fold<Map<int, int>>(
        {},
        (previousValue, element) {
          previousValue[element.speakerId] = (previousValue[element.speakerId] ?? 0) + element.text.split(' ').length;
          return previousValue;
        },
      );
      debugPrint('speakerToWords: $speakerToWords');
      if (speakerToWords.values.every((element) => element / segments.length > 0.2)) {
        showDialog(
          context: context,
          builder: (c) => getDialog(
            context,
            () {
              Navigator.pop(context);
              segments.clear();
              streamStartedAtSecond = null;
              audioStorage.clearAudioBytes();
              setState(() {});
            },
            () {},
            'Invalid recording detected',
            'It seems like there are multiple speakers in the recording. Please make sure you are in a quiet location and try again.',
            okButtonText: 'Try Again',
            singleButton: true,
          ),
          barrierDismissible: false,
        );
      }
    }
  }

  _handleCompletion() async {
    if (uploadingProfile || profileCompleted) return;
    String text = segments.map((e) => e.text).join(' ').trim();
    int wordsCount = text.split(' ').length;
    setState(() => percentageCompleted = (wordsCount / targetWordsCount).clamp(0, 1));
    if (percentageCompleted == 1) {
      setState(() => uploadingProfile = true);
      closeWebSocket();
      _connectionStateListener?.cancel();
      _bleBytesStream?.cancel();

      List<List<int>> raw = List.from(audioStorage.rawPackets);
      await uploadProfileBytes(raw, segments.last.end.toInt());
      setState(() {
        uploadingProfile = false;
        profileCompleted = true;
      });
    }
  }

  Future<void> initiateWebsocket() async {
    await initWebSocket(
      codec: BleAudioCodec.opus,
      sampleRate: 16000,
      includeSpeechProfile: false,
      onConnectionSuccess: () => setState(() {}),
      onConnectionFailed: (err) => setState(() {}),
      onConnectionClosed: (int? closeCode, String? closeReason) {},
      onConnectionError: (err) => setState(() {}),
      onMessageReceived: (List<TranscriptSegment> newSegments) {
        if (newSegments.isEmpty) return;
        if (segments.isEmpty) {
          audioStorage.removeFramesRange(fromSecond: 0, toSecond: newSegments[0].start.toInt());
        }
        streamStartedAtSecond ??= newSegments[0].start;

        TranscriptSegment.combineSegments(
          segments,
          newSegments,
          toRemoveSeconds: streamStartedAtSecond ?? 0,
        );
        _validateSingleSpeaker();
        _handleCompletion();
        setState(() {});
        scrollDown();
        debugPrint('Memory creation timer restarted');
      },
    );
  }

  Future<void> initiateFriendAudioStreaming(BTDeviceStruct btDevice) async {
    // if (await getAudioCodec(btDevice.id) != BleAudioCodec.opus) return;
    _bleBytesStream = await getBleAudioBytesListener(
      btDevice.id,
      onAudioBytesReceived: (List<int> value) {
        if (value.isEmpty) return;
        audioStorage.storeFramePacket(value);
        value.removeRange(0, 3);
        if (wsConnectionState == WebsocketConnectionStatus.connected) {
          websocketChannel?.sink.add(value);
        }
      },
    );
    print('_bleBytesStream: $_bleBytesStream');
  }

  @override
  void initState() {
    _init();
    super.initState();
  }

  @override
  void dispose() {
    _connectionStateListener?.cancel();
    _bleBytesStream?.cancel();
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
    String text = segments.map((e) => e.text).join(' ').trim();
    int wordsCount = text.split(' ').length;
    String message = 'Keep speaking until we tell you we have enough recording of your voice to continue.';
    if (wordsCount > 5) {
      message = 'Keep going, you are doing great';
    } else if (wordsCount > 25) {
      message = 'Great job, you are almost there';
    } else if (wordsCount > 50) {
      message = 'So close, just a little more';
    }

    return PopScope(
      canPop: true,
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
                ? const SizedBox()
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
            const Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: EdgeInsets.fromLTRB(16, 32, 16, 0),
                child: Text(
                  'Tell your Friend about you.',
                  style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
                ),
              ),
            ),
            Align(
              alignment: Alignment.center,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(40, 0, 40, 24),
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    return ShaderMask(
                      shaderCallback: (bounds) {
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
                              text,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 20, // Larger text size
                                fontWeight: FontWeight.w400, // Lighter font weight
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
                child: profileCompleted
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
                          onPressed: () async {},
                          child: const Text(
                            "All done!",
                            style: TextStyle(color: Colors.white, fontSize: 16),
                          ),
                        ),
                      )
                    : uploadingProfile
                        ? const CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          )
                        : Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                message,
                                style: TextStyle(color: Colors.grey.shade300, fontSize: 14, height: 1.4),
                                textAlign: TextAlign.center,
                              ),
                              const SizedBox(height: 16),
                              Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 16.0),
                                child: LinearProgressIndicator(
                                  value: percentageCompleted,
                                  backgroundColor: Colors.grey[300],
                                  valueColor: const AlwaysStoppedAnimation<Color>(Colors.deepPurple),
                                ),
                              ),
                              // const SizedBox(height: 8),
                              // TODO: improve UI
                              // TODO: handle once completed UI
                              // TODO: backend endpoints call
                              // Text(
                              //   'asdasd ${(percentageCompleted * 100).toInt()}%',
                              //   style: const TextStyle(color: Colors.white, fontSize: 16),
                              // ),
                            ],
                          ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

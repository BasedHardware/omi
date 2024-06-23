import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/speaker_id/page.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:friend_private/widgets/scanning_ui.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:url_launcher/url_launcher.dart';

import 'widgets/transcript.dart';

class CapturePage extends StatefulWidget {
  final Function refreshMemories;
  final Function refreshMessages;
  final BTDeviceStruct? device;

  final GlobalKey<TranscriptWidgetState> transcriptChildWidgetKey;

  const CapturePage({
    super.key,
    required this.device,
    required this.refreshMemories,
    required this.transcriptChildWidgetKey,
    required this.refreshMessages,
  });

  @override
  State<CapturePage> createState() => _CapturePageState();
}

class _CapturePageState extends State<CapturePage> with AutomaticKeepAliveClientMixin {
  bool _hasTranscripts = false;
  final record = AudioRecorder();

  RecordState _state = RecordState.stop;

  @override
  bool get wantKeepAlive => true;

  _startRecording() async {
    record.onStateChanged().listen((event) {
      debugPrint('event: $event');
      setState(() => _state = event);
    });
    debugPrint('_startRecording: ${await record.hasPermission()}');
    if (await record.hasPermission()) {
      // Start recording to file
      var path = await getApplicationDocumentsDirectory();
      debugPrint(path.toString());
      // await record.cancel();
      await record.start(
        const RecordConfig(numChannels: 1),
        path: '${path.path}/recording.m4a',
      );
    }
  }

  @override
  void dispose() {
    record.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        ListView(children: [
          SharedPreferencesUtil().hasSpeakerProfile
              ? const SizedBox(height: 16)
              : Stack(
                  children: [
                    GestureDetector(
                      onTap: () {
                        Navigator.of(context).push(MaterialPageRoute(builder: (c) => const SpeakerIdPage()));
                        MixpanelManager().speechProfileCapturePageClicked();
                      },
                      child: Container(
                        decoration: BoxDecoration(
                          color: Colors.grey.shade900,
                          borderRadius: const BorderRadius.all(Radius.circular(12)),
                        ),
                        margin: const EdgeInsets.symmetric(vertical: 16, horizontal: 24),
                        padding: const EdgeInsets.all(16),
                        child: const Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: Row(
                                children: [
                                  Icon(Icons.multitrack_audio),
                                  SizedBox(width: 16),
                                  Text(
                                    'Set up speech profile',
                                    style: TextStyle(color: Colors.white, fontSize: 16),
                                  ),
                                ],
                              ),
                            ),
                            Icon(Icons.arrow_forward_ios)
                          ],
                        ),
                      ),
                    ),
                    Positioned(
                      top: 12,
                      right: 24,
                      child: Container(
                        width: 12,
                        height: 12,
                        decoration: const BoxDecoration(color: Colors.red, shape: BoxShape.circle),
                      ),
                    ),
                  ],
                ),
          ..._getConnectedDeviceWidgets(),
          TranscriptWidget(
              btDevice: widget.device,
              key: widget.transcriptChildWidgetKey,
              refreshMemories: widget.refreshMemories,
              refreshMessages: widget.refreshMessages,
              setHasTranscripts: (hasTranscripts) {
                if (_hasTranscripts == hasTranscripts) return;
                setState(() {
                  _hasTranscripts = hasTranscripts;
                });
              }),
          const SizedBox(height: 16)
        ]),
        Padding(
          padding: const EdgeInsets.only(bottom: 140),
          child: Align(
            alignment: Alignment.bottomCenter,
            child: MaterialButton(
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: BorderSide(color: _state == RecordState.record ? Colors.red : Colors.white)),
              onPressed: () async {
                debugPrint('await record.isRecording(): ${await record.isRecording()}');
                if (await record.isRecording()) {
                  await record.stop();
                  setState(() => _state == RecordState.stop);
                  var file = File('${(await getApplicationDocumentsDirectory()).path}/recording.m4a');
                  int bytes = await file.length();
                  var i = (log(bytes) / log(1024)).floor();
                  const suffixes = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];
                  var size = '${(bytes / pow(1024, i)).toStringAsFixed(2)} ${suffixes[i]}';
                  debugPrint('File size: $size');
                  var segments = await transcribeAudioFile2(file);
                  debugPrint('segments: $segments');
                } else {
                  setState(() => _state == RecordState.record);
                  _startRecording();
                }
              },
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    _state == RecordState.record
                        ? const Icon(Icons.stop, color: Colors.red, size: 24)
                        : const Icon(Icons.mic),
                    const SizedBox(width: 8),
                    Text(_state == RecordState.record ? 'Stop Recording' : 'Try With Phone Mic'),
                    const SizedBox(width: 4),
                  ],
                ),
              ),
            ),
          ),
        )
      ],
    );
  }

  _getConnectedDeviceWidgets() {
    if (_hasTranscripts) return [];
    if (widget.device == null) {
      return [
        const DeviceAnimationWidget(
          sizeMultiplier: 0.7,
        ),
        SharedPreferencesUtil().deviceId.isEmpty
            ? Column(
                children: [
                  const Text(
                    'You have not connected a Friend yet  🥺',
                    style: TextStyle(color: Colors.white, fontSize: 18),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 24),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      TextButton(
                        onPressed: () async {

                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.transparent,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        child: Container(
                          width: 80,
                          height: 45, // Fixed height for the button
                          alignment: Alignment.center,
                          child: const Text(
                            'Connect',
                            style: TextStyle(
                              fontWeight: FontWeight.w400,
                              fontSize: 16,
                              color: Colors.white,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 16),
                      Container(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
                          decoration: BoxDecoration(
                            color: Colors.deepPurple,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: TextButton(
                              onPressed: () {
                                launchUrl(Uri.parse('https://basedhardware.com'));
                              },
                              child: const Text(
                                'Buy Now',
                                style: TextStyle(color: Colors.white, fontSize: 16),
                              ))),
                    ],
                  ),
                  const SizedBox(height: 32),
                  // const Text(
                  //   'Or you can use your phone as\nthe audio source 👇',
                  //   style: TextStyle(color: Colors.white, fontSize: 18),
                  //   textAlign: TextAlign.center,
                  // ),
                ],
              )
            : const ScanningUI(
                string1: 'Looking for Friend wearable',
                string2: 'Locating your Friend device. Keep it near your phone for pairing',
              ),
      ];
    }
    // return [const DeviceAnimationWidget()];
    return [
      const Center(child: DeviceAnimationWidget(sizeMultiplier: 0.7)),
      Center(
          child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(width: 24),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.start,
            children: [
              const Text(
                'Listening',
                style: TextStyle(
                    fontFamily: 'SF Pro Display',
                    color: Colors.white,
                    fontSize: 29.0,
                    letterSpacing: 0.0,
                    fontWeight: FontWeight.w700,
                    height: 1.2),
                textAlign: TextAlign.center,
              ),
              Text(
                'DEVICE-${widget.device?.id.split('-').last.substring(0, 6)}',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16.0,
                  fontWeight: FontWeight.w500,
                  height: 1.5,
                ),
                textAlign: TextAlign.center,
              )
            ],
          ),
          const SizedBox(width: 24),
          Container(
            width: 10,
            height: 10,
            decoration: const BoxDecoration(
              color: Color.fromARGB(255, 0, 255, 8),
              shape: BoxShape.circle,
            ),
          ),
        ],
      )),
      const SizedBox(height: 8),
      const Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [],
      ),
    ];
  }
}

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/connect.dart';
import 'package:friend_private/pages/speaker_id/page.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:friend_private/widgets/scanning_ui.dart';
import 'package:friend_private/widgets/transcript.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:record/record.dart';
import 'package:url_launcher/url_launcher.dart';

getConnectionStateWidgets(BuildContext context, bool hasTranscripts, BTDeviceStruct? device) {
  if (hasTranscripts) return [];
  if (device == null) {
    return [
      const DeviceAnimationWidget(sizeMultiplier: 0.7),
      SharedPreferencesUtil().deviceId.isEmpty
          ? _getNoFriendConnectedYet(context)
          : const ScanningUI(
              string1: 'Looking for Friend wearable',
              string2: 'Locating your Friend device. Keep it near your phone for pairing',
            ),
    ];
  }
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
              'DEVICE-${device.id.split('-').last.substring(0, 6)}',
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
    // const Row(
    //   crossAxisAlignment: CrossAxisAlignment.center,
    //   mainAxisAlignment: MainAxisAlignment.center,
    //   children: [],
    // ),
  ];
}

_getNoFriendConnectedYet(BuildContext context) {
  return Column(
    children: [
      const SizedBox(height: 24),
      Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          // const Padding(
          //     padding: EdgeInsets.symmetric(horizontal: 32),
          //     child: Text(
          //       'Get a Friend wearable to start capturing your memories.',
          //       textAlign: TextAlign.center,
          //       style: TextStyle(color: Colors.white, fontSize: 18),
          //     )),
          // const SizedBox(height: 32),
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
                  onPressed: () {
                    launchUrl(Uri.parse('https://basedhardware.com'));
                    MixpanelManager().getFriendClicked();
                  },
                  child: const Text(
                    'Get a Friend',
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  ))),
          const SizedBox(height: 4),
          TextButton(
            onPressed: () async {
              Navigator.of(context).push(MaterialPageRoute(builder: (c) => const ConnectDevicePage()));
              MixpanelManager().connectFriendClicked();
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.transparent,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: const Text(
              'Connect',
              style: TextStyle(
                fontWeight: FontWeight.w400,
                fontSize: 18,
                color: Colors.white,
                decoration: TextDecoration.underline,
              ),
            ),
          ),
          const SizedBox(width: 16),
        ],
      ),
      // const Text(
      //   'Or you can use your phone as\nthe audio source 👇',
      //   style: TextStyle(color: Colors.white, fontSize: 18),
      //   textAlign: TextAlign.center,
      // ),
    ],
  );
}

speechProfileWidget(BuildContext context) {
  return SharedPreferencesUtil().hasSpeakerProfile
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
        );
}

getTranscriptWidget(bool memoryCreating, List<TranscriptSegment> segments, BTDeviceStruct? btDevice) {
  if (memoryCreating) {
    return const Padding(
      padding: EdgeInsets.only(top: 80),
      child: Center(child: CircularProgressIndicator(color: Colors.white)),
    );
  }

  if (segments.isEmpty) {
    return btDevice != null
        ? const Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(height: 80),
              Align(
                alignment: Alignment.center,
                child: Padding(
                  padding: EdgeInsets.symmetric(horizontal: 32.0),
                  child: Text(
                    textAlign: TextAlign.center,
                    'Your transcripts will start appearing\nhere after 30 seconds.',
                    style: TextStyle(color: Colors.white, height: 1.5, decoration: TextDecoration.underline),
                  ),
                ),
              )
            ],
          )
        : const SizedBox.shrink();
  }
  return TranscriptWidget(segments: segments);
}

getPhoneMicRecordingButton(VoidCallback recordingToggled, RecordState state) {
  if (SharedPreferencesUtil().deviceId.isNotEmpty) return const SizedBox.shrink();
  return Visibility(
    visible: false,
    child: Padding(
      padding: const EdgeInsets.only(bottom: 128),
      child: Align(
        alignment: Alignment.bottomCenter,
        child: MaterialButton(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            // side: BorderSide(color: state == RecordState.record ? Colors.red : Colors.white),
          ),
          onPressed: recordingToggled,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                state == RecordState.record
                    ? const Icon(Icons.stop, color: Colors.red, size: 24)
                    : const Icon(Icons.mic),
                const SizedBox(width: 8),
                Text(
                  state == RecordState.record ? 'Stop Recording' : 'Try With Phone Mic',
                  style: const TextStyle(fontSize: 14),
                ),
                const SizedBox(width: 4),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

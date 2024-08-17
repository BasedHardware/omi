import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/connect.dart';
import 'package:friend_private/pages/speaker_id/page.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/photos_grid.dart';
import 'package:friend_private/widgets/scanning_ui.dart';
import 'package:friend_private/widgets/transcript.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:lottie/lottie.dart';
import 'package:tuple/tuple.dart';
import 'package:url_launcher/url_launcher.dart';

getConnectionStateWidgets(
  BuildContext context,
  bool hasTranscripts,
  BTDeviceStruct? device,
  WebsocketConnectionStatus wsConnectionState,
  InternetStatus? internetStatus,
) {
  if (hasTranscripts) return [];
  if (device == null) {
    return [
      const DeviceAnimationWidget(sizeMultiplier: 0.7),
      SharedPreferencesUtil().btDeviceStruct.id == ''
          ? _getNoFriendConnectedYet(context)
          : const ScanningUI(
              string1: 'Looking for Friend wearable',
              string2: 'Locating your Friend device. Keep it near your phone for pairing',
            ),
    ];
  }

  bool isWifiDisconnected = internetStatus == InternetStatus.disconnected;
  bool isWebsocketError =
      wsConnectionState == WebsocketConnectionStatus.failed || wsConnectionState == WebsocketConnectionStatus.error;

  return [
    const Center(child: DeviceAnimationWidget(sizeMultiplier: 0.7)),
    GestureDetector(
      onTap: isWifiDisconnected || isWebsocketError
          ? () {
              showDialog(
                context: context,
                builder: (c) => getDialog(
                  context,
                  () => Navigator.pop(context),
                  () => Navigator.pop(context),
                  isWifiDisconnected ? 'Internet Connection Lost' : 'Connection Issue',
                  isWifiDisconnected
                      ? 'Your device is offline. Transcription is paused until connection is restored.'
                      : 'Unable to connect to the transcript service. Please restart the app or contact support if the problem persists.',
                  okButtonText: 'Ok',
                  singleButton: true,
                ),
              );
            }
          : null,
      child: Center(
          child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(width: 24),
          Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            mainAxisAlignment: MainAxisAlignment.start,
            children: [
              Text(
                isWifiDisconnected
                    ? 'No Internet'
                    : (!isWifiDisconnected && isWebsocketError)
                        ? 'Server Issue'
                        : 'Listening',
                style: TextStyle(
                    fontFamily: 'SF Pro Display',
                    color: Colors.white,
                    fontSize: isWifiDisconnected
                        ? 29
                        : isWebsocketError
                            ? 29
                            : 29,
                    letterSpacing: 0.0,
                    fontWeight: FontWeight.w700,
                    height: 1.2),
                textAlign: TextAlign.center,
              ),
              Text(
                '${device.name} (${device.getShortId()})',
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
          isWifiDisconnected
              ? Lottie.asset('assets/lottie_animations/no_internet.json', height: 56, width: 56)
              : isWebsocketError
                  // ? Lottie.network('https://lottie.host/8223dbf8-8a50-4d48-8e37-0b845b1f1094/TQcT5w5Mn4.json', height: 48, width: 48)
                  ? Lottie.asset('assets/lottie_animations/no_internet.json', height: 56, width: 56)
                  // TODO: find a better animation for server
                  : Container(
                      width: 10,
                      height: 10,
                      decoration: const BoxDecoration(
                        color: Color.fromARGB(255, 0, 255, 9),
                        shape: BoxShape.circle,
                      ),
                    ),
        ],
      )),
    ),
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

speechProfileWidget(BuildContext context, StateSetter setState, Function restartWebSocket) {
  return !SharedPreferencesUtil().hasSpeakerProfile
      ? Stack(
          children: [
            GestureDetector(
              onTap: () async {
                MixpanelManager().speechProfileCapturePageClicked();
                bool hasSpeakerProfile = SharedPreferencesUtil().hasSpeakerProfile;
                await routeToPage(context, const SpeakerIdPage());
                if (hasSpeakerProfile != SharedPreferencesUtil().hasSpeakerProfile) {
                  // setState(() {});
                  restartWebSocket();
                }
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
        )
      : const SizedBox(height: 16);
}

getTranscriptWidget(
  bool memoryCreating,
  List<TranscriptSegment> segments,
  List<Tuple2<String, String>> photos,
  BTDeviceStruct? btDevice,
) {
  if (memoryCreating) {
    return const Padding(
      padding: EdgeInsets.only(top: 80),
      child: Center(child: CircularProgressIndicator(color: Colors.white)),
    );
  }

  if (photos.isNotEmpty) return PhotosGridComponent(photos: photos);
  return TranscriptWidget(segments: segments);
}

connectionStatusWidgets(
  BuildContext context,
  List<TranscriptSegment> segments,
  WebsocketConnectionStatus wsConnectionState,
  InternetStatus? internetStatus,
) {
  if (segments.isEmpty) return [];

  bool isWifiDisconnected = internetStatus == InternetStatus.disconnected;
  bool isWebsocketError =
      wsConnectionState == WebsocketConnectionStatus.failed || wsConnectionState == WebsocketConnectionStatus.error;
  if (!isWifiDisconnected && !isWebsocketError) return [];
  return [
    GestureDetector(
      onTap: () {
        showDialog(
          context: context,
          builder: (c) => getDialog(
            context,
            () => Navigator.pop(context),
            () => Navigator.pop(context),
            isWifiDisconnected ? 'Internet Connection Lost' : 'Connection Issue',
            isWifiDisconnected
                ? 'Your device is offline. Transcription is paused until connection is restored.'
                : 'Unable to connect to the transcript service. Please restart the app or contact support if the problem persists.',
            okButtonText: 'Ok',
            singleButton: true,
          ),
        );
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          mainAxisAlignment: MainAxisAlignment.start,
          children: [
            Text(
              isWifiDisconnected ? 'No Internet' : 'Server Issue',
              style: TextStyle(
                color: Colors.grey.shade300,
                fontSize: 20,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(width: 16),
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: isWifiDisconnected
                  ? Lottie.asset('assets/lottie_animations/no_internet.json', height: 48, width: 48)
                  : Lottie.asset('assets/lottie_animations/no_internet.json', height: 48, width: 48),
            )
          ],
        ),
      ),
    )
  ];
}

getPhoneMicRecordingButton(VoidCallback recordingToggled, RecordingState state) {
  if (SharedPreferencesUtil().btDeviceStruct.id.isNotEmpty) return const SizedBox.shrink();
  return Visibility(
    visible: true,
    child: Padding(
      padding: const EdgeInsets.only(bottom: 128),
      child: Align(
        alignment: Alignment.bottomCenter,
        child: MaterialButton(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            // side: BorderSide(color: state == RecordState.record ? Colors.red : Colors.white),
          ),
          onPressed: state == RecordingState.initialising ? null : recordingToggled,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                state == RecordingState.initialising
                    ? const SizedBox(
                        height: 8,
                        width: 8,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : (state == RecordingState.record
                        ? const Icon(Icons.stop, color: Colors.red, size: 24)
                        : const Icon(Icons.mic)),
                const SizedBox(width: 8),
                Text(
                  state == RecordingState.initialising
                      ? 'Initialising Recorder'
                      : (state == RecordingState.record ? 'Stop Recording' : 'Try With Phone Mic'),
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

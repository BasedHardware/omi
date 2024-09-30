import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/pages/speech_profile/page.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/utils/analytics/intercom.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/photos_grid.dart';
import 'package:friend_private/widgets/transcript.dart';
import 'package:provider/provider.dart';
import 'package:tuple/tuple.dart';

class SpeechProfileCardWidget extends StatelessWidget {
  const SpeechProfileCardWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<HomeProvider>(
      builder: (context, provider, child) {
        if (provider.isLoading) return const SizedBox();
        return provider.hasSpeakerProfile
            ? const SizedBox()
            : Consumer<DeviceProvider>(builder: (context, device, child) {
                if (device.pairedDevice == null ||
                    !device.isConnected ||
                    device.pairedDevice?.firmwareRevision == '1.0.2') {
                  return const SizedBox();
                }
                return Stack(
                  children: [
                    GestureDetector(
                      onTap: () async {
                        MixpanelManager().pageOpened('Speech Profile Memories');
                        bool hasSpeakerProfile = SharedPreferencesUtil().hasSpeakerProfile;
                        await routeToPage(context, const SpeechProfilePage());
                        if (hasSpeakerProfile != SharedPreferencesUtil().hasSpeakerProfile) {
                          if (context.mounted) {
                            context.read<CaptureProvider>().onRecordProfileSettingChanged();
                          }
                        }
                      },
                      child: Container(
                        decoration: BoxDecoration(
                          color: Colors.grey.shade900,
                          borderRadius: const BorderRadius.all(Radius.circular(12)),
                        ),
                        margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
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
                                    'Teach Omi your voice',
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
              });
      },
    );
  }
}

class UpdateFirmwareCardWidget extends StatelessWidget {
  const UpdateFirmwareCardWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceProvider>(
      builder: (context, provider, child) {
        return (provider.pairedDevice == null || !provider.isConnected)
            ? const SizedBox()
            : (provider.pairedDevice?.firmwareRevision != '1.0.2')
                ? const SizedBox()
                : Stack(
                    children: [
                      GestureDetector(
                        onTap: () {
                          MixpanelManager().pageOpened('Update Firmware Memories');
                          IntercomManager.instance.displayFirmwareUpdateArticle();
                        },
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.grey.shade900,
                            borderRadius: const BorderRadius.all(Radius.circular(12)),
                          ),
                          margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                          padding: const EdgeInsets.all(16),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Expanded(
                                child: Row(
                                  children: [
                                    Icon(Icons.upload),
                                    SizedBox(width: 16),
                                    Text(
                                      'Update your Firmware',
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
      },
    );
  }
}

getTranscriptWidget(
  bool memoryCreating,
  List<TranscriptSegment> segments,
  List<Tuple2<String, String>> photos,
  BtDevice? btDevice,
) {
  if (memoryCreating) {
    return const Padding(
      padding: EdgeInsets.only(top: 80),
      child: Center(child: CircularProgressIndicator(color: Colors.white)),
    );
  }

  return Column(
    children: [
      if (photos.isNotEmpty) const PhotosGridComponent(),
      if (segments.isNotEmpty) TranscriptWidget(segments: segments),
    ],
  );
}

getLiteTranscriptWidget(
  List<TranscriptSegment> segments,
  List<Tuple2<String, String>> photos,
  BtDevice? btDevice,
) {
  return Column(
    children: [
      // TODO: thinh, be reenabled soon
      //if (photos.isNotEmpty) PhotosGridComponent(photos: photos),
      if (segments.isNotEmpty)
        LiteTranscriptWidget(
          segments: segments,
        ),
    ],
  );
}

getPhoneMicRecordingButton(VoidCallback recordingToggled, RecordingState state) {
  if (SharedPreferencesUtil().btDevice.id.isNotEmpty) return const SizedBox.shrink();
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

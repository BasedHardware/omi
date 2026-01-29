import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/audio/wav_bytes.dart';

class LiteCaptureWidget extends StatefulWidget {
  const LiteCaptureWidget({super.key});

  @override
  State<LiteCaptureWidget> createState() => LiteCaptureWidgetState();
}

class LiteCaptureWidgetState extends State<LiteCaptureWidget> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  setHasTranscripts(bool hasTranscripts) {
    context.read<CaptureProvider>().setHasTranscripts(hasTranscripts);
  }

  @override
  void initState() {
    WavBytesUtil.clearTempWavFiles();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    // Use Selector to only rebuild when segments/photos change, not on metrics, recording state, etc.
    // This reduces battery drain by avoiding unnecessary rebuilds during transcription.
    return Selector<CaptureProvider, (List<TranscriptSegment>, List<ConversationPhoto>)>(
      selector: (_, provider) => (provider.segments, provider.photos),
      shouldRebuild: (prev, next) =>
          prev.$1.length != next.$1.length ||
          prev.$2.length != next.$2.length ||
          (prev.$1.isNotEmpty && next.$1.isNotEmpty && prev.$1.last.text != next.$1.last.text),
      builder: (context, data, child) {
        final (segments, photos) = data;
        return Selector<DeviceProvider, BtDevice?>(
          selector: (_, provider) => provider.connectedDevice,
          builder: (context, connectedDevice, child) {
            return getLiteTranscriptWidget(segments, photos, connectedDevice);
          },
        );
      },
    );
  }
}

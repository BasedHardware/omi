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
    // Use Selector to only rebuild when segments or photos change (not on metrics, recording state, etc.)
    return Selector<CaptureProvider, (List<TranscriptSegment>, List<ConversationPhoto>)>(
      selector: (_, provider) => (provider.segments, provider.photos),
      shouldRebuild: (previous, next) =>
          previous.$1.length != next.$1.length ||
          previous.$2.length != next.$2.length ||
          (previous.$1.isNotEmpty && next.$1.isNotEmpty && previous.$1.last.text != next.$1.last.text),
      builder: (context, data, child) {
        final (segments, photos) = data;
        // Only select connectedDevice from DeviceProvider
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

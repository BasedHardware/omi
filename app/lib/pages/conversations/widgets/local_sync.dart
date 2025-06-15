import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/pages/sdcard/sdcard_transfer_progress.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';

class LocalSyncWidget extends StatefulWidget {
  const LocalSyncWidget({super.key});

  @override
  State<LocalSyncWidget> createState() => _LocalSyncWidgetState();
}

enum LocalSyncStatus {
  disabled,
  inProgress,
  flush, // flushed to disk
}

class _LocalSyncWidgetState extends State<LocalSyncWidget> {
  LocalSyncStatus? _status;
  Timer? _missSecondsInEstTimer;
  bool _missSecondsInEstTimerEnabled = false;
  int _missSeconds = 0;

  @override
  void initState() {
    super.initState();

    _missSecondsInEstTimer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (_missSecondsInEstTimerEnabled) {
        setState(() {
          _missSeconds++;
        });
      }
    });
  }

  @override
  void dispose() {
    _missSecondsInEstTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<ConversationProvider, CaptureProvider>(builder: (context, provider, captureProvider, child) {
      var previousStatus = _status;
      if (provider.missingWalsInSeconds >= 120) {
        _status = LocalSyncStatus.flush;
      } else if (!captureProvider.isWalSupported) {
        _status = LocalSyncStatus.disabled;
      } else if (!captureProvider.transcriptServiceReady && captureProvider.recordingDeviceServiceReady) {
        _status = LocalSyncStatus.inProgress;
      } else {
        _status = LocalSyncStatus.disabled;
      }

      // miss seconds
      if (_status == LocalSyncStatus.inProgress || _status == LocalSyncStatus.flush) {
        if (previousStatus != _status) {
          _missSeconds = provider.missingWalsInSeconds;
        }
      }

      // timer
      if ((_status == LocalSyncStatus.inProgress || _status == LocalSyncStatus.flush) &&
          (!captureProvider.transcriptServiceReady && captureProvider.recordingDeviceServiceReady)) {
        _missSecondsInEstTimerEnabled = true;
      } else {
        _missSecondsInEstTimerEnabled = false;
      }

      // in progress
      if (_status == LocalSyncStatus.inProgress) {
        return Container(
          decoration: BoxDecoration(
            color: Colors.grey.shade900,
            borderRadius: const BorderRadius.all(Radius.circular(12)),
          ),
          margin: const EdgeInsets.fromLTRB(16, 16, 16, 16),
          padding: const EdgeInsets.all(16),
          child: Text(
            '${secondsToHumanReadable(_missSeconds.toString())} On-Device Conversations',
            style: Theme.of(context).textTheme.bodyMedium!.copyWith(fontSize: 16),
            textAlign: TextAlign.center,
          ),
        );
      }

      // ready to sync
      if (_status == LocalSyncStatus.flush) {
        return const SizedBox.shrink();
        // return GestureDetector(
        //   onTap: () {
        //     routeToPage(context, const SyncPage());
        //   },
        //   child: Container(
        //     decoration: BoxDecoration(
        //       color: Colors.grey.shade900,
        //       borderRadius: const BorderRadius.all(Radius.circular(12)),
        //     ),
        //     padding: const EdgeInsets.all(16),
        //     margin: const EdgeInsets.fromLTRB(16, 16, 16, 0),
        //     child: Row(
        //       mainAxisAlignment: MainAxisAlignment.spaceBetween,
        //       crossAxisAlignment: CrossAxisAlignment.center,
        //       children: [
        //         const Row(
        //           children: [
        //             Text(
        //               'Stay in Sync',
        //               style: TextStyle(color: Colors.white, fontSize: 16),
        //               textAlign: TextAlign.center,
        //             ),
        //           ],
        //         ),
        //         Text(
        //           '${secondsToHumanReadable(_missSeconds.toString())} available',
        //           style: Theme.of(context).textTheme.bodyMedium!.copyWith(decoration: TextDecoration.underline),
        //         ),
        //       ],
        //     ),
        //   ),
        // );
      }

      return const SizedBox.shrink();
    });
  }
}

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/pages/memories/sync_page.dart';
import 'package:friend_private/pages/sdcard/sdcard_transfer_progress.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/utils/other/string_utils.dart';
import 'package:friend_private/utils/other/temp.dart';
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
    return Consumer2<MemoryProvider, CaptureProvider>(builder: (context, provider, captureProvider, child) {
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
            '${convertToHHMMSS(_missSeconds)} of conversation locally',
            style: const TextStyle(color: Colors.white, fontSize: 16),
            textAlign: TextAlign.center,
          ),
        );
      }

      // ready to sync
      if (_status == LocalSyncStatus.flush) {
        return GestureDetector(
          onTap: () {
            routeToPage(context, const SyncPage());
          },
          child: Container(
            decoration: BoxDecoration(
              color: Colors.grey.shade900,
              borderRadius: const BorderRadius.all(Radius.circular(12)),
            ),
            margin: const EdgeInsets.fromLTRB(16, 16, 16, 16),
            padding: const EdgeInsets.all(16),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Row(
                    children: [
                      const Icon(Icons.download_rounded),
                      const SizedBox(width: 16),
                      Text(
                        '${secondsToHumanReadable(_missSeconds.toString())} available. Sync now?',
                        style: const TextStyle(color: Colors.white, fontSize: 16),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      }

      return const SizedBox.shrink();
    });
  }
}

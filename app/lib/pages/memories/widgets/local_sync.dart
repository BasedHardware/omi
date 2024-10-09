import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/pages/memories/page.dart';
import 'package:friend_private/pages/memories/sync_page.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/developer_mode_provider.dart';
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
  int _missSeconds = 0;

  @override
  void dispose() {
    _missSecondsInEstTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<MemoryProvider, CaptureProvider>(builder: (context, provider, captureProvider, child) {
      if (provider.missingWalsInSeconds > 120) {
        _status = LocalSyncStatus.flush;
        _missSeconds = max(_missSeconds, provider.missingWalsInSeconds); // est. good for ux
      } else if (!captureProvider.isWalSupported) {
        _status = LocalSyncStatus.disabled;
        _missSecondsInEstTimer?.cancel();
      } else if ((!captureProvider.transcriptServiceReady && captureProvider.recordingDeviceServiceReady) ||
          provider.missingWalsInSeconds > 0) {
        var previousStatus = _status;
        _status = LocalSyncStatus.inProgress;

        // Change state to in progress
        if (previousStatus != LocalSyncStatus.inProgress) {
          _missSecondsInEstTimer?.cancel();
          _missSeconds = provider.missingWalsInSeconds;
          _missSecondsInEstTimer = Timer.periodic(const Duration(seconds: 1), (t) {
            setState(() {
              _missSeconds++;
            });
          });
        }
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
                        '${secondsToHumanReadable(_missSeconds)} available. Sync now?',
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

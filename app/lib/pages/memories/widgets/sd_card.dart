import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/pages/memories/sync_page.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';

class SdCardBannerWidget extends StatefulWidget {
  const SdCardBannerWidget({super.key});

  @override
  State<SdCardBannerWidget> createState() => _SdCardBannerWidgetState();
}

class _SdCardBannerWidgetState extends State<SdCardBannerWidget> {
  bool _visible = true;
  Timer? _visibleTimer;

  @override
  void dispose() {
    _visibleTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<CaptureProvider>(builder: (context, provider, child) {
      if (!_visible || !provider.sdCardReady) {
        return const SizedBox.shrink();
      }

      var totalRemainingSeconds = provider.sdCardSecondsTotal - provider.sdCardSecondsReceived;
      if (totalRemainingSeconds <= 0) {
        return const SizedBox.shrink();
      }

      _visibleTimer?.cancel();
      _visibleTimer = Timer(const Duration(seconds: 15), () {
        setState(() {
          _visible = false;
        });
      });

      /// Friend V2 SD CARD functionality
      String totalsdCardSecondsRemainingString = totalRemainingSeconds.toStringAsFixed(2);
      var banner = 'You have $totalsdCardSecondsRemainingString seconds of Storage Remaining. Click here to see';

      return GestureDetector(
        onTap: () {
          routeToPage(context, const SyncPage());
          _visibleTimer?.cancel();
          setState(() {
            _visible = false;
          });
        },
        child: Container(
          padding: const EdgeInsets.all(16),
          color: Colors.green,
          child: Row(
            mainAxisSize: MainAxisSize.max,
            children: [
              Expanded(
                child: Text(
                  banner,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.normal,
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    });
  }
}

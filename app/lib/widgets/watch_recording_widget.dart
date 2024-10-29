import 'package:flutter/material.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/services/watch_manager.dart';
import 'package:provider/provider.dart';

class WatchRecordingWidget extends StatelessWidget {
  const WatchRecordingWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, WatchManager>(
      builder: (context, provider, watchManager, _) {
        return StreamBuilder<String>(
          stream: watchManager.errors,
          builder: (context, snapshot) {
            final hasError = snapshot.hasData;
            final errorMessage = snapshot.data;

            return Container(
              margin: const EdgeInsets.symmetric(horizontal: 16),
              decoration: BoxDecoration(
                color: Colors.grey.shade900,
                borderRadius: BorderRadius.circular(16.0),
              ),
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Row(
                  children: [
                    Icon(
                      hasError ? Icons.error_outline : Icons.watch,
                      color: hasError ? Colors.red :
                             (provider.isWatchRecording ? Colors.red : Colors.grey),
                      size: 22,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        hasError ? errorMessage! :
                        (provider.isWatchRecording ? 'Recording from Watch' : 'Watch Connected'),
                        style: Theme.of(context).textTheme.bodyMedium!.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    if (hasError)
                      IconButton(
                        icon: const Icon(Icons.refresh),
                        onPressed: () => watchManager.initialize(),
                        color: Colors.white,
                      ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }
}

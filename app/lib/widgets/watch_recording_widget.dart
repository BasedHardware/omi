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
        return StreamBuilder<WatchConnectionState>(
          stream: watchManager.connectionState,
          builder: (context, snapshot) {
            final connectionState = snapshot.data ?? WatchConnectionState.disconnected;
            final isRecording = provider.isWatchRecording;

            return Container(
              margin: const EdgeInsets.symmetric(horizontal: 16),
              decoration: BoxDecoration(
                color: Colors.grey.shade900,
                borderRadius: BorderRadius.circular(16.0),
              ),
              semanticsLabel: _getSemanticLabel(connectionState, isRecording),
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Row(
                  children: [
                    _buildStatusIcon(connectionState, isRecording),
                    const SizedBox(width: 12),
                    _buildStatusText(context, connectionState, isRecording),
                    if (connectionState == WatchConnectionState.error) ...[
                      const Spacer(),
                      IconButton(
                        icon: const Icon(Icons.refresh, color: Colors.white),
                        onPressed: () => watchManager.initialize(),
                        tooltip: 'Retry connection',
                      ),
                    ],
                    if (isRecording && connectionState == WatchConnectionState.connected) ...[
                      const Spacer(),
                      _buildRecordingIndicator(context),
                    ],
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  String _getSemanticLabel(WatchConnectionState state, bool isRecording) {
    switch (state) {
      case WatchConnectionState.connected:
        return isRecording ? 'Watch is currently recording' : 'Watch is connected';
      case WatchConnectionState.connecting:
        return 'Watch is connecting';
      case WatchConnectionState.error:
        return 'Watch connection error';
      case WatchConnectionState.disconnected:
        return 'Watch is disconnected';
    }
  }

  Widget _buildStatusIcon(WatchConnectionState state, bool isRecording) {
    switch (state) {
      case WatchConnectionState.connected:
        return Icon(
          Icons.watch,
          color: isRecording ? Colors.red : Colors.grey,
          size: 22,
        );
      case WatchConnectionState.connecting:
        return const SizedBox(
          width: 22,
          height: 22,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            valueColor: AlwaysStoppedAnimation<Color>(Colors.blue),
          ),
        );
      case WatchConnectionState.error:
        return const Icon(
          Icons.error_outline,
          color: Colors.red,
          size: 22,
        );
      case WatchConnectionState.disconnected:
        return const Icon(
          Icons.watch_off,
          color: Colors.grey,
          size: 22,
        );
    }
  }

  Widget _buildStatusText(BuildContext context, WatchConnectionState state, bool isRecording) {
    String text;
    Color backgroundColor = Colors.grey.shade800;

    switch (state) {
      case WatchConnectionState.connected:
        text = isRecording ? 'Recording from Watch' : 'Watch Connected';
        break;
      case WatchConnectionState.connecting:
        text = 'Connecting to Watch...';
        break;
      case WatchConnectionState.error:
        text = 'Watch Connection Error';
        backgroundColor = Colors.red.withOpacity(0.2);
        break;
      case WatchConnectionState.disconnected:
        text = 'Watch Disconnected';
        break;
    }

    return Container(
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(16),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Text(
        text,
        style: Theme.of(context).textTheme.bodyMedium!.copyWith(
              color: Colors.white,
              fontWeight: FontWeight.w600,
            ),
      ),
    );
  }

  Widget _buildRecordingIndicator(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: const BoxDecoration(
            color: Colors.red,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 4),
        Text(
          'Recording',
          style: Theme.of(context).textTheme.bodyMedium!.copyWith(
                color: Colors.red,
              ),
        ),
      ],
    );
  }
}

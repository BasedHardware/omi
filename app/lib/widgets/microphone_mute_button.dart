import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/microphone_provider.dart';

class MicrophoneMuteButton extends StatelessWidget {
  final bool showLabel;
  final double iconSize;

  const MicrophoneMuteButton({
    super.key,
    this.showLabel = false,
    this.iconSize = 24.0,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<MicrophoneProvider>(
      builder: (context, micProvider, child) {
        return GestureDetector(
          onTap: () => _showMuteOptions(context, micProvider),
          onLongPress: () => micProvider.toggleMute(),
          child: Container(
            padding: const EdgeInsets.all(8.0),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: micProvider.isMuted ? Colors.red.withOpacity(0.2) : Colors.transparent,
              border: micProvider.isMuted ? Border.all(color: Colors.red.withOpacity(0.5), width: 1) : null,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  micProvider.isMuted ? Icons.mic_off : Icons.mic,
                  color: micProvider.isMuted ? Colors.red : Colors.white,
                  size: iconSize,
                ),
                if (showLabel) ...[
                  const SizedBox(height: 4),
                  Text(
                    micProvider.isMuted ? 'Muted' : 'Live',
                    style: TextStyle(
                      color: micProvider.isMuted ? Colors.red : Colors.white,
                      fontSize: 10,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  void _showMuteOptions(BuildContext context, MicrophoneProvider micProvider) {
    if (micProvider.isMuted) {
      // If already muted, just unmute
      micProvider.unmute();
      return;
    }

    // Show options for muting
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.grey[900],
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (BuildContext context) {
        return Container(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Mute Microphone',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              const Text(
                'Temporarily stop listening and transcribing',
                style: TextStyle(
                  color: Colors.grey,
                  fontSize: 14,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              _buildMuteOption(
                context,
                micProvider,
                'Mute indefinitely',
                'Tap the mic button again to unmute',
                Icons.mic_off,
                null,
              ),
              const SizedBox(height: 12),
              _buildMuteOption(
                context,
                micProvider,
                'Mute for 15 minutes',
                'Automatically unmute after 15 minutes',
                Icons.timer,
                15,
              ),
              const SizedBox(height: 12),
              _buildMuteOption(
                context,
                micProvider,
                'Mute for 1 hour',
                'Automatically unmute after 1 hour',
                Icons.timer,
                60,
              ),
              const SizedBox(height: 12),
              _buildMuteOption(
                context,
                micProvider,
                'Mute for 2 hours',
                'Automatically unmute after 2 hours',
                Icons.timer,
                120,
              ),
              const SizedBox(height: 20),
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text(
                  'Cancel',
                  style: TextStyle(color: Colors.grey),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildMuteOption(
    BuildContext context,
    MicrophoneProvider micProvider,
    String title,
    String subtitle,
    IconData icon,
    int? durationMinutes,
  ) {
    return InkWell(
      onTap: () {
        Navigator.pop(context);
        micProvider.mute(durationMinutes: durationMinutes);
      },
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.grey[800],
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Icon(icon, color: Colors.white, size: 24),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    style: const TextStyle(
                      color: Colors.grey,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
            const Icon(Icons.arrow_forward_ios, color: Colors.grey, size: 16),
          ],
        ),
      ),
    );
  }
}

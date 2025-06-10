import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/providers/mute_provider.dart';
import 'package:provider/provider.dart';

/// A beautiful mute toggle widget with professional UX patterns
class MuteToggleWidget extends StatefulWidget {
  /// Whether to show the timer options
  final bool showTimerOptions;

  /// Size of the icon
  final double iconSize;

  /// Custom color for the muted state
  final Color? mutedColor;

  /// Custom color for the unmuted state
  final Color? unmuteColor;

  const MuteToggleWidget({
    super.key,
    this.showTimerOptions = true,
    this.iconSize = 24.0,
    this.mutedColor,
    this.unmuteColor,
  });

  @override
  State<MuteToggleWidget> createState() => _MuteToggleWidgetState();
}

class _MuteToggleWidgetState extends State<MuteToggleWidget> with TickerProviderStateMixin {
  late AnimationController _animationController;
  Timer? _updateTimer;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 150),
      vsync: this,
    );

    // Start timer to update remaining time every second
    _updateTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (mounted) {
        setState(() {
          // This will trigger a rebuild to update the time display
        });
      }
    });
  }

  @override
  void dispose() {
    _animationController.dispose();
    _updateTimer?.cancel();
    super.dispose();
  }

  void _handleTap(MuteProvider muteProvider) {
    // Haptic feedback
    HapticFeedback.lightImpact();

    // Animation
    _animationController.forward().then((_) {
      _animationController.reverse();
    });

    if (muteProvider.isMuted) {
      // Show unmute confirmation
      _showUnmuteDialog(muteProvider);
    } else {
      // Show mute options
      _showMuteOptions(muteProvider);
    }
  }

  void _onLongPress(MuteProvider muteProvider) {
    // Haptic feedback for long press - quick toggle
    HapticFeedback.mediumImpact();
    muteProvider.toggleMute();
  }

  void _showUnmuteDialog(MuteProvider muteProvider) {
    // Get remaining time if timed mute is active
    final remainingTime = muteProvider.timeRemaining;

    showDialog(
      context: context,
      barrierDismissible: true,
      builder: (BuildContext context) {
        return Dialog(
          backgroundColor: Colors.transparent,
          child: Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: Colors.grey[900],
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 64,
                  height: 64,
                  decoration: BoxDecoration(
                    color: Colors.red.withOpacity(0.2),
                    shape: BoxShape.circle,
                  ),
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      const Icon(
                        FontAwesomeIcons.microphone,
                        color: Colors.red,
                        size: 28,
                      ),
                      // Slash overlay
                      Transform.rotate(
                        angle: -0.785398, // -45 degrees in radians
                        child: Container(
                          width: 3,
                          height: 36,
                          decoration: BoxDecoration(
                            color: Colors.red,
                            borderRadius: BorderRadius.circular(1.5),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  'Microphone is muted',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (remainingTime != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    'Will unmute in ${_formatDuration(remainingTime)}',
                    style: TextStyle(
                      color: Colors.grey[400],
                      fontSize: 14,
                    ),
                  ),
                ],
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      child: TextButton(
                        onPressed: () => Navigator.pop(context),
                        style: TextButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                        child: Text(
                          'Keep muted',
                          style: TextStyle(color: Colors.grey[400]),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () {
                          muteProvider.unmuteAll();
                          Navigator.pop(context);
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: Colors.black,
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                        child: const Text(
                          'Unmute now',
                          style: TextStyle(fontWeight: FontWeight.w600),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _showMuteOptions(MuteProvider muteProvider) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (BuildContext context) {
        return Container(
          decoration: BoxDecoration(
            color: Colors.grey[900],
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: SafeArea(
            child: SingleChildScrollView(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Handle bar
                    Container(
                      width: 40,
                      height: 4,
                      margin: const EdgeInsets.only(bottom: 16),
                      decoration: BoxDecoration(
                        color: Colors.grey[700],
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                    // Header
                    const Text(
                      'Mute Microphone',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Temporarily stop listening and transcribing',
                      style: TextStyle(
                        color: Colors.grey[400],
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 20),
                    // Options
                    _buildMuteOption(
                      muteProvider: muteProvider,
                      icon: FontAwesomeIcons.microphoneSlash,
                      title: 'Mute indefinitely',
                      subtitle: 'Tap the mic button again to unmute',
                      onTap: () {
                        Navigator.pop(context);
                        muteProvider.toggleMute();
                      },
                    ),
                    _buildMuteOption(
                      muteProvider: muteProvider,
                      icon: Icons.schedule,
                      title: 'Mute for 30 minutes',
                      subtitle: 'Automatically unmute after 30 minutes',
                      onTap: () {
                        Navigator.pop(context);
                        muteProvider.muteForDuration(const Duration(minutes: 30));
                      },
                    ),
                    _buildMuteOption(
                      muteProvider: muteProvider,
                      icon: Icons.schedule,
                      title: 'Mute for 1 hour',
                      subtitle: 'Automatically unmute after 1 hour',
                      onTap: () {
                        Navigator.pop(context);
                        muteProvider.muteForDuration(const Duration(hours: 1));
                      },
                    ),
                    _buildMuteOption(
                      muteProvider: muteProvider,
                      icon: Icons.schedule,
                      title: 'Mute for 2 hours',
                      subtitle: 'Automatically unmute after 2 hours',
                      onTap: () {
                        Navigator.pop(context);
                        muteProvider.muteForDuration(const Duration(hours: 2));
                      },
                    ),
                    const SizedBox(height: 8),
                    // Cancel button
                    TextButton(
                      onPressed: () => Navigator.pop(context),
                      style: TextButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        minimumSize: const Size(double.infinity, 48),
                      ),
                      child: Text(
                        'Cancel',
                        style: TextStyle(
                          color: Colors.grey[400],
                          fontSize: 16,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildMuteOption({
    required MuteProvider muteProvider,
    required IconData icon,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.grey[800]?.withOpacity(0.5),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: Colors.grey[700]!.withOpacity(0.3),
                width: 1,
              ),
            ),
            child: Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: Colors.grey[700]?.withOpacity(0.5),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    icon,
                    color: Colors.white,
                    size: 18,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 1),
                      Text(
                        subtitle,
                        style: TextStyle(
                          color: Colors.grey[400],
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(
                  Icons.chevron_right,
                  color: Colors.grey[600],
                  size: 18,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _formatDuration(Duration duration) {
    if (duration.inHours > 0) {
      final hours = duration.inHours;
      final minutes = duration.inMinutes % 60;
      return minutes > 0 ? '$hours hr ${minutes} min' : '$hours hr';
    } else {
      return '${duration.inMinutes} min';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<MuteProvider>(
      builder: (context, muteProvider, child) {
        final isMuted = muteProvider.isMuted;
        final isTimerActive = muteProvider.isTimerMuteActive;
        final timeRemaining = muteProvider.timeRemaining;

        return GestureDetector(
          onTap: () => _handleTap(muteProvider),
          onLongPress: () => _onLongPress(muteProvider),
          child: AnimatedBuilder(
            animation: _animationController,
            builder: (context, child) {
              return Transform.scale(
                scale: 1.0 - (_animationController.value * 0.05),
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    // Base container with consistent size - matching settings icon touch target
                    Container(
                      width: 40.0,
                      height: 40.0,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: isMuted ? Colors.red.withOpacity(0.15) : Colors.white.withOpacity(0.08),
                      ),
                    ),
                    // Microphone icon - sized to match other app bar icons
                    Icon(
                      FontAwesomeIcons.microphone,
                      color: isMuted ? Colors.red.shade400 : Colors.white,
                      size: 20.0, // Slightly smaller than settings (36px) but larger than tabs (18px)
                    ),
                    // Slash overlay when muted
                    if (isMuted)
                      Transform.rotate(
                        angle: -0.785398, // -45 degrees in radians
                        child: Container(
                          width: 2.5,
                          height: 28,
                          decoration: BoxDecoration(
                            color: Colors.red.shade400,
                            borderRadius: BorderRadius.circular(1.25),
                          ),
                        ),
                      ),
                    // Timer indicator with time remaining
                    if (isTimerActive && timeRemaining != null)
                      Positioned(
                        top: 2,
                        right: 2,
                        child: Container(
                          constraints: const BoxConstraints(
                            maxWidth: 30,
                            maxHeight: 14,
                          ),
                          padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 1),
                          decoration: BoxDecoration(
                            color: Colors.orange.shade600,
                            borderRadius: BorderRadius.circular(7),
                            border: Border.all(color: Colors.black87, width: 0.5),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.schedule,
                                size: 7,
                                color: Colors.white,
                              ),
                              const SizedBox(width: 1),
                              Flexible(
                                child: Text(
                                  _formatTimerDisplay(timeRemaining),
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 6,
                                    fontWeight: FontWeight.bold,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              );
            },
          ),
        );
      },
    );
  }

  String _formatTimerDisplay(Duration duration) {
    if (duration.inHours > 0) {
      return '${duration.inHours}h${duration.inMinutes.remainder(60)}m';
    } else {
      return '${duration.inMinutes}m';
    }
  }
}

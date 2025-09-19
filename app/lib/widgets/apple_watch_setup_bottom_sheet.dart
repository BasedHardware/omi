import 'package:flutter/material.dart';
import 'package:omi/src/flutter_communicator.g.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';

class AppleWatchSetupBottomSheet extends StatefulWidget {
  final String deviceId;
  final VoidCallback? onConnected;

  const AppleWatchSetupBottomSheet({
    Key? key,
    required this.deviceId,
    this.onConnected,
  }) : super(key: key);

  @override
  State<AppleWatchSetupBottomSheet> createState() => _AppleWatchSetupBottomSheetState();
}

class _AppleWatchSetupBottomSheetState extends State<AppleWatchSetupBottomSheet> {
  bool _isChecking = false;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Colors.black,
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(20),
          topRight: Radius.circular(20),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Handle bar
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white30,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 24),

            // Watch icon
            const Icon(
              Icons.watch,
              size: 60,
              color: Colors.white,
            ),
            const SizedBox(height: 16),

            // Title
            const Text(
              'Apple Watch Not Found',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 12),

            // Instructions
            const Text(
              'To use your Apple Watch with Omi:\n\n'
              '1. Install the Omi app on your Apple Watch\n'
              '2. Open the Omi app on your watch\n'
              '3. Make sure your watch is connected to your phone\n'
              '4. Tap "I\'ve Connected" below',
              style: TextStyle(
                fontSize: 14,
                color: Colors.white70,
                height: 1.4,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),

            // Action buttons
            Row(
              children: [
                // Cancel button
                Expanded(
                  child: TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text(
                      'Cancel',
                      style: TextStyle(color: Colors.white70),
                    ),
                  ),
                ),
                const SizedBox(width: 12),

                // I've Connected button
                Expanded(
                  flex: 2,
                  child: ElevatedButton(
                    onPressed: _isChecking ? null : _checkConnection,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.blue,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(25),
                      ),
                      padding: const EdgeInsets.symmetric(vertical: 12),
                    ),
                    child: _isChecking
                        ? const SizedBox(
                            height: 16,
                            width: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : const Text(
                            'I\'ve Connected',
                            style: TextStyle(fontWeight: FontWeight.w600),
                          ),
                  ),
                ),
              ],
            ),

            // Help text
            const SizedBox(height: 16),
            TextButton(
              onPressed: _showHelpDialog,
              child: const Text(
                'Need help installing the watch app?',
                style: TextStyle(
                  color: Colors.blue,
                  fontSize: 12,
                ),
              ),
            ),

            // Bottom padding for safe area
            SizedBox(height: MediaQuery.of(context).padding.bottom),
          ],
        ),
      ),
    );
  }

  Future<void> _checkConnection() async {
    setState(() {
      _isChecking = true;
    });

    try {
      // Check if the watch is now reachable
      final hostAPI = WatchRecorderHostAPI();
      final bool isReachable = await hostAPI.isWatchReachable();

      if (isReachable) {
        AppSnackbar.showSnackbar(
          'Apple Watch connected successfully!',
          duration: const Duration(seconds: 2),
        );

        // Close the bottom sheet and notify parent
        Navigator.of(context).pop();
        widget.onConnected?.call();
      } else {
        AppSnackbar.showSnackbar(
          'Apple Watch still not reachable. Please make sure the Omi app is open on your watch.',
          duration: const Duration(seconds: 4),
        );
      }
    } catch (e) {
      AppSnackbar.showSnackbar(
        'Error checking connection: $e',
        duration: const Duration(seconds: 3),
      );
    } finally {
      setState(() {
        _isChecking = false;
      });
    }
  }

  void _showHelpDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: Colors.grey[900],
        title: const Text(
          'Installing Omi on Apple Watch',
          style: TextStyle(color: Colors.white),
        ),
        content: const Text(
          'To install Omi on your Apple Watch:\n\n'
          '1. Open the Watch app on your iPhone\n'
          '2. Scroll down to "Available Apps"\n'
          '3. Find "Omi" and tap "Install"\n'
          '4. Wait for installation to complete\n'
          '5. Open the Omi app on your Apple Watch\n'
          '6. Come back and tap "I\'ve Connected"',
          style: TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Got it'),
          ),
        ],
      ),
    );
  }
}

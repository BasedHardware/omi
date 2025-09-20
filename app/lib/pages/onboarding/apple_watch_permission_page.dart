import 'package:flutter/material.dart';
import 'package:omi/services/devices/apple_watch_connection.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';

class AppleWatchPermissionPage extends StatefulWidget {
  final AppleWatchDeviceConnection connection;
  final VoidCallback? onPermissionGranted;

  const AppleWatchPermissionPage({
    Key? key,
    required this.connection,
    this.onPermissionGranted,
  }) : super(key: key);

  @override
  State<AppleWatchPermissionPage> createState() => _AppleWatchPermissionPageState();
}

class _AppleWatchPermissionPageState extends State<AppleWatchPermissionPage> {
  bool _isRequestingPermission = false;
  bool _permissionRequested = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: const Text(
          'Apple Watch Setup',
          style: TextStyle(color: Colors.white),
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Watch icon
            const Icon(
              Icons.watch,
              size: 80,
              color: Colors.white,
            ),
            const SizedBox(height: 32),

            // Title
            const Text(
              'Microphone Permission Required',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),

            // Instructions
            Text(
              _permissionRequested
                  ? 'Great! Now follow these steps:\n\n1. Check your Apple Watch for the permission popup\n2. Tap "Allow" to grant microphone access\n3. The watch app will close automatically\n4. Open the Omi app on your watch again\n5. Tap "Continue" below to start recording'
                  : 'To record audio from your Apple Watch, we need microphone permission.\n\nTap "Grant Permission" below to get started.',
              style: const TextStyle(
                fontSize: 16,
                color: Colors.white70,
                height: 1.5,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 40),

            // Action buttons
            if (!_permissionRequested) ...[
              // Grant Permission Button
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  onPressed: _isRequestingPermission ? null : _requestPermission,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.blue,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(25),
                    ),
                  ),
                  child: _isRequestingPermission
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                        )
                      : const Text(
                          'Grant Permission',
                          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                        ),
                ),
              ),
            ] else ...[
              // Continue Button (after permission was requested)
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  onPressed: _continueAndStartRecording,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.green,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(25),
                    ),
                  ),
                  child: const Text(
                    'Continue',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Need Help Button
              TextButton(
                onPressed: _showHelpDialog,
                child: const Text(
                  'Need Help?',
                  style: TextStyle(color: Colors.white70),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _requestPermission() async {
    setState(() {
      _isRequestingPermission = true;
    });

    try {
      // Request permission - this will cause the watch app to close
      await widget.connection.requestPermissionAndStartRecording();

      setState(() {
        _isRequestingPermission = false;
        _permissionRequested = true;
      });

      AppSnackbar.showSnackbar(
        'Permission request sent to your Apple Watch. Check your watch for the popup.',
        duration: const Duration(seconds: 3),
      );
    } catch (e) {
      setState(() {
        _isRequestingPermission = false;
      });

      AppSnackbar.showSnackbar(
        'Error requesting permission: $e',
        duration: const Duration(seconds: 3),
      );
    }
  }

  Future<void> _continueAndStartRecording() async {
    try {
      // Check if permission was granted and start recording
      final bool recordingStarted = await widget.connection.checkPermissionAndStartRecording();

      if (recordingStarted) {
        AppSnackbar.showSnackbar(
          'Recording started successfully!',
          duration: const Duration(seconds: 3),
        );

        // Call the callback and close the page
        widget.onPermissionGranted?.call();
        Navigator.of(context).pop();
      } else {
        AppSnackbar.showSnackbar(
          'Permission not granted yet. Please make sure you allowed microphone access on your watch and reopened the app.',
          duration: const Duration(seconds: 5),
        );
      }
    } catch (e) {
      AppSnackbar.showSnackbar(
        'Error starting recording: $e',
        duration: const Duration(seconds: 3),
      );
    }
  }

  void _showHelpDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: Colors.grey[900],
        title: const Text(
          'Need Help?',
          style: TextStyle(color: Colors.white),
        ),
        content: const Text(
          'If you\'re having trouble:\n\n'
          '1. Make sure the Omi app is installed on your Apple Watch\n'
          '2. Open the Omi app on your watch\n'
          '3. Look for the microphone permission popup\n'
          '4. Tap "Allow" when prompted\n'
          '5. The app will close - this is normal\n'
          '6. Open the Omi app on your watch again\n'
          '7. Come back and tap "Continue"',
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

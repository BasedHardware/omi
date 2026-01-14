import 'package:flutter/material.dart';

import 'package:url_launcher/url_launcher.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/gen/flutter_communicator.g.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

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
  bool? _isAppInstalled;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _checkAppInstallationStatus();
  }

  Future<void> _checkAppInstallationStatus() async {
    try {
      final hostAPI = WatchRecorderHostAPI();
      final bool isInstalled = await hostAPI.isWatchAppInstalled();

      if (mounted) {
        setState(() {
          _isAppInstalled = isInstalled;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isAppInstalled = false;
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return Container(
      decoration: const BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary,
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(24),
          topRight: Radius.circular(24),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Handle bar
          Container(
            margin: const EdgeInsets.only(top: 12),
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: ResponsiveHelper.textTertiary,
              borderRadius: BorderRadius.circular(2),
            ),
          ),

          // Main content
          Padding(
            padding: const EdgeInsets.all(32.0),
            child: Column(
              children: [
                // Apple Watch image
                AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  height: 120,
                  width: 120,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: responsive.mediumShadow,
                  ),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(20),
                    child: Image.asset(
                      Assets.images.appleWatch.path,
                      fit: BoxFit.cover,
                    ),
                  ),
                ),
                const SizedBox(height: 32),

                if (_isLoading) ...[
                  Text(
                    'Checking Apple Watch...',
                    style: responsive.titleLarge,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  const CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
                    strokeWidth: 2,
                  ),
                ] else if (_isAppInstalled == false) ...[
                  // App not installed
                  Text(
                    'Install Omi on your\nApple Watch',
                    style: responsive.titleLarge.copyWith(height: 1.2),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'To use your Apple Watch with Omi, you need to install the Omi app on your watch first.',
                    style: responsive.bodyLarge,
                    textAlign: TextAlign.center,
                  ),
                ] else ...[
                  // App installed but not reachable (not open)
                  Text(
                    'Open Omi on your\nApple Watch',
                    style: responsive.titleLarge.copyWith(height: 1.2),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'The Omi app is installed on your Apple Watch. Open it and tap Start to begin.',
                    style: responsive.bodyLarge,
                    textAlign: TextAlign.center,
                  ),
                ],

                const SizedBox(height: 32),

                // Action buttons
                Row(
                  children: [
                    Expanded(
                      flex: 2,
                      child: ElevatedButton(
                        onPressed: _isChecking ? null : _handlePrimaryAction,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: ResponsiveHelper.purplePrimary,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          elevation: 0,
                        ),
                        child: _isChecking
                            ? const SizedBox(
                                height: 20,
                                width: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                ),
                              )
                            : Text(
                                _getPrimaryButtonText(),
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                  fontSize: 16,
                                ),
                              ),
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 20),
                InkWell(
                  onTap: () => Navigator.of(context).pop(),
                  child: const Text(
                    'Cancel',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                ),

                SizedBox(height: MediaQuery.of(context).padding.bottom + 16),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _getPrimaryButtonText() {
    if (_isAppInstalled == false) {
      return 'Open Watch App';
    } else {
      return 'I\'ve Installed & Opened the App';
    }
  }

  Future<void> _handlePrimaryAction() async {
    if (_isAppInstalled == false) {
      await _launchWatchApp();
    } else {
      await _checkConnection();
    }
  }

  Future<void> _launchWatchApp() async {
    try {
      final url = Uri.parse("itms-watchs://");

      if (await canLaunchUrl(url)) {
        await launchUrl(url);

        Navigator.of(context).pop();
      }
    } catch (e) {
      AppSnackbar.showSnackbar(
        'Unable to open Apple Watch app. Please manually open the Watch app on your Apple Watch and install Omi from the "Available Apps" section.',
        duration: const Duration(seconds: 6),
      );

      Navigator.of(context).pop();
    }
  }

  Future<void> _checkConnection() async {
    setState(() {
      _isChecking = true;
    });

    try {
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
}

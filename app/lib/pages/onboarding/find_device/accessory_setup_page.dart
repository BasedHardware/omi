import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/services/accessory_setup_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/widgets/dialog.dart';

class AccessorySetupPage extends StatefulWidget {
  final bool isFromOnboarding;
  final VoidCallback goNext;
  final VoidCallback? onSkip;
  final bool includeSkip;

  const AccessorySetupPage({
    super.key,
    required this.goNext,
    this.includeSkip = true,
    this.isFromOnboarding = false,
    this.onSkip,
  });

  @override
  State<AccessorySetupPage> createState() => _AccessorySetupPageState();
}

class _AccessorySetupPageState extends State<AccessorySetupPage> {
  bool _isAccessorySetupKitAvailable = false;
  bool _isConnecting = false;
  bool _isConnected = false;
  String? _connectedDeviceName;
  StreamSubscription<AccessoryEvent>? _eventSubscription;

  @override
  void initState() {
    super.initState();
    _initializeAccessorySetup();
  }

  @override
  void dispose() {
    _eventSubscription?.cancel();
    super.dispose();
  }

  Future<void> _initializeAccessorySetup() async {
    if (!Platform.isIOS) return;

    try {
      AccessorySetupService.instance.initialize();
      final isAvailable = await AccessorySetupService.instance.isAccessorySetupKitAvailable();

      setState(() {
        _isAccessorySetupKitAvailable = isAvailable;
      });

      if (isAvailable) {
        _subscribeToAccessoryEvents();
        _checkExistingAccessories();
      }
    } catch (e) {
      debugPrint('Error initializing AccessorySetupKit: $e');
    }
  }

  void _subscribeToAccessoryEvents() {
    _eventSubscription = AccessorySetupService.eventStream.listen((event) {
      switch (event.type) {
        case AccessoryEventTypes.accessoryAdded:
          setState(() {
            _isConnected = true;
            _isConnecting = false;
            _connectedDeviceName = event.data['displayName'] as String?;
          });

          HapticFeedback.heavyImpact();
          MixpanelManager().deviceConnected();

          // Auto-proceed after successful connection
          Future.delayed(const Duration(seconds: 2), () {
            if (mounted) {
              widget.goNext();
            }
          });
          break;

        case AccessoryEventTypes.pickerDidPresent:
          setState(() {
            _isConnecting = true;
          });
          break;

        case AccessoryEventTypes.pickerDidDismiss:
          setState(() {
            _isConnecting = false;
          });
          break;

        case AccessoryEventTypes.accessoryRemoved:
          setState(() {
            _isConnected = false;
            _connectedDeviceName = null;
          });
          break;
      }
    });
  }

  Future<void> _checkExistingAccessories() async {
    try {
      final accessories = await AccessorySetupService.instance.getConnectedAccessories();
      if (accessories.isNotEmpty) {
        setState(() {
          _isConnected = true;
          _connectedDeviceName = accessories.first.displayName;
        });
      }
    } catch (e) {
      debugPrint('Error checking existing accessories: $e');
    }
  }

  Future<void> _showAccessoryPicker() async {
    if (!_isAccessorySetupKitAvailable) {
      _showFallbackDialog();
      return;
    }

    try {
      setState(() {
        _isConnecting = true;
      });

      await AccessorySetupService.instance.showAccessoryPicker();
    } catch (e) {
      setState(() {
        _isConnecting = false;
      });

      if (mounted) {
        _showErrorDialog(e.toString());
      }
    }
  }

  void _showFallbackDialog() {
    showDialog(
      context: context,
      builder: (context) => getDialog(
        context,
        () => Navigator.of(context).pop(),
        () => Navigator.of(context).pop(),
        'Update Required',
        'To use the improved device setup experience, please update to iOS 18 or later. You can still connect your device using the manual setup.',
        singleButton: true,
        okButtonText: 'Continue',
      ),
    );
  }

  void _showErrorDialog(String error) {
    showDialog(
      context: context,
      builder: (context) => getDialog(
        context,
        () => Navigator.of(context).pop(),
        () => Navigator.of(context).pop(),
        'Connection Error',
        'Failed to connect to your Omi device. Please try again.\n\nError: $error',
        singleButton: true,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // Status text
        Text(
          _isConnected
              ? 'DEVICE CONNECTED'
              : _isConnecting
                  ? 'CONNECTING...'
                  : 'READY TO CONNECT',
          style: const TextStyle(
            fontWeight: FontWeight.w400,
            fontSize: 14,
            color: Color(0x66FFFFFF),
          ),
        ),

        const SizedBox(height: 24),

        // Connected device info or connection button
        if (_isConnected) ...[
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 24),
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: Colors.green.withOpacity(0.1),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: Colors.green.withOpacity(0.3)),
            ),
            child: Column(
              children: [
                const Icon(
                  Icons.check_circle,
                  color: Colors.green,
                  size: 48,
                ),
                const SizedBox(height: 16),
                Text(
                  _connectedDeviceName ?? 'Omi Device',
                  style: const TextStyle(
                    fontWeight: FontWeight.w500,
                    fontSize: 18,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Successfully Connected',
                  style: TextStyle(
                    fontWeight: FontWeight.w400,
                    fontSize: 14,
                    color: Color(0x99FFFFFF),
                  ),
                ),
              ],
            ),
          ),
        ] else ...[
          // Connection button
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 24),
            child: Column(
              children: [
                // Main connect button
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: _isConnecting ? null : _showAccessoryPicker,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFFFF6B35),
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(28),
                      ),
                      elevation: 0,
                    ),
                    child: _isConnecting
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : const Text(
                            'Connect Your Omi',
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              fontSize: 16,
                            ),
                          ),
                  ),
                ),

                const SizedBox(height: 16),

                // Helper text
                Text(
                  _isAccessorySetupKitAvailable
                      ? 'Tap to connect using the Apple standard setup experience'
                      : 'Make sure your Omi device is powered on and nearby',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontWeight: FontWeight.w400,
                    fontSize: 14,
                    color: Color(0x99FFFFFF),
                  ),
                ),
              ],
            ),
          ),
        ],

        const SizedBox(height: 48),

        // Skip button (if enabled and no device connected)
        if (widget.includeSkip && !_isConnected) ...[
          ElevatedButton(
            onPressed: () {
              if (widget.isFromOnboarding) {
                widget.onSkip?.call();
              } else {
                widget.goNext();
              }
              MixpanelManager().useWithoutDeviceOnboardingFindDevices();
            },
            child: Container(
              width: double.infinity,
              height: 45,
              alignment: Alignment.center,
              child: const Text(
                'Connect Later',
                style: TextStyle(
                  fontWeight: FontWeight.w400,
                  fontSize: 16,
                  color: Colors.white,
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

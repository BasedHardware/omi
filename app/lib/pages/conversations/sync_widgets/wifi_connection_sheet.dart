import 'package:flutter/material.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

/// Represents the current step of WiFi connection process
enum WifiConnectionStep {
  enablingWifi,
  connectingToDevice,
  connected,
  failed,
}

/// Shows a bottom sheet displaying WiFi connection progress
class WifiConnectionSheet extends StatefulWidget {
  final String deviceName;
  final VoidCallback? onCancel;

  const WifiConnectionSheet({
    super.key,
    this.deviceName = 'Omi',
    this.onCancel,
  });

  /// Shows the WiFi connection sheet and returns a controller to update progress
  static Future<WifiConnectionSheetController> show(
    BuildContext context, {
    String deviceName = 'Omi',
    VoidCallback? onCancel,
    VoidCallback? onRetry,
  }) async {
    final controller = WifiConnectionSheetController();

    showModalBottomSheet(
      context: context,
      isDismissible: false,
      enableDrag: false,
      backgroundColor: Colors.transparent,
      builder: (context) => _WifiConnectionSheetContent(
        deviceName: deviceName,
        controller: controller,
        onCancel: () {
          onCancel?.call();
          Navigator.of(context).pop();
        },
        onRetry: onRetry != null
            ? () {
                controller.reset();
                onRetry();
              }
            : null,
      ),
    );

    return controller;
  }

  @override
  State<WifiConnectionSheet> createState() => _WifiConnectionSheetState();
}

class _WifiConnectionSheetState extends State<WifiConnectionSheet> {
  @override
  Widget build(BuildContext context) {
    return const SizedBox.shrink();
  }
}

/// Controller to update the WiFi connection sheet progress
class WifiConnectionSheetController extends ChangeNotifier {
  WifiConnectionStep _currentStep = WifiConnectionStep.enablingWifi;
  String? _errorMessage;

  WifiConnectionStep get currentStep => _currentStep;
  String? get errorMessage => _errorMessage;

  void setStep(WifiConnectionStep step) {
    _currentStep = step;
    _errorMessage = null;
    notifyListeners();
  }

  void setError(String message) {
    _currentStep = WifiConnectionStep.failed;
    _errorMessage = message;
    notifyListeners();
  }

  void setConnected() {
    _currentStep = WifiConnectionStep.connected;
    _errorMessage = null;
    notifyListeners();
  }

  void reset() {
    _currentStep = WifiConnectionStep.enablingWifi;
    _errorMessage = null;
    notifyListeners();
  }
}

class _WifiConnectionSheetContent extends StatefulWidget {
  final String deviceName;
  final WifiConnectionSheetController controller;
  final VoidCallback onCancel;
  final VoidCallback? onRetry;

  const _WifiConnectionSheetContent({
    required this.deviceName,
    required this.controller,
    required this.onCancel,
    this.onRetry,
  });

  @override
  State<_WifiConnectionSheetContent> createState() => _WifiConnectionSheetContentState();
}

class _WifiConnectionSheetContentState extends State<_WifiConnectionSheetContent> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onControllerUpdate);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onControllerUpdate);
    super.dispose();
  }

  void _onControllerUpdate() {
    if (mounted) {
      setState(() {});

      // Auto-dismiss on success after a brief delay
      if (widget.controller.currentStep == WifiConnectionStep.connected) {
        Future.delayed(const Duration(milliseconds: 800), () {
          if (mounted) {
            Navigator.of(context).pop();
          }
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final step = widget.controller.currentStep;
    final isFailed = step == WifiConnectionStep.failed;

    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1C1C1E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Handle bar
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey.shade700,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 20),
              // Title row
              Row(
                children: [
                  Expanded(
                    child: Text(
                      isFailed ? 'Connection Failed' : 'Connecting to ${widget.deviceName}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  if (isFailed || step != WifiConnectionStep.connected)
                    GestureDetector(
                      onTap: widget.onCancel,
                      child: Container(
                        width: 32,
                        height: 32,
                        decoration: BoxDecoration(
                          color: const Color(0xFF2A2A2E),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: const Icon(Icons.close, color: Colors.white, size: 18),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 24),
              // Step 1: Enabling WiFi
              _buildStepRow(
                icon: Icons.wifi_tethering,
                title: 'Enable ${widget.deviceName}\'s WiFi',
                isActive: step == WifiConnectionStep.enablingWifi,
                isCompleted: step.index > WifiConnectionStep.enablingWifi.index && !isFailed,
                isFailed: isFailed &&
                    step == WifiConnectionStep.failed &&
                    widget.controller.currentStep == WifiConnectionStep.enablingWifi,
              ),
              const SizedBox(height: 16),
              // Step 2: Connecting to device
              _buildStepRow(
                icon: Icons.wifi,
                title: 'Connect to ${widget.deviceName}',
                isActive: step == WifiConnectionStep.connectingToDevice,
                isCompleted: step == WifiConnectionStep.connected,
                isFailed: isFailed && widget.controller.currentStep == WifiConnectionStep.connectingToDevice,
              ),
              // Error message
              if (isFailed && widget.controller.errorMessage != null) ...[
                const SizedBox(height: 20),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.red.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline, color: Colors.red, size: 20),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          widget.controller.errorMessage!,
                          style: TextStyle(color: Colors.red.shade300, fontSize: 13),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              // Retry button (only shown when failed)
              if (isFailed && widget.onRetry != null) ...[
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: widget.onRetry,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.blue,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.refresh, size: 20),
                        SizedBox(width: 8),
                        Text(
                          'Retry',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStepRow({
    required IconData icon,
    required String title,
    required bool isActive,
    required bool isCompleted,
    required bool isFailed,
  }) {
    Color iconBgColor;
    Color iconColor;
    Widget statusWidget;

    if (isCompleted) {
      iconBgColor = Colors.green.withOpacity(0.2);
      iconColor = Colors.green;
      statusWidget = const Icon(Icons.check_circle, color: Colors.green, size: 24);
    } else if (isFailed) {
      iconBgColor = Colors.red.withOpacity(0.2);
      iconColor = Colors.red;
      statusWidget = const Icon(Icons.error, color: Colors.red, size: 24);
    } else if (isActive) {
      iconBgColor = Colors.blue.withOpacity(0.2);
      iconColor = Colors.blue;
      statusWidget = const SizedBox(
        width: 24,
        height: 24,
        child: CircularProgressIndicator(
          strokeWidth: 2.5,
          color: Colors.blue,
        ),
      );
    } else {
      iconBgColor = const Color(0xFF2A2A2E);
      iconColor = Colors.grey.shade600;
      statusWidget = Icon(Icons.circle_outlined, color: Colors.grey.shade600, size: 24);
    }

    return Row(
      children: [
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: iconBgColor,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(icon, color: iconColor, size: 22),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Text(
            title,
            style: TextStyle(
              color: isActive || isCompleted ? Colors.white : Colors.grey.shade500,
              fontSize: 16,
              fontWeight: isActive ? FontWeight.w500 : FontWeight.w400,
            ),
          ),
        ),
        statusWidget,
      ],
    );
  }
}

/// Bridge class that implements IWifiConnectionListener and updates the sheet controller
class WifiConnectionListenerBridge implements IWifiConnectionListener {
  final WifiConnectionSheetController controller;

  WifiConnectionListenerBridge(this.controller);

  @override
  void onEnablingDeviceWifi() {
    controller.setStep(WifiConnectionStep.enablingWifi);
  }

  @override
  void onConnectingToDevice() {
    controller.setStep(WifiConnectionStep.connectingToDevice);
  }

  @override
  void onConnected() {
    controller.setConnected();
  }

  @override
  void onConnectionFailed(String error) {
    controller.setError(error);
  }
}

import 'package:flutter/material.dart';

class FirmwareUpdateStep {
  final String title;
  final String description;
  final IconData icon;
  final bool isLastStep;

  FirmwareUpdateStep({
    required this.title,
    required this.description,
    required this.icon,
    this.isLastStep = false,
  });
}

class FirmwareUpdateDialog extends StatefulWidget {
  final Function() onUpdateStart;
  final List<String> steps;

  const FirmwareUpdateDialog({
    super.key,
    required this.onUpdateStart,
    required this.steps,
  });

  @override
  State<FirmwareUpdateDialog> createState() => _FirmwareUpdateDialogState();
}

class _FirmwareUpdateDialogState extends State<FirmwareUpdateDialog> {
  late final List<FirmwareUpdateStep> updateSteps;
  bool hasUsbStep = false;
  bool isConfirmed = false;

  @override
  void initState() {
    super.initState();

    // Map API steps to UI steps
    final stepMap = {
      'no_usb': FirmwareUpdateStep(
        title: 'No USB',
        description:
            "Disconnect your Omi device from any USB connection. USB connection during updates may damage your device.",
        icon: Icons.usb_off,
      ),
      'battery': FirmwareUpdateStep(
        title: 'Battery > 15%',
        description: "Ensure your Omi device has at least 15% battery remaining for a safe update.",
        icon: Icons.battery_5_bar,
      ),
      'internet': FirmwareUpdateStep(
        title: 'Stable Internet',
        description: 'Connect to a stable WiFi or cellular network for reliable firmware download.',
        icon: Icons.wifi,
      ),
    };

    updateSteps = widget.steps.map((step) => stepMap[step]!).toList();
    hasUsbStep = widget.steps.contains('no_usb');
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        constraints: const BoxConstraints(
          maxHeight: 500,
        ),
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Update Requirements',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 24),
              // Scrollable area for steps
              Flexible(
                child: SingleChildScrollView(
                  child: Column(
                    children: updateSteps.map((step) => _buildStepItem(step)).toList(),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              // Confirmation checkbox
              Row(
                children: [
                  Theme(
                    data: Theme.of(context).copyWith(
                      checkboxTheme: CheckboxThemeData(
                        fillColor: MaterialStateProperty.resolveWith<Color>(
                          (Set<MaterialState> states) {
                            if (states.contains(MaterialState.selected)) {
                              return Colors.deepPurple;
                            }
                            return Colors.grey.shade700;
                          },
                        ),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                    child: Checkbox(
                      value: isConfirmed,
                      onChanged: (value) {
                        setState(() {
                          isConfirmed = value ?? false;
                        });
                      },
                    ),
                  ),
                  Expanded(
                    child: Text(
                      hasUsbStep
                          ? "I've disconnected USB and understand the risks."
                          : "I confirm I want to update my device firmware.",
                      style: TextStyle(
                        color: Colors.grey.shade300,
                        fontSize: 14,
                        height: 1.5,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              // Update button (disabled until confirmed)
              TextButton(
                onPressed: isConfirmed
                    ? () {
                        Navigator.of(context).pop();
                        try {
                          widget.onUpdateStart();
                        } catch (e) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text('Failed to start update: $e'),
                              backgroundColor: Colors.red,
                            ),
                          );
                        }
                      }
                    : null,
                style: TextButton.styleFrom(
                  foregroundColor: Colors.white,
                  backgroundColor: isConfirmed ? Colors.deepPurple : Colors.grey.shade800,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                  minimumSize: const Size(double.infinity, 0),
                ),
                child: const Text(
                  'Start Update',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStepItem(FirmwareUpdateStep step) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ShaderMask(
            shaderCallback: (Rect bounds) {
              return const LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Color(0xFFE8EAED),
                  Color(0xFF848587),
                ],
              ).createShader(bounds);
            },
            child: Icon(
              step.icon,
              size: 32,
              color: Colors.white,
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  step.title,
                  style: const TextStyle(
                    fontSize: 16,
                    color: Colors.white,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  step.description,
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.grey.shade300,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

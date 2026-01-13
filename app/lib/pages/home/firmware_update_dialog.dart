import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

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

/// Shows the firmware update bottom sheet
void showFirmwareUpdateSheet({
  required BuildContext context,
  required List<String> steps,
  required Function() onUpdateStart,
}) {
  showModalBottomSheet(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (context) => FirmwareUpdateSheet(
      steps: steps,
      onUpdateStart: onUpdateStart,
    ),
  );
}

class FirmwareUpdateSheet extends StatefulWidget {
  final Function() onUpdateStart;
  final List<String> steps;

  const FirmwareUpdateSheet({
    super.key,
    required this.onUpdateStart,
    required this.steps,
  });

  @override
  State<FirmwareUpdateSheet> createState() => _FirmwareUpdateSheetState();
}

class _FirmwareUpdateSheetState extends State<FirmwareUpdateSheet> {
  late final List<FirmwareUpdateStep> updateSteps;
  bool hasUsbStep = false;

  @override
  void initState() {
    super.initState();

    final stepMap = {
      'no_usb': FirmwareUpdateStep(
        title: 'Disconnect USB',
        description: 'USB connection during updates may damage your device.',
        icon: FontAwesomeIcons.plug,
      ),
      'battery': FirmwareUpdateStep(
        title: 'Battery Above 15%',
        description: 'Ensure your device has 15% battery.',
        icon: FontAwesomeIcons.batteryHalf,
      ),
      'internet': FirmwareUpdateStep(
        title: 'Stable Connection',
        description: 'Connect to WiFi or cellular.',
        icon: FontAwesomeIcons.wifi,
      ),
    };

    updateSteps = widget.steps.map((step) => stepMap[step]!).toList();
    hasUsbStep = widget.steps.contains('no_usb');
  }

  void _onConfirmed() {
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

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1C1C1E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Drag handle
            Container(
              margin: const EdgeInsets.only(top: 12),
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.grey.shade600,
                borderRadius: BorderRadius.circular(2),
              ),
            ),

            // Header
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const FaIcon(
                    FontAwesomeIcons.circleExclamation,
                    color: Color(0xFFFFB800),
                    size: 20,
                  ),
                  const SizedBox(width: 10),
                  const Text(
                    'Before Update, Make Sure:',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // Steps list
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                children: updateSteps.map((step) => _buildStepItem(step)).toList(),
              ),
            ),

            // Footer with swipe to confirm
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
              child: SwipeToConfirm(
                onConfirmed: _onConfirmed,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStepItem(FirmwareUpdateStep step) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF2A2A2E),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: const Color(0xFF1C1C1E),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Center(
                child: FaIcon(
                  step.icon,
                  size: 18,
                  color: Colors.white,
                ),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    step.title,
                    style: const TextStyle(
                      fontSize: 15,
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    step.description,
                    style: TextStyle(
                      fontSize: 13,
                      color: Colors.grey.shade400,
                      height: 1.3,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class SwipeToConfirm extends StatefulWidget {
  final VoidCallback onConfirmed;

  const SwipeToConfirm({
    super.key,
    required this.onConfirmed,
  });

  @override
  State<SwipeToConfirm> createState() => _SwipeToConfirmState();
}

class _SwipeToConfirmState extends State<SwipeToConfirm> with SingleTickerProviderStateMixin {
  double _dragPosition = 0;
  bool _isDragging = false;
  bool _isConfirmed = false;
  late AnimationController _animationController;
  late Animation<double> _animation;

  static const double _buttonSize = 52;
  static const double _trackHeight = 60;
  static const double _horizontalPadding = 4;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );
    _animation = Tween<double>(begin: 0, end: 0).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeOut),
    );
    _animationController.addListener(() {
      setState(() {
        _dragPosition = _animation.value;
      });
    });
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final maxDragDistance = constraints.maxWidth - _buttonSize - (_horizontalPadding * 2);
        final progress = maxDragDistance > 0 ? (_dragPosition / maxDragDistance).clamp(0.0, 1.0) : 0.0;

        return Container(
          height: _trackHeight,
          decoration: BoxDecoration(
            color: _isConfirmed ? const Color(0xFF22C55E) : const Color(0xFF2A2A2E),
            borderRadius: BorderRadius.circular(_trackHeight / 2),
          ),
          child: Stack(
            children: [
              // Green fill progress
              if (!_isConfirmed)
                Positioned(
                  left: 0,
                  top: 0,
                  bottom: 0,
                  child: Container(
                    width: _dragPosition + _buttonSize + _horizontalPadding,
                    decoration: BoxDecoration(
                      color: Color.lerp(
                        const Color(0xFF2A2A2E),
                        const Color(0xFF22C55E),
                        progress,
                      ),
                      borderRadius: BorderRadius.circular(_trackHeight / 2),
                    ),
                  ),
                ),
              // Center text
              Center(
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 150),
                  child: _isConfirmed
                      ? Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          key: const ValueKey('confirmed'),
                          children: [
                            const Text(
                              'Confirmed!',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              width: 24,
                              height: 24,
                              decoration: BoxDecoration(
                                color: Colors.white.withOpacity(0.2),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: const Icon(
                                Icons.check,
                                color: Colors.white,
                                size: 16,
                              ),
                            ),
                          ],
                        )
                      : _isDragging && progress > 0.3
                          ? Text(
                              'Release',
                              key: const ValueKey('release'),
                              style: TextStyle(
                                color: Colors.grey.shade400,
                                fontSize: 16,
                                fontWeight: FontWeight.w500,
                              ),
                            )
                          : Text(
                              'Slide to Update',
                              key: const ValueKey('slide'),
                              style: TextStyle(
                                color: Colors.grey.shade400,
                                fontSize: 16,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                ),
              ),
              // Draggable button
              if (!_isConfirmed)
                Positioned(
                  left: _horizontalPadding + _dragPosition,
                  top: (_trackHeight - _buttonSize) / 2,
                  child: GestureDetector(
                    onHorizontalDragStart: (_) {
                      setState(() {
                        _isDragging = true;
                      });
                    },
                    onHorizontalDragUpdate: (details) {
                      if (_isConfirmed) return;
                      final newPosition = (_dragPosition + details.delta.dx).clamp(0.0, maxDragDistance);
                      setState(() {
                        _dragPosition = newPosition;
                      });
                    },
                    onHorizontalDragEnd: (details) {
                      if (_isConfirmed) return;

                      final threshold = maxDragDistance * 0.85;

                      if (_dragPosition >= threshold) {
                        setState(() {
                          _isConfirmed = true;
                          _dragPosition = maxDragDistance;
                        });
                        Future.delayed(const Duration(milliseconds: 200), () {
                          widget.onConfirmed();
                        });
                      } else {
                        _animation = Tween<double>(begin: _dragPosition, end: 0).animate(
                          CurvedAnimation(parent: _animationController, curve: Curves.easeOut),
                        );
                        _animationController.forward(from: 0);
                      }

                      setState(() {
                        _isDragging = false;
                      });
                    },
                    child: Container(
                      width: _buttonSize,
                      height: _buttonSize,
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(_buttonSize / 2),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.2),
                            blurRadius: 8,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: const Center(
                        child: FaIcon(
                          FontAwesomeIcons.chevronRight,
                          color: Color(0xFF2A2A2E),
                          size: 18,
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

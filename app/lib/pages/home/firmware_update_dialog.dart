import 'package:flutter/material.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

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
    Key? key,
    required this.onUpdateStart,
    required this.steps,
  }) : super(key: key);

  @override
  State<FirmwareUpdateDialog> createState() => _FirmwareUpdateDialogState();
}

class _FirmwareUpdateDialogState extends State<FirmwareUpdateDialog> {
  final PageController _pageController = PageController();
  int _currentPage = 0;

  late final List<FirmwareUpdateStep> updateSteps;

  @override
  void initState() {
    super.initState();

    // Map API steps to UI steps
    final stepMap = {
      'no_usb': FirmwareUpdateStep(
        title: 'No USB',
        description: 'Unplug your Omi device from the USB, either from a charger or a computer.',
        icon: Icons.usb_off,
      ),
      'battery': FirmwareUpdateStep(
        title: 'Battery > 15%',
        description: 'Ensure your Omi device\'s battery is above 15%.',
        icon: Icons.battery_5_bar,
      ),
      'internet': FirmwareUpdateStep(
        title: 'Stable Internet',
        description: 'Make sure your phone has a stable internet connection.',
        icon: Icons.wifi,
      ),
    };

    updateSteps = widget.steps.map((step) => stepMap[step]!).toList();
    // Mark last step
    if (updateSteps.isNotEmpty) {
      updateSteps.last = FirmwareUpdateStep(
        title: updateSteps.last.title,
        description: updateSteps.last.description,
        icon: updateSteps.last.icon,
        isLastStep: true,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        height: 450,
        decoration: BoxDecoration(
          color: const Color(0xFF1D1D1D),
          borderRadius: BorderRadius.circular(20),
        ),
        child: PageView.builder(
          controller: _pageController,
          itemCount: updateSteps.length,
          onPageChanged: (int page) {
            setState(() {
              _currentPage = page;
            });
          },
          itemBuilder: (context, index) {
            final step = updateSteps[index];
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 40),
              child: Column(
                mainAxisSize: MainAxisSize.max,
                children: [
                  Column(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: const BoxDecoration(
                          color: Colors.white60,
                          shape: BoxShape.circle,
                        ),
                        child: Text(
                          '${_currentPage + 1}',
                          style: const TextStyle(
                            color: Color(0xFF1D1D1D),
                            fontWeight: FontWeight.bold,
                            fontSize: 14,
                          ),
                        ),
                      ),
                      const SizedBox(height: 40),
                      Text(
                        step.title,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 24,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 40),
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
                          size: 54,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 40),
                      Text(
                        step.description,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          color: Color(0xFFAAAAAA),
                          fontSize: 14,
                          height: 1.5,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 40),
                  Expanded(
                    child: Row(
                      mainAxisSize: MainAxisSize.max,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Container(
                          decoration: updateSteps[_currentPage].isLastStep
                              ? BoxDecoration(
                                  border: const GradientBoxBorder(
                                    gradient: LinearGradient(
                                      colors: [
                                        Color.fromARGB(127, 208, 208, 208),
                                        Color.fromARGB(127, 188, 99, 121),
                                        Color.fromARGB(127, 86, 101, 182),
                                        Color.fromARGB(127, 126, 190, 236)
                                      ],
                                    ),
                                  ),
                                  borderRadius: BorderRadius.circular(12),
                                )
                              : null,
                          child: TextButton(
                            style: TextButton.styleFrom(
                              minimumSize: Size.zero,
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              padding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                            ),
                            onPressed: () {
                              if (_currentPage < updateSteps.length - 1) {
                                _pageController.nextPage(
                                  duration: const Duration(milliseconds: 300),
                                  curve: Curves.easeInOut,
                                );
                              } else {
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
                            },
                            // Add container with gradient for last step
                            child: Text(
                              updateSteps[_currentPage].isLastStep ? 'Start Update' : 'Next',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 16,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

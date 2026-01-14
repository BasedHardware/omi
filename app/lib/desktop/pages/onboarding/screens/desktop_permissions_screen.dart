import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/ui/atoms/omi_button.dart';
import 'package:omi/ui/molecules/omi_selectable_tile.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopPermissionsScreen extends StatefulWidget {
  final VoidCallback onNext;
  final VoidCallback onBack;

  const DesktopPermissionsScreen({
    super.key,
    required this.onNext,
    required this.onBack,
  });

  @override
  State<DesktopPermissionsScreen> createState() => _DesktopPermissionsScreenState();
}

class _DesktopPermissionsScreenState extends State<DesktopPermissionsScreen>
    with WidgetsBindingObserver, TickerProviderStateMixin {
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );

    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _fadeController,
      curve: Curves.easeOut,
    ));

    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = Provider.of<OnboardingProvider>(context, listen: false);
      provider.updatePermissions();
      _fadeController.forward();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _fadeController.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      final provider = Provider.of<OnboardingProvider>(context, listen: false);
      provider.updatePermissions();
    }
  }

  void _showPermissionDialog({
    required String title,
    required String description,
    required VoidCallback onContinue,
  }) {
    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1A1A1A),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text(
            title,
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
          ),
          content: Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              description,
              style: const TextStyle(
                fontSize: 14,
                color: Colors.grey,
                height: 1.4,
              ),
            ),
          ),
          actions: [
            TextButton(
              child: Text(
                'Cancel',
                style: TextStyle(
                  color: Colors.grey.shade500,
                  fontSize: 16,
                ),
              ),
              onPressed: () => Navigator.of(context).pop(),
            ),
            OmiButton(
              label: 'Continue',
              onPressed: () {
                Navigator.of(context).pop();
                onContinue();
              },
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<OnboardingProvider>(
      builder: (context, provider, child) {
        return SizedBox(
          width: double.infinity,
          height: double.infinity,
          child: SingleChildScrollView(
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: MediaQuery.of(context).size.height,
              ),
              child: IntrinsicHeight(
                child: Column(
                  children: [
                    FadeTransition(
                      opacity: _fadeAnimation,
                      child: Container(
                        padding: const EdgeInsets.only(
                          top: 40,
                          bottom: 32,
                        ),
                        child: Column(
                          children: [
                            Container(
                              width: 56,
                              height: 56,
                              decoration: BoxDecoration(
                                color: const Color(0xFF1A1A1A),
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: const Icon(
                                Icons.shield_rounded,
                                color: Colors.white,
                                size: 28,
                              ),
                            ),
                            const SizedBox(height: 24),
                            const Text(
                              'Grant permissions',
                              style: TextStyle(
                                fontSize: 28,
                                fontWeight: FontWeight.w600,
                                color: Colors.white,
                                letterSpacing: -0.5,
                              ),
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 8),
                            Container(
                              constraints: const BoxConstraints(maxWidth: 480),
                              padding: const EdgeInsets.symmetric(horizontal: 40),
                              child: const Text(
                                'Enable features for the best Omi experience on your device.',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w400,
                                  color: Color(0xFF9CA3AF),
                                  height: 1.5,
                                ),
                                textAlign: TextAlign.center,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    Flexible(
                      child: FadeTransition(
                        opacity: _fadeAnimation,
                        child: Container(
                          constraints: const BoxConstraints(maxWidth: 520),
                          margin: const EdgeInsets.symmetric(horizontal: 40),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              // Microphone Permission
                              OmiSelectableTile(
                                leading: Icon(Icons.mic_rounded,
                                    color: provider.hasMicrophonePermission
                                        ? ResponsiveHelper.purplePrimary
                                        : const Color(0xFF9CA3AF),
                                    size: 20),
                                title: 'Microphone Access',
                                subtitle: 'Record audio conversations',
                                selected: provider.hasMicrophonePermission,
                                onTap: () {
                                  if (!provider.hasMicrophonePermission) {
                                    _showPermissionDialog(
                                      title: 'Microphone Access',
                                      description:
                                          'Omi needs microphone access to record your conversations and provide transcriptions.',
                                      onContinue: () async {
                                        await provider.askForMicrophonePermissions();
                                      },
                                    );
                                  } else {
                                    provider.updateMicrophonePermission(false);
                                  }
                                },
                              ),

                              const SizedBox(height: 12),

                              // Screen Capture Permission
                              OmiSelectableTile(
                                leading: Icon(Icons.screen_share_rounded,
                                    color: provider.hasScreenCapturePermission
                                        ? ResponsiveHelper.purplePrimary
                                        : const Color(0xFF9CA3AF),
                                    size: 20),
                                title: 'Screen Recording',
                                subtitle: 'Capture system audio from meetings',
                                selected: provider.hasScreenCapturePermission,
                                onTap: () {
                                  if (!provider.hasScreenCapturePermission) {
                                    _showPermissionDialog(
                                      title: 'Screen Recording',
                                      description:
                                          'Omi needs screen recording permission to capture system audio from your browser-based meetings.',
                                      onContinue: () async {
                                        await provider.askForScreenCapturePermissions();
                                      },
                                    );
                                  } else {
                                    provider.updateScreenCapturePermission(false);
                                  }
                                },
                              ),

                              const SizedBox(height: 12),

                              // Accessibility Permission
                              OmiSelectableTile(
                                leading: Icon(Icons.accessibility_new_rounded,
                                    color: provider.hasAccessibilityPermission
                                        ? ResponsiveHelper.purplePrimary
                                        : const Color(0xFF9CA3AF),
                                    size: 20),
                                title: 'Accessibility',
                                subtitle: 'Detect browser-based meetings',
                                selected: provider.hasAccessibilityPermission,
                                onTap: () {
                                  if (!provider.hasAccessibilityPermission) {
                                    _showPermissionDialog(
                                      title: 'Accessibility',
                                      description:
                                          'Omi needs accessibility permission to detect when you join Zoom, Meet, or Teams meetings in your browser.',
                                      onContinue: () async {
                                        await provider.askForAccessibilityPermissions();
                                      },
                                    );
                                  } else {
                                    provider.updateAccessibilityPermission(false);
                                  }
                                },
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.fromLTRB(40, 24, 40, 40),
                      child: Column(
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              OmiButton(
                                label: provider.isLoading
                                    ? 'Please wait...'
                                    : (provider.hasMicrophonePermission ||
                                            provider.hasScreenCapturePermission ||
                                            provider.hasAccessibilityPermission)
                                        ? 'Continue'
                                        : 'Skip',
                                onPressed: provider.isLoading
                                    ? null
                                    : () {
                                        provider.setLoading(false);
                                        MixpanelManager().onboardingStepCompleted('Permissions');
                                        widget.onNext();
                                      },
                                enabled: !provider.isLoading,
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          OmiButton(
                            label: 'Back',
                            type: OmiButtonType.text,
                            onPressed: widget.onBack,
                          ),
                        ],
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
}

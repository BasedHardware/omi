import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:intercom_flutter/intercom_flutter.dart';

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

class _DesktopPermissionsScreenState extends State<DesktopPermissionsScreen> with WidgetsBindingObserver, TickerProviderStateMixin {
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

    // Initial permission check - same as permissions_desktop_widget.dart
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
      // Refresh permissions when user returns to the app
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
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: ResponsiveHelper.purplePrimary,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              child: const Text(
                'Continue',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                ),
              ),
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
        return Container(
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
                    // Header Section
                    FadeTransition(
                      opacity: _fadeAnimation,
                      child: Container(
                        padding: const EdgeInsets.only(
                          top: 40,
                          bottom: 32,
                        ),
                        child: Column(
                          children: [
                            // Simple minimal icon matching name and language pages
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

                            // Clean title
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

                            // Clean subtitle
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

                    // Permissions list - use flexible instead of expanded
                    Flexible(
                      child: FadeTransition(
                        opacity: _fadeAnimation,
                        child: Container(
                          constraints: const BoxConstraints(maxWidth: 520),
                          margin: const EdgeInsets.symmetric(horizontal: 40),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              // Bluetooth Permission
                              _buildCleanPermissionItem(
                                icon: Icons.bluetooth_rounded,
                                title: 'Bluetooth Access',
                                subtitle: 'Connect to your Omi device',
                                value: provider.hasBluetoothPermission,
                                onTap: () {
                                  if (!provider.hasBluetoothPermission) {
                                    _showPermissionDialog(
                                      title: 'Bluetooth Access',
                                      description: 'This app uses Bluetooth to connect and communicate with your device. Your device data stays private and secure.',
                                      onContinue: () async {
                                        await provider.askForBluetoothPermissions();
                                      },
                                    );
                                  } else {
                                    provider.updateBluetoothPermission(false);
                                  }
                                },
                              ),

                              const SizedBox(height: 12),

                              // Location Permission
                              _buildCleanPermissionItem(
                                icon: Icons.location_on_rounded,
                                title: 'Location Services',
                                subtitle: 'Tag conversations with location',
                                value: provider.hasLocationPermission,
                                onTap: () {
                                  if (!provider.hasLocationPermission) {
                                    _showPermissionDialog(
                                      title: 'Location Services',
                                      description: 'This app may use your location to tag your conversations and improve your experience.',
                                      onContinue: () async {
                                        await provider.askForLocationPermissions();
                                      },
                                    );
                                  } else {
                                    provider.updateLocationPermission(false);
                                  }
                                },
                              ),

                              const SizedBox(height: 12),

                              // Notification Permission
                              _buildCleanPermissionItem(
                                icon: Icons.notifications_rounded,
                                title: 'Notifications',
                                subtitle: 'Receive important updates',
                                value: provider.hasNotificationPermission,
                                onTap: () {
                                  if (!provider.hasNotificationPermission) {
                                    _showPermissionDialog(
                                      title: 'Notifications',
                                      description: 'This app would like to send you notifications to keep you informed about important updates and activities.',
                                      onContinue: () async {
                                        await provider.askForNotificationPermissions();
                                      },
                                    );
                                  } else {
                                    provider.updateNotificationPermission(false);
                                  }
                                },
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),

                    // Clean minimal navigation - reduced padding and responsive
                    Container(
                      padding: const EdgeInsets.fromLTRB(40, 24, 40, 40),
                      child: Column(
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              // Premium continue button
                              Container(
                                height: 44,
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(
                                    colors: [
                                      ResponsiveHelper.purplePrimary,
                                      ResponsiveHelper.purplePrimary.withOpacity(0.8),
                                    ],
                                  ),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: ElevatedButton.icon(
                                  onPressed: provider.isLoading
                                      ? null
                                      : () {
                                          provider.setLoading(false);
                                          widget.onNext();
                                        },
                                  icon: provider.isLoading
                                      ? const SizedBox(
                                          width: 16,
                                          height: 16,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                          ),
                                        )
                                      : null,
                                  label: Text(provider.isLoading
                                      ? 'Please wait...'
                                      : (provider.hasBluetoothPermission || provider.hasLocationPermission || provider.hasNotificationPermission)
                                          ? 'Continue'
                                          : 'Skip'),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: Colors.transparent,
                                    foregroundColor: Colors.white,
                                    shadowColor: Colors.transparent,
                                    padding: const EdgeInsets.symmetric(horizontal: 24),
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    textStyle: const TextStyle(
                                      fontSize: 15,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),

                          const SizedBox(height: 8),

                          // Small back button
                          TextButton(
                            onPressed: widget.onBack,
                            child: const Text(
                              'Back',
                              style: TextStyle(
                                color: Color(0xFF6B7280),
                                fontSize: 13,
                                fontWeight: FontWeight.w400,
                              ),
                            ),
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

  Widget _buildCleanPermissionItem({
    required IconData icon,
    required String title,
    required String subtitle,
    required bool value,
    required VoidCallback onTap,
  }) {
    return Material(
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: 20,
            vertical: 16,
          ),
          decoration: BoxDecoration(
            color: const Color(0xFF1A1A1A),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: value ? ResponsiveHelper.purplePrimary.withOpacity(0.5) : const Color(0xFF2A2A2A),
              width: 1,
            ),
          ),
          child: Row(
            children: [
              // Icon
              Container(
                width: 24,
                height: 24,
                child: Icon(
                  icon,
                  color: value ? ResponsiveHelper.purplePrimary : const Color(0xFF9CA3AF),
                  size: 20,
                ),
              ),

              const SizedBox(width: 16),

              // Text content
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        color: value ? Colors.white : const Color(0xFFE5E7EB),
                        fontSize: 15,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: const TextStyle(
                        color: Color(0xFF9CA3AF),
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(width: 16),

              // Radio button
              Container(
                width: 20,
                height: 20,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: value ? ResponsiveHelper.purplePrimary : const Color(0xFF6B7280),
                    width: 2,
                  ),
                  color: value ? ResponsiveHelper.purplePrimary : Colors.transparent,
                ),
                child: value
                    ? const Icon(
                        Icons.check,
                        color: Colors.white,
                        size: 12,
                      )
                    : null,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

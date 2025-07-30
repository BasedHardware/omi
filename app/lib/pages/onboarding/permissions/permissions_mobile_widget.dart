import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

class PermissionsMobileWidget extends StatefulWidget {
  final VoidCallback goNext;

  const PermissionsMobileWidget({super.key, required this.goNext});

  @override
  State<PermissionsMobileWidget> createState() => _PermissionsMobileWidgetState();
}

class _PermissionsMobileWidgetState extends State<PermissionsMobileWidget> {
  String _getButtonText(OnboardingProvider provider) {
    bool allPermissionsGranted = provider.hasLocationPermission && provider.hasNotificationPermission && (Platform.isAndroid ? provider.hasBackgroundPermission : true);
    return allPermissionsGranted ? 'Continue' : 'Allow All';
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<OnboardingProvider>(builder: (context, provider, child) {
      return Column(
        children: [
          // Background area - takes remaining space
          Expanded(
            child: Container(), // Just takes up space for background image
          ),

          // Bottom drawer card - wraps content
          Container(
            width: double.infinity,
            padding: EdgeInsets.fromLTRB(32, 0, 32, MediaQuery.of(context).padding.bottom + 8),
            decoration: const BoxDecoration(
              color: Colors.black,
              borderRadius: BorderRadius.only(
                topLeft: Radius.circular(40),
                topRight: Radius.circular(40),
              ),
            ),
            child: SafeArea(
              top: false,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(height: 32),

                  // Main title
                  const Text(
                    'Grant permissions',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 32,
                      fontWeight: FontWeight.bold,
                      height: 1.2,
                      fontFamily: 'Manrope',
                    ),
                    textAlign: TextAlign.center,
                  ),

                  const SizedBox(height: 28),

                  // Permissions checkboxes
                  Column(
                    children: [
                      // Background permission (Android only)
                      if (Platform.isAndroid)
                        _buildPermissionTile(
                          value: provider.hasBackgroundPermission,
                          title: 'Background activity',
                          subtitle: 'Let Omi run in the background for better stability',
                          onChanged: (s) async {
                            if (s != null) {
                              if (s) {
                                await provider.askForBackgroundPermissions();
                              } else {
                                provider.updateBackgroundPermission(false);
                              }
                            }
                          },
                        ),

                      // Location permission
                      _buildPermissionTile(
                        value: provider.hasLocationPermission,
                        title: 'Location access',
                        subtitle: 'Enable background location for the full experience',
                        onChanged: (s) async {
                          if (s != null) {
                            if (s) {
                              var (serviceStatus, permissionStatus) = await provider.askForLocationPermissions();
                              if (!serviceStatus) {
                                showDialog(
                                  context: context,
                                  builder: (ctx) {
                                    return getDialog(
                                      context,
                                      () => Navigator.of(context).pop(),
                                      () => Navigator.of(context).pop(),
                                      'Location Service Disabled',
                                      'Location Service is Disabled. Please go to Settings > Privacy & Security > Location Services and enable it',
                                      singleButton: true,
                                    );
                                  },
                                );
                              } else {
                                if (permissionStatus.isGranted) {
                                  await provider.alwaysAllowLocation();
                                  Permission.locationAlways.onDeniedCallback(() {
                                    showDialog(
                                      context: context,
                                      builder: (ctx) {
                                        return getDialog(
                                          context,
                                          () => Navigator.of(context).pop(),
                                          () => Navigator.of(context).pop(),
                                          'Background Location Access Denied',
                                          'Please go to device settings and set location permission to "Always Allow"',
                                          singleButton: true,
                                          okButtonText: 'Continue',
                                        );
                                      },
                                    );
                                  });
                                  Permission.locationAlways.onGrantedCallback(() {
                                    provider.updateLocationPermission(true);
                                  });
                                } else {
                                  showDialog(
                                    context: context,
                                    builder: (ctx) {
                                      return getDialog(
                                        context,
                                        () => Navigator.of(context).pop(),
                                        () => Navigator.of(context).pop(),
                                        'Background Location Access Denied',
                                        'Please go to device settings and set location permission to "Always Allow"',
                                        singleButton: true,
                                        okButtonText: 'Continue',
                                      );
                                    },
                                  );
                                }
                              }
                            } else {
                              provider.updateLocationPermission(false);
                            }
                          }
                        },
                      ),

                      // Notification permission
                      _buildPermissionTile(
                        value: provider.hasNotificationPermission,
                        title: 'Notifications',
                        subtitle: 'Enable notifications to stay informed',
                        onChanged: (s) async {
                          if (s != null) {
                            if (s) {
                              await provider.askForNotificationPermissions();
                            } else {
                              provider.updateNotificationPermission(false);
                            }
                          }
                        },
                      ),
                    ],
                  ),

                  const SizedBox(height: 8),

                  // Continue button
                  provider.isLoading
                      ? const CircularProgressIndicator(
                          color: Colors.white,
                        )
                      : SizedBox(
                          width: double.infinity,
                          height: 56,
                          child: ElevatedButton(
                            onPressed: () async {
                              provider.setLoading(true);
                              if (Platform.isAndroid) {
                                if (!provider.hasBackgroundPermission) {
                                  await provider.askForBackgroundPermissions();
                                }
                              }
                              await Permission.notification.request().then(
                                (value) async {
                                  if (value.isGranted) {
                                    provider.updateNotificationPermission(true);
                                  }
                                  if (await Permission.location.serviceStatus.isEnabled) {
                                    await Permission.locationWhenInUse.request().then(
                                      (value) async {
                                        if (value.isGranted) {
                                          await Permission.locationAlways.request().then(
                                            (value) async {
                                              if (value.isGranted) {
                                                provider.updateLocationPermission(true);
                                                widget.goNext();
                                                provider.setLoading(false);
                                              } else {
                                                Future.delayed(const Duration(milliseconds: 2500), () async {
                                                  if (await Permission.locationAlways.status.isGranted) {
                                                    provider.updateLocationPermission(true);
                                                  }
                                                  widget.goNext();
                                                  provider.setLoading(false);
                                                });
                                              }
                                            },
                                          );
                                        } else {
                                          widget.goNext();
                                          provider.setLoading(false);
                                        }
                                      },
                                    );
                                  } else {
                                    widget.goNext();
                                    provider.setLoading(false);
                                  }
                                },
                              );
                            },
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.white,
                              foregroundColor: Colors.black,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(28),
                              ),
                              elevation: 0,
                            ),
                            child: Text(
                              _getButtonText(provider),
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w600,
                                fontFamily: 'Manrope',
                              ),
                            ),
                          ),
                        ),
                ],
              ),
            ),
          ),
        ],
      );
    });
  }

  Widget _buildPermissionTile({
    required bool value,
    required String title,
    required String subtitle,
    required Function(bool?) onChanged,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
      decoration: BoxDecoration(
        color: Colors.grey[900],
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Colors.grey[700]!,
          width: 1,
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    fontFamily: 'Manrope',
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.6),
                    fontSize: 12,
                    fontFamily: 'Manrope',
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          Transform.scale(
            scale: 1.2,
            child: Checkbox(
              value: value,
              onChanged: onChanged,
              activeColor: Colors.white,
              checkColor: Colors.black,
              side: BorderSide(
                color: Colors.grey[500]!,
                width: 2,
              ),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(4),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

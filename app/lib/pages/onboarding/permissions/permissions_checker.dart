import 'dart:io';

import 'package:flutter/material.dart';

import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/dialog.dart';

/// Checks if critical permissions are granted. Returns true if all are granted.
Future<bool> arePermissionsGranted() async {
  final notification = await Permission.notification.isGranted;
  final location = await Permission.location.isGranted;
  return notification && location;
}

/// Interstitial screen shown when onboarding was completed (from backend)
/// but permissions haven't been granted on this device (fresh install).
class PermissionsInterstitialPage extends StatelessWidget {
  const PermissionsInterstitialPage({super.key});

  void _goHome(BuildContext context) {
    SharedPreferencesUtil().permissionsCompleted = true;
    Navigator.of(
      context,
    ).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const HomePageWrapper()), (route) => false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Consumer<OnboardingProvider>(
        builder: (context, provider, child) {
          return Column(
            children: [
              // Omi logo in the top area, biased toward bottom
              Expanded(
                child: Align(
                  alignment: const Alignment(0, 0.4),
                  child: Image.asset(Assets.images.logoTransparent.path, width: 120, height: 120),
                ),
              ),

              // Bottom card with permissions
              Container(
                width: double.infinity,
                padding: EdgeInsets.fromLTRB(32, 0, 32, MediaQuery.of(context).padding.bottom + 8),
                decoration: const BoxDecoration(
                  color: Colors.black,
                  borderRadius: BorderRadius.only(topLeft: Radius.circular(40), topRight: Radius.circular(40)),
                ),
                child: SafeArea(
                  top: false,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const SizedBox(height: 32),

                      // Title
                      Text(
                        context.l10n.permissionsSetupTitle,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 32,
                          fontWeight: FontWeight.bold,
                          height: 1.2,
                          fontFamily: 'Manrope',
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 8),

                      // Subtitle
                      Text(
                        context.l10n.permissionsSetupDescription,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.6),
                          fontSize: 15,
                          fontFamily: 'Manrope',
                        ),
                        textAlign: TextAlign.center,
                      ),

                      const SizedBox(height: 28),

                      // Permission tiles
                      if (Platform.isAndroid)
                        _PermissionTile(
                          value: provider.hasBackgroundPermission,
                          title: context.l10n.backgroundActivity,
                          subtitle: context.l10n.backgroundActivityDesc,
                          onChanged: (s) async {
                            if (s == true) {
                              await provider.askForBackgroundPermissions();
                            } else {
                              provider.updateBackgroundPermission(false);
                            }
                          },
                        ),

                      _PermissionTile(
                        value: provider.hasLocationPermission,
                        title: context.l10n.locationAccess,
                        subtitle: context.l10n.locationAccessDesc,
                        onChanged: (s) async {
                          if (s == true) {
                            provider.updateLocationPermission(true);
                            var (serviceStatus, permissionStatus) = await provider.askForLocationPermissions();
                            if (!serviceStatus) {
                              provider.updateLocationPermission(false);
                              if (context.mounted) {
                                showDialog(
                                  context: context,
                                  builder: (ctx) {
                                    return getDialog(
                                      context,
                                      () => Navigator.of(context).pop(),
                                      () => Navigator.of(context).pop(),
                                      context.l10n.locationServiceDisabled,
                                      context.l10n.locationServiceDisabledDesc,
                                      singleButton: true,
                                    );
                                  },
                                );
                              }
                            } else {
                              bool wasGranted = permissionStatus.isGranted;
                              provider.updateLocationPermission(wasGranted);
                              // iOS-only: chain Always so background location
                              // updates work in BGTask windows.
                              await provider.alwaysAllowLocation();
                              if (wasGranted) {
                                provider.updateLocationPermission(true);
                              }
                            }
                          } else {
                            provider.updateLocationPermission(false);
                          }
                        },
                      ),

                      _PermissionTile(
                        value: provider.hasNotificationPermission,
                        title: context.l10n.notifications,
                        subtitle: context.l10n.notificationsDesc,
                        onChanged: (s) async {
                          if (s == true) {
                            await provider.askForNotificationPermissions();
                          } else {
                            provider.updateNotificationPermission(false);
                          }
                        },
                      ),

                      const SizedBox(height: 8),

                      // Continue button — requests both permissions
                      provider.isLoading
                          ? const CircularProgressIndicator(color: Colors.white)
                          : SizedBox(
                              width: double.infinity,
                              height: 56,
                              child: ElevatedButton(
                                onPressed: () async {
                                  provider.setLoading(true);
                                  if (Platform.isAndroid && !provider.hasBackgroundPermission) {
                                    await provider.askForBackgroundPermissions();
                                  }
                                  await Permission.notification.request().then((value) async {
                                    if (value.isGranted) {
                                      provider.updateNotificationPermission(true);
                                    }
                                    if (await Permission.location.serviceStatus.isEnabled) {
                                      var res = await Permission.locationWhenInUse.request();
                                      provider.updateLocationPermission(res.isGranted);
                                      if (Platform.isIOS && res.isGranted) {
                                        await provider.alwaysAllowLocation();
                                      }
                                    }
                                  });
                                  MixpanelManager().permissionsInterstitialCompleted();
                                  provider.setLoading(false);
                                  if (context.mounted) {
                                    _goHome(context);
                                  }
                                },
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.white,
                                  foregroundColor: Colors.black,
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                                  elevation: 0,
                                ),
                                child: Text(
                                  context.l10n.continueButton,
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
        },
      ),
    );
  }
}

class _PermissionTile extends StatelessWidget {
  final bool value;
  final String title;
  final String subtitle;
  final Function(bool?) onChanged;

  const _PermissionTile({required this.value, required this.title, required this.subtitle, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
      decoration: BoxDecoration(
        color: Colors.grey[900],
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey[700]!, width: 1),
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
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 12, fontFamily: 'Manrope'),
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
              side: BorderSide(color: Colors.grey[500]!, width: 2),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
            ),
          ),
        ],
      ),
    );
  }
}

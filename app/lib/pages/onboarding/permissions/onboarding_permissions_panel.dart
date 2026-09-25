import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/ui/components/omi_permission_row.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The permissions the first-run flow and the returning-user interstitial ask for.
///
/// "Always" location is deliberately not here: it is asked by the feature that needs it
/// (Settings → Permissions), never during first run (docs/ux-contract.md §15).
enum OnboardingPermission { background, location, notifications }

/// Reads and requests [OnboardingPermission]s. The default reads the platform directly and requests
/// through [OnboardingProvider] (which keeps its telemetry and flags); tests pass a fake.
abstract class OnboardingPermissionsSource {
  List<OnboardingPermission> get permissions;
  Future<OmiPermissionStatus> status(OnboardingPermission permission);
  Future<void> request(OnboardingPermission permission);
}

class PlatformOnboardingPermissionsSource implements OnboardingPermissionsSource {
  PlatformOnboardingPermissionsSource(this.provider);

  final OnboardingProvider provider;

  @override
  List<OnboardingPermission> get permissions => [
        if (Platform.isAndroid) OnboardingPermission.background,
        OnboardingPermission.location,
        OnboardingPermission.notifications,
      ];

  @override
  Future<OmiPermissionStatus> status(OnboardingPermission permission) async {
    switch (permission) {
      case OnboardingPermission.background:
        final granted = await FlutterForegroundTask.isIgnoringBatteryOptimizations;
        return granted ? OmiPermissionStatus.granted : OmiPermissionStatus.askable;
      case OnboardingPermission.location:
        if (await Permission.location.serviceStatus.isDisabled) return OmiPermissionStatus.serviceOff;
        return OmiPermissionStatus.fromStatus(await Permission.locationWhenInUse.status);
      case OnboardingPermission.notifications:
        return OmiPermissionStatus.fromStatus(await Permission.notification.status);
    }
  }

  @override
  Future<void> request(OnboardingPermission permission) async {
    switch (permission) {
      case OnboardingPermission.background:
        await provider.askForBackgroundPermissions();
      case OnboardingPermission.location:
        await provider.askForLocationPermissions();
      case OnboardingPermission.notifications:
        await provider.askForNotificationPermissions();
    }
  }
}

/// The permission rows shared by the onboarding step and the interstitial: one
/// [OmiPermissionRow] per permission, each with its own Allow / Open Settings.
///
/// Nothing here prompts on its own; the screens' Continue only moves on. States are re-read when
/// the app returns to the foreground, so a permission switched on in Settings shows as allowed.
class OnboardingPermissionsPanel extends StatefulWidget {
  const OnboardingPermissionsPanel({super.key, this.source});

  /// Defaults to [PlatformOnboardingPermissionsSource] over the ambient [OnboardingProvider].
  final OnboardingPermissionsSource? source;

  @override
  State<OnboardingPermissionsPanel> createState() => _OnboardingPermissionsPanelState();
}

class _OnboardingPermissionsPanelState extends State<OnboardingPermissionsPanel> with WidgetsBindingObserver {
  late final OnboardingPermissionsSource _source =
      widget.source ?? PlatformOnboardingPermissionsSource(context.read<OnboardingProvider>());
  final Map<OnboardingPermission, OmiPermissionStatus> _statuses = {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_refresh());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_refresh());
  }

  Future<void> _refresh() async {
    for (final permission in _source.permissions) {
      OmiPermissionStatus status;
      try {
        status = await _source.status(permission);
      } catch (_) {
        status = OmiPermissionStatus.askable;
      }
      if (!mounted) return;
      setState(() => _statuses[permission] = status);
    }
  }

  Future<void> _allow(OnboardingPermission permission) async {
    try {
      await _source.request(permission);
    } finally {
      await _refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final permission in _source.permissions) ...[
          OmiPermissionRow(
            key: ValueKey('onboarding_permission_${permission.name}'),
            // The same glyphs as the Settings permission list.
            leading: FaIcon(switch (permission) {
              OnboardingPermission.background => FontAwesomeIcons.batteryFull,
              OnboardingPermission.location => FontAwesomeIcons.locationArrow,
              OnboardingPermission.notifications => FontAwesomeIcons.solidBell,
            }),
            title: switch (permission) {
              OnboardingPermission.background => l10n.backgroundActivity,
              OnboardingPermission.location => l10n.locationAccess,
              OnboardingPermission.notifications => l10n.notifications,
            },
            reason: switch (permission) {
              OnboardingPermission.background => l10n.backgroundActivityDesc,
              OnboardingPermission.location => l10n.locationAccessDesc,
              OnboardingPermission.notifications => l10n.notificationsDesc,
            },
            status: _statuses[permission] ?? OmiPermissionStatus.askable,
            onAllow: () => _allow(permission),
          ),
          const SizedBox(height: OmiSpacing.sm),
        ],
      ],
    );
  }
}

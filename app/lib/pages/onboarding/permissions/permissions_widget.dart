import 'dart:async';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/onboarding/permissions/onboarding_permissions_panel.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_plain_step.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

/// How one card on the first-run permissions step looks.
enum OnboardingPermissionCardState {
  /// Not answered yet: grey, switch off.
  unanswered,

  /// Allowed: switch on.
  allowed,

  /// Answered with no (or switched off in Settings). Tapping opens Settings.
  denied,
}

/// First-run permissions step: one switch card per permission (docs/ux-contract.md §15).
///
/// Each card is answered by toggling it, which shows that permission's system prompt. A "no" is an
/// answer: the card turns orange (notifications: red with "Tap to fix") and the reader can still
/// continue. Continue unlocks once every card has been answered. Bluetooth is asked as the app
/// opens, so its card only appears when it was not allowed.
class PermissionsWidget extends StatefulWidget {
  final VoidCallback goNext;
  final OnboardingPermissionsSource? source;

  const PermissionsWidget({super.key, required this.goNext, this.source});

  @override
  State<PermissionsWidget> createState() => _PermissionsWidgetState();
}

class _PermissionsWidgetState extends State<PermissionsWidget> with WidgetsBindingObserver {
  late final OnboardingPermissionsSource _source = resolveOnboardingPermissionsSource(context, widget.source);

  /// The cards, fixed when the step opens: Bluetooth stays listed after it is allowed here.
  List<OnboardingPermission>? _permissions;
  final Map<OnboardingPermission, OmiPermissionStatus> _statuses = {};

  /// Cards whose system prompt the reader has already seen (on this step, or Bluetooth at launch).
  final Set<OnboardingPermission> _asked = {};
  OnboardingPermission? _busy;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    if (SharedPreferencesUtil().getBool('onboarding/bluetoothAskedAtLaunch')) {
      _asked.add(OnboardingPermission.bluetooth);
    }
    unawaited(_load());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Back from Settings: show what the reader switched on there.
    if (state == AppLifecycleState.resumed) unawaited(_refresh());
  }

  Future<OmiPermissionStatus> _read(OnboardingPermission permission) async {
    try {
      return await _source.status(permission);
    } catch (_) {
      return OmiPermissionStatus.askable;
    }
  }

  Future<void> _load() async {
    final bluetooth = await _read(OnboardingPermission.bluetooth);
    if (!mounted) return;
    setState(() {
      _permissions = [
        if (bluetooth != OmiPermissionStatus.granted) OnboardingPermission.bluetooth,
        ..._source.permissions,
      ];
      _statuses[OnboardingPermission.bluetooth] = bluetooth;
    });
    await _refresh();
  }

  Future<void> _refresh() async {
    final permissions = _permissions;
    if (permissions == null) return;
    for (final permission in permissions) {
      final status = await _read(permission);
      if (!mounted) return;
      setState(() => _statuses[permission] = status);
    }
  }

  OnboardingPermissionCardState _stateOf(OnboardingPermission permission) {
    final status = _statuses[permission] ?? OmiPermissionStatus.askable;
    if (status == OmiPermissionStatus.granted) return OnboardingPermissionCardState.allowed;
    if (status == OmiPermissionStatus.blocked || status == OmiPermissionStatus.serviceOff) {
      return OnboardingPermissionCardState.denied;
    }
    return _asked.contains(permission)
        ? OnboardingPermissionCardState.denied
        : OnboardingPermissionCardState.unanswered;
  }

  bool get _allAnswered {
    final permissions = _permissions;
    if (permissions == null) return false;
    return permissions.every((p) => _stateOf(p) != OnboardingPermissionCardState.unanswered);
  }

  Future<void> _onTap(OnboardingPermission permission) async {
    if (_busy != null) return;
    final state = _stateOf(permission);
    if (state == OnboardingPermissionCardState.allowed) return;
    OmiHaptics.selection();
    if (state == OnboardingPermissionCardState.denied) {
      // The system will not ask again (or the reader said no): only Settings can turn it on.
      await openAppSettings();
      return;
    }
    setState(() => _busy = permission);
    try {
      await _source.request(permission);
    } catch (e) {
      Logger.debug('Onboarding permission request failed for ${permission.name}: $e');
    } finally {
      _asked.add(permission);
      final status = await _read(permission);
      if (mounted) {
        setState(() {
          _statuses[permission] = status;
          _busy = null;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final permissions = _permissions ?? const <OnboardingPermission>[];
    return OnboardingPlainStep(
      title: context.l10n.grantPermissions,
      body: Column(
        children: [
          for (final permission in permissions) ...[
            _OnboardingPermissionRow(
              key: ValueKey('onboarding_permission_${permission.name}'),
              permission: permission,
              state: _stateOf(permission),
              busy: _busy == permission,
              onTap: () => _onTap(permission),
            ),
            const SizedBox(height: OmiSpacing.sm),
          ],
        ],
      ),
      action: OmiButton(
        key: const Key('onboarding_permissions_continue'),
        label: context.l10n.continueButton,
        expand: true,
        onPressed: _allAnswered
            ? () {
                OmiHaptics.selection();
                widget.goNext();
              }
            : null,
      ),
    );
  }
}

/// One permission as its own card: icon tile, title, and the switch. A line under the title
/// appears only when there is something to do (Bluetooth off, notifications to fix).
class _OnboardingPermissionRow extends StatelessWidget {
  const _OnboardingPermissionRow({
    super.key,
    required this.permission,
    required this.state,
    required this.busy,
    required this.onTap,
  });

  final OnboardingPermission permission;
  final OnboardingPermissionCardState state;
  final bool busy;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final denied = state == OnboardingPermissionCardState.denied;
    final String? note = !denied
        ? null
        : switch (permission) {
            OnboardingPermission.notifications => l10n.onboardingPermissionTapToFix,
            OnboardingPermission.bluetooth => l10n.onboardingBluetoothRequired,
            _ => null,
          };
    final title = onboardingPermissionTitle(l10n, permission);

    return Semantics(
      button: true,
      toggled: state == OnboardingPermissionCardState.allowed,
      label: note == null ? title : '$title, $note',
      excludeSemantics: true,
      child: Material(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: busy ? null : onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 64),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
              child: Row(
                children: [
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(color: OmiColors.surface0, borderRadius: OmiRadius.smAll),
                    child: Center(
                      child: FaIcon(onboardingPermissionIcon(permission), size: 15, color: OmiColors.textPrimary),
                    ),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                        if (note != null) ...[
                          const SizedBox(height: 2),
                          Text(note, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  OnboardingPermissionToggle(
                    on: state == OnboardingPermissionCardState.allowed,
                    denied: denied,
                    busy: busy,
                    // Notifications that are off are worth fixing (red); the rest are a caution (orange).
                    deniedColor:
                        permission == OnboardingPermission.notifications ? OmiColors.danger : OmiColors.warning,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

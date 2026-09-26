import 'package:flutter/material.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_service.dart';

// Product names are the same in every language.
const String _kOmiGlass = 'OmiGlass';
const String _kAppleWatch = 'Apple Watch';
const String _kRayBanMeta = 'Ray-Ban Meta';

/// Recorders people already own, one row each, in the order the app supports them.
const List<(DeviceType, String, String)> _kOtherRecorders = [
  (DeviceType.plaud, 'PLAUD NotePin', 'add_device_plaud'),
  (DeviceType.bee, 'Bee', 'add_device_bee'),
  (DeviceType.limitless, 'Limitless Pendant', 'add_device_limitless'),
  (DeviceType.fieldy, 'Fieldy', 'add_device_fieldy'),
  (DeviceType.friendPendant, 'Friend', 'add_device_friend'),
];
const String _kOmiBrand = 'Omi';

/// The "What will you wear?" choices (Rev 3 PickDevice): Omi's own devices first, then ones people
/// already own (each supported recorder on its own row), then this phone — "no device" is a first-class choice. Every wearable opens the
/// same connect flow ([onConnect]), which finds whichever of them is nearby (and walks Apple Watch
/// and Ray-Ban Meta through their setup). Shared by Add a device and onboarding.
class DevicePickerGroups extends StatelessWidget {
  const DevicePickerGroups({super.key, required this.onConnect, required this.onUsePhone});

  final VoidCallback onConnect;
  final VoidCallback onUsePhone;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        const _SmallHead(_kOmiBrand),
        OmiSettingsGroup(
          children: [
            OmiSettingsRow(
              key: const Key('add_device_omi'),
              leading: const _Product(DeviceType.omi),
              title: l10n.omiPendantName,
              subtitle: l10n.allDayConversations,
              onTap: onConnect,
            ),
            OmiSettingsRow(
              key: const Key('add_device_omiglass'),
              leading: const _Product(DeviceType.openglass),
              title: _kOmiGlass,
              subtitle: l10n.conversationsAndPhotos,
              onTap: onConnect,
            ),
          ],
        ),
        const SizedBox(height: 22),
        _SmallHead(l10n.alreadyHaveOne),
        OmiSettingsGroup(
          children: [
            if (PlatformService.isIOS)
              OmiSettingsRow(
                key: const Key('add_device_watch'),
                leading: const _Product(DeviceType.appleWatch),
                title: _kAppleWatch,
                subtitle: l10n.wristMic,
                onTap: onConnect,
              ),
            OmiSettingsRow(
              key: const Key('add_device_rayban'),
              leading: const _Product(DeviceType.raybanMeta),
              title: _kRayBanMeta,
              subtitle: l10n.glassesAudio,
              onTap: onConnect,
            ),
            for (final (type, name, key) in _kOtherRecorders)
              OmiSettingsRow(
                key: Key(key),
                leading: _Product(type),
                title: name,
                subtitle: l10n.bringRecordingsIntoOmi,
                onTap: onConnect,
              ),
          ],
        ),
        const SizedBox(height: 22),
        _SmallHead(l10n.noDeviceHeader),
        OmiSettingsGroup(
          children: [
            OmiSettingsRow(
              key: const Key('add_device_phone'),
              leading: const OmiGlyph(OmiGlyphs.iphone),
              title: PlatformService.isIOS ? l10n.useThisIphone : l10n.useThisPhone,
              subtitle: l10n.startInSeconds,
              onTap: onUsePhone,
            ),
          ],
        ),
      ],
    );
  }
}

/// A small uppercase heading over a group (v2 `small_head`: 13/18 semibold, tracked).
class _SmallHead extends StatelessWidget {
  const _SmallHead(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.xs),
      child: Semantics(
        header: true,
        child: Text(
          text.toUpperCase(),
          style: OmiType.footnote.copyWith(
            fontWeight: FontWeight.w600,
            letterSpacing: 0.4,
            color: OmiColors.textSecondary,
          ),
        ),
      ),
    );
  }
}

/// The product's own picture at row-icon size.
class _Product extends StatelessWidget {
  const _Product(this.type);

  final DeviceType type;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: SizedBox(
        width: 30,
        height: 30,
        child: Image.asset(DeviceUtils.getDeviceImagePath(deviceType: type), fit: BoxFit.contain),
      ),
    );
  }
}

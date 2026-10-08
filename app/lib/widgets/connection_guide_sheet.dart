import 'dart:io';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/schema/device_guide.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/onboarding/find_device/device_discovery_controller.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/device_pairing_sheet.dart';
import 'package:omi/widgets/rayban_meta_input_picker_sheet.dart';

/// Pairing instructions per device, in the shared sheet shell (docs/ux-contract.md §2).
class ConnectionGuideSheet extends StatelessWidget {
  const ConnectionGuideSheet({super.key});

  /// Opens the guide. Picking a device opens its pairing steps on top; their Done closes both.
  static Future<void> show(BuildContext context) {
    return showOmiSheet<void>(
      context: context,
      title: context.l10n.connectionGuide,
      builder: (_) => const ConnectionGuideSheet(),
      nativeBuilder: (_) => const _NativeConnectionGuide(),
    );
  }

  /// The guide's devices, in the order both presentations show them.
  @visibleForTesting
  static List<DeviceGuideProduct> products(BuildContext context) {
    final l10n = context.l10n;
    return [
      DeviceGuideProduct(
        id: 'omi',
        name: 'Omi',
        pairingTitle: l10n.pairingTitleOmi,
        pairingDescription: l10n.pairingDescOmi,
        localImagePath: Assets.images.omiWithoutRope.path,
      ),
      DeviceGuideProduct(
        id: 'omi_devkit',
        name: 'Omi DevKit',
        pairingTitle: l10n.pairingTitleOmiDevkit,
        pairingDescription: l10n.pairingDescOmiDevkit,
        localImagePath: Assets.images.omiDevkitWithoutRope.path,
      ),
      DeviceGuideProduct(
        id: 'omi_glass',
        name: 'Omi Glass',
        pairingTitle: l10n.pairingTitleOmiGlass,
        pairingDescription: l10n.pairingDescOmiGlass,
        localImagePath: Assets.images.omiGlass.path,
      ),
      DeviceGuideProduct(
        id: 'plaud_note',
        name: 'Plaud Note',
        pairingTitle: l10n.pairingTitlePlaudNote,
        pairingDescription: l10n.pairingDescPlaudNote,
        localImagePath: Assets.images.plaudNotePin.path,
      ),
      DeviceGuideProduct(
        id: 'bee',
        name: 'Bee',
        pairingTitle: l10n.pairingTitleBee,
        pairingDescription: l10n.pairingDescBee,
        localImagePath: Assets.images.beeDevice.path,
      ),
      DeviceGuideProduct(
        id: 'limitless',
        name: 'Limitless',
        pairingTitle: l10n.pairingTitleLimitless,
        pairingDescription: l10n.pairingDescLimitless,
        localImagePath: Assets.images.limitless.path,
      ),
      DeviceGuideProduct(
        id: 'friend_pendant',
        name: 'Friend Pendant',
        pairingTitle: l10n.pairingTitleFriendPendant,
        pairingDescription: l10n.pairingDescFriendPendant,
        localImagePath: Assets.images.friendPendant.path,
      ),
      DeviceGuideProduct(
        id: 'fieldy',
        name: 'Fieldy',
        pairingTitle: l10n.pairingTitleFieldy,
        pairingDescription: l10n.pairingDescFieldy,
        localImagePath: Assets.images.fieldy.path,
      ),
      // Apple Watch pairs through the iPhone Watch app only.
      if (Platform.isIOS)
        DeviceGuideProduct(
          id: 'apple_watch',
          name: 'Apple Watch',
          pairingTitle: l10n.pairingTitleAppleWatch,
          pairingDescription: l10n.pairingDescAppleWatch,
          localImagePath: Assets.images.appleWatch.path,
        ),
      DeviceGuideProduct(
        id: 'neo_one',
        name: 'Neo One',
        pairingTitle: l10n.pairingTitleNeoOne,
        pairingDescription: l10n.pairingDescNeoOne,
        localImagePath: Assets.images.neoOne.path,
      ),
      if (Platform.isIOS)
        DeviceGuideProduct(id: 'rayban_meta', name: 'Ray-Ban Meta', localImagePath: Assets.images.raybanMeta.path),
    ];
  }

  static void _onDeviceTapped(BuildContext context, DeviceGuideProduct product) {
    PlatformManager.instance.analytics.connectionGuideDeviceTapped(product.id);
    if (product.id == 'rayban_meta') {
      Widget picker(BuildContext sheetContext, {bool native = false}) => RayBanMetaInputPickerSheet(
            native: native,
            onConnected: () {
              Navigator.of(sheetContext).pop();
              Navigator.of(context).pop();
            },
          );
      showOmiSheet<void>(
        context: context,
        title: context.l10n.rayBanMetaMicPickerTitle,
        builder: (sheetContext) => picker(sheetContext),
        nativeBuilder: (sheetContext) => picker(sheetContext, native: true),
      );
      return;
    }
    Widget pairing(BuildContext sheetContext, {bool native = false}) => DevicePairingSheet(
          product: product,
          native: native,
          onDismissAll: () {
            PlatformManager.instance.analytics.connectionGuideDismissed(product.id);
            Navigator.of(sheetContext).pop();
            Navigator.of(context).pop();
          },
        );
    showOmiSheet<void>(
      context: context,
      builder: (sheetContext) => pairing(sheetContext),
      nativeBuilder: (sheetContext) => pairing(sheetContext, native: true),
    );
  }

  @override
  Widget build(BuildContext context) {
    final devices = products(context);
    return ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.75),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.xs, OmiSpacing.xs, OmiSpacing.xs, OmiSpacing.xl),
        child: _buildDeviceGrid(context, devices),
      ),
    );
  }

  Widget _buildDeviceGrid(BuildContext context, List<DeviceGuideProduct> devices) {
    final rows = <Widget>[];
    for (var i = 0; i < devices.length; i += 2) {
      final left = devices[i];
      final right = i + 1 < devices.length ? devices[i + 1] : null;
      rows.add(
        Row(
          children: [
            Expanded(child: _buildDeviceCard(context, left)),
            const SizedBox(width: OmiSpacing.md),
            Expanded(child: right != null ? _buildDeviceCard(context, right) : const SizedBox.shrink()),
          ],
        ),
      );
      if (i + 2 < devices.length) rows.add(const SizedBox(height: OmiSpacing.md));
    }
    return Column(children: rows);
  }

  Widget _buildDeviceCard(BuildContext context, DeviceGuideProduct product) {
    return Semantics(
      button: true,
      label: product.name,
      excludeSemantics: true,
      child: Material(
        color: OmiColors.surface2,
        borderRadius: OmiRadius.lgAll,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () {
            OmiHaptics.selection();
            _onDeviceTapped(context, product);
          },
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: OmiSpacing.lg, horizontal: OmiSpacing.sm),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (product.localImagePath != null)
                  Image.asset(product.localImagePath!, width: 80, height: 80, fit: BoxFit.contain)
                else
                  SizedBox(width: 80, height: 80, child: Icon(Icons.devices, color: OmiColors.textTertiary)),
                const SizedBox(height: OmiSpacing.sm),
                Text(
                  product.name,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The guide as a native list: one navigation row per product, with its bundled art as the
/// thumbnail, opening the same pairing sheet (or, for Ray-Ban Meta, the microphone picker).
class _NativeConnectionGuide extends StatefulWidget {
  const _NativeConnectionGuide();

  @override
  State<_NativeConnectionGuide> createState() => _NativeConnectionGuideState();
}

class _NativeConnectionGuideState extends State<_NativeConnectionGuide> {
  late final NativeAssetUris _images = NativeAssetUris(() {
    if (mounted) setState(() {});
  });

  @override
  void dispose() {
    _images.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return IosNativeSurface(
      title: l10n.connectionGuide,
      fallback: OmiSheetScaffold(title: l10n.connectionGuide, child: const ConnectionGuideSheet()),
      toolbar: [
        NativeRow('guide_close', l10n.close, symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        NativeSection('guide_products', [
          for (final product in ConnectionGuideSheet.products(context))
            NativeRow(
              'guide_product:${product.id}',
              product.name,
              kind: 'navigation',
              imageUri: nativeImageUri(_images[product.localImagePath]),
              action: (_) {
                OmiHaptics.selection();
                ConnectionGuideSheet._onDeviceTapped(context, product);
              },
            ),
        ]),
      ],
    );
  }
}

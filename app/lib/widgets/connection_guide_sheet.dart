import 'package:flutter/material.dart';

import 'package:omi/backend/schema/device_guide.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/device_pairing_sheet.dart';

class ConnectionGuideSheet extends StatelessWidget {
  const ConnectionGuideSheet({super.key});

  List<DeviceGuideProduct> _buildDevices(BuildContext context) {
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
    ];
  }

  void _onDeviceTapped(BuildContext context, DeviceGuideProduct product) {
    MixpanelManager().connectionGuideDeviceTapped(product.id);
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (sheetContext) => DevicePairingSheet(
        product: product,
        onDismissAll: () {
          MixpanelManager().connectionGuideDismissed(product.id);
          Navigator.of(sheetContext).pop();
          Navigator.of(context).pop();
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final devices = _buildDevices(context);
    return Container(
      constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.85),
      decoration: const BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary,
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(24),
          topRight: Radius.circular(24),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Handle bar
          Container(
            margin: const EdgeInsets.only(top: 12),
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: ResponsiveHelper.textTertiary,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(height: 20),
          // Title
          Text(
            context.l10n.connectionGuide,
            style: const TextStyle(
              color: ResponsiveHelper.textPrimary,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 24),
          // Device grid
          Flexible(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                children: [
                  _buildDeviceGrid(context, devices),
                  SizedBox(height: MediaQuery.of(context).padding.bottom + 24),
                ],
              ),
            ),
          ),
        ],
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
            const SizedBox(width: 16),
            Expanded(child: right != null ? _buildDeviceCard(context, right) : const SizedBox.shrink()),
          ],
        ),
      );
      if (i + 2 < devices.length) rows.add(const SizedBox(height: 16));
    }
    return Column(children: rows);
  }

  Widget _buildDeviceCard(BuildContext context, DeviceGuideProduct product) {
    return GestureDetector(
      onTap: () => _onDeviceTapped(context, product),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 12),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundTertiary,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (product.localImagePath != null)
              Image.asset(product.localImagePath!, width: 80, height: 80, fit: BoxFit.contain)
            else
              const SizedBox(width: 80, height: 80, child: Icon(Icons.devices, color: ResponsiveHelper.textTertiary)),
            const SizedBox(height: 12),
            Text(
              product.name,
              style: const TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }
}

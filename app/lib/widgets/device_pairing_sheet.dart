import 'package:flutter/material.dart';

import 'package:omi/backend/schema/device_guide.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// How to pair one device from the connection guide. Shown in the shared sheet shell
/// (docs/ux-contract.md §2); "Done" closes this sheet and the guide.
class DevicePairingSheet extends StatelessWidget {
  final DeviceGuideProduct product;
  final VoidCallback onDismissAll;

  const DevicePairingSheet({super.key, required this.product, required this.onDismissAll});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.xl),
      child: Column(
        children: [
          ExcludeSemantics(
            child: product.localImagePath != null
                ? ClipRRect(
                    borderRadius: OmiRadius.lgAll,
                    child: Image.asset(product.localImagePath!, height: 180, width: 180, fit: BoxFit.contain),
                  )
                : const SizedBox(
                    height: 180,
                    width: 180,
                    child: Icon(Icons.bluetooth_searching, size: 64, color: OmiColors.textSecondary),
                  ),
          ),
          const SizedBox(height: OmiSpacing.xl),
          Semantics(
            header: true,
            child: Text(
              product.pairingTitle.isNotEmpty ? product.pairingTitle : product.name,
              style: OmiType.title2,
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(height: OmiSpacing.sm),
          if (product.pairingDescription.isNotEmpty)
            Text(
              product.pairingDescription,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
              textAlign: TextAlign.center,
            ),
          const SizedBox(height: OmiSpacing.xxl),
          OmiButton(label: context.l10n.done, expand: true, onPressed: onDismissAll),
          const SizedBox(height: OmiSpacing.xs),
          OmiButton.tertiary(
            label: context.l10n.reportAnIssue,
            expand: true,
            onPressed: () async {
              PlatformManager.instance.analytics.connectionGuideReportIssue(product.id);
              onDismissAll();
              await IntercomManager.instance.intercom.displayMessenger();
            },
          ),
        ],
      ),
    );
  }
}

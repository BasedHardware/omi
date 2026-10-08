import 'package:flutter/material.dart';

import 'package:omi/backend/schema/device_guide.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/onboarding/find_device/device_discovery_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// How to pair one device from the connection guide. Shown in the shared sheet shell
/// (docs/ux-contract.md §2); "Done" closes this sheet and the guide.
class DevicePairingSheet extends StatelessWidget {
  final DeviceGuideProduct product;
  final VoidCallback onDismissAll;

  const DevicePairingSheet({super.key, required this.product, required this.onDismissAll, this.native = false});

  /// Draws the native presentation, with the classic content in the shared shell as its fallback.
  final bool native;

  @override
  Widget build(BuildContext context) {
    if (native) return _NativeDevicePairing(sheet: this);
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
                : SizedBox(
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
          OmiButton.tertiary(label: context.l10n.reportAnIssue, expand: true, onPressed: _reportIssue),
        ],
      ),
    );
  }

  Future<void> _reportIssue() async {
    PlatformManager.instance.analytics.connectionGuideReportIssue(product.id);
    onDismissAll();
    await IntercomManager.instance.intercom.displayMessenger();
  }
}

/// The pairing steps as a native list: the product art (once its bundled copy is ready), the title
/// and description, Done (which closes this sheet and the guide) and Report an issue.
class _NativeDevicePairing extends StatefulWidget {
  const _NativeDevicePairing({required this.sheet});

  final DevicePairingSheet sheet;

  @override
  State<_NativeDevicePairing> createState() => _NativeDevicePairingState();
}

class _NativeDevicePairingState extends State<_NativeDevicePairing> {
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
    final sheet = widget.sheet;
    final product = sheet.product;
    final title = product.pairingTitle.isNotEmpty ? product.pairingTitle : product.name;
    final art = nativeImageUri(_images[product.localImagePath]);
    return IosNativeSurface(
      title: product.name,
      fallback: OmiSheetScaffold(child: DevicePairingSheet(product: product, onDismissAll: sheet.onDismissAll)),
      toolbar: [
        NativeRow('pairing_close', l10n.close, symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        NativeSection('pairing_steps', [
          if (art != null) NativeRow('pairing_art', product.name, kind: 'image', imageUri: art, maximumValue: 1),
          NativeRow('pairing_title', title,
              kind: 'label', symbol: art == null ? 'dot.radiowaves.left.and.right' : null),
          if (product.pairingDescription.isNotEmpty)
            NativeRow('pairing_description', product.pairingDescription, kind: 'label'),
        ]),
        NativeSection('pairing_actions', [
          NativeRow('pairing_done', l10n.done, action: (_) => sheet.onDismissAll()),
          NativeRow('pairing_report', l10n.reportAnIssue,
              symbol: 'exclamationmark.bubble', action: (_) => sheet._reportIssue()),
        ]),
      ],
    );
  }
}

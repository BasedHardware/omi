import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class CaptureRecoveryBanner extends StatelessWidget {
  const CaptureRecoveryBanner({super.key, this.monitor});

  final CaptureWedgeMonitor? monitor;

  @override
  Widget build(BuildContext context) {
    final wedge = monitor ?? CaptureWedgeMonitor.instance;
    return ListenableBuilder(
      listenable: wedge,
      builder: (context, _) {
        final episode = wedge.visiblePrompt;
        if (episode == null) return const SizedBox.shrink();
        if (TickerMode.valuesOf(context).enabled) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (context.mounted) wedge.markPromptShown();
          });
        }
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: Semantics(
            button: true,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () {
                wedge.onRecoveryActioned(surface: 'banner');
                unawaited(HomeNavigation.openRoute('/settings/device'));
              },
              child: Container(
                key: const Key('capture_recovery_banner'),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: OmiColors.surface1,
                  borderRadius: const BorderRadius.all(Radius.circular(OmiRadius.md)),
                  border: Border.all(color: OmiColors.border, width: 0.5),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.warning_amber_rounded, size: 16, color: OmiColors.warning),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        context.l10n.captureRecoveryBanner,
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                      ),
                    ),
                    const Icon(Icons.chevron_right, size: 16, color: OmiColors.textTertiary),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

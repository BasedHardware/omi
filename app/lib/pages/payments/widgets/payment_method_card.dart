import 'package:flutter/material.dart';

import 'package:skeletonizer/skeletonizer.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/pages/payments/models/payment_method_config.dart';

class PaymentMethodCard extends StatelessWidget {
  final Widget icon;
  final String title;
  final String subtitle;
  final Color backgroundColor;
  final VoidCallback? onManageTap;
  final VoidCallback? onSetActiveTap;
  final bool isActive;
  final bool isConnected;

  const PaymentMethodCard({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.backgroundColor,
    this.onManageTap,
    this.onSetActiveTap,
    this.isActive = false,
    this.isConnected = false,
  });

  factory PaymentMethodCard.fromConfig(PaymentMethodConfig config) {
    return PaymentMethodCard(
      icon: config.icon,
      title: config.title,
      subtitle: config.subtitle,
      backgroundColor: config.backgroundColor,
      onManageTap: config.onManageTap,
      onSetActiveTap: config.onSetActiveTap,
      isActive: config.isActive,
      isConnected: config.isConnected,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Skeleton.leaf(
      child: Container(
        padding: const EdgeInsets.all(OmiSpacing.md),
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: OmiRadius.mdAll,
          border: !isConnected
              ? Border.all(
                  color: OmiColors.border,
                  width: 2,
                  strokeAlign: BorderSide.strokeAlignOutside,
                  style: BorderStyle.solid,
                )
              : null,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: const BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.smAll),
                  child: icon,
                ),
                const SizedBox(width: OmiSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: OmiType.headline,
                      ),
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: isActive ? OmiColors.successSurface : OmiColors.surface3,
                          borderRadius: OmiRadius.mdAll,
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (isActive) ...[
                              const Icon(Icons.check_circle, color: OmiColors.success, size: 16),
                              const SizedBox(width: 4),
                            ] else if (isConnected && !isActive) ...[
                              const Icon(Icons.circle, color: OmiColors.textSecondary, size: 16),
                              const SizedBox(width: 4),
                            ],
                            Text(
                              subtitle,
                              style: OmiType.footnote.copyWith(
                                color: isActive ? OmiColors.success : OmiColors.textSecondary,
                                fontWeight: isActive ? FontWeight.w500 : FontWeight.w400,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: OmiSpacing.md),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                if (isConnected && isActive) ...[
                  OmiButton(label: context.l10n.update, onPressed: onManageTap, size: OmiButtonSize.compact),
                ],
                if (!isActive && isConnected) ...[
                  PopupMenuButton<String>(
                    icon: const Icon(Icons.more_vert, color: OmiColors.textSecondary),
                    tooltip: context.l10n.moreOptions,
                    onSelected: (value) {
                      if (value == 'update') {
                        onManageTap?.call();
                      } else if (value == 'setActive') {
                        onSetActiveTap?.call();
                      }
                    },
                    itemBuilder: (context) => [
                      PopupMenuItem(value: 'update', child: Text(context.l10n.update)),
                      if (onSetActiveTap != null)
                        PopupMenuItem(value: 'setActive', child: Text(context.l10n.setActive)),
                    ],
                  ),
                ],
                if (!isConnected) ...[
                  OmiButton(label: context.l10n.connect, onPressed: onManageTap, size: OmiButtonSize.compact),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';

import 'package:skeletonizer/skeletonizer.dart';

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
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(12),
          border: !isConnected
              ? Border.all(
                  color: Colors.white.withOpacity(0.3),
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
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: icon,
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: isActive ? Colors.green.withOpacity(0.2) : Colors.white.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (isActive) ...[
                              const Icon(
                                Icons.check_circle,
                                color: Colors.green,
                                size: 16,
                              ),
                              const SizedBox(width: 4),
                            ] else if (isConnected && !isActive) ...[
                              Icon(
                                Icons.circle,
                                color: Colors.white.withOpacity(0.7),
                                size: 16,
                              ),
                              const SizedBox(width: 4),
                            ],
                            Text(
                              subtitle,
                              style: TextStyle(
                                color: isActive ? Colors.green : Colors.white.withOpacity(0.7),
                                fontSize: 14,
                                fontWeight: isActive ? FontWeight.w500 : FontWeight.normal,
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
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                if (isConnected && isActive) ...[
                  ElevatedButton(
                    onPressed: onManageTap,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.black,
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: Text(
                      context.l10n.update,
                      style: const TextStyle(fontWeight: FontWeight.w500),
                    ),
                  ),
                  const SizedBox(width: 16),
                ],
                if (!isActive && isConnected) ...[
                  PopupMenuButton<String>(
                    icon: Icon(
                      Icons.more_vert,
                      color: Colors.white.withOpacity(0.7),
                    ),
                    onSelected: (value) {
                      if (value == 'update') {
                        onManageTap?.call();
                      } else if (value == 'setActive') {
                        onSetActiveTap?.call();
                      }
                    },
                    itemBuilder: (context) => [
                      PopupMenuItem(
                        value: 'update',
                        child: Text(context.l10n.update),
                      ),
                      if (onSetActiveTap != null)
                        PopupMenuItem(
                          value: 'setActive',
                          child: Text(context.l10n.setActive),
                        ),
                    ],
                  ),
                ],
                if (!isConnected) ...[
                  ElevatedButton(
                    onPressed: onManageTap,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.black,
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: Text(
                      context.l10n.connect,
                      style: const TextStyle(fontWeight: FontWeight.w500),
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

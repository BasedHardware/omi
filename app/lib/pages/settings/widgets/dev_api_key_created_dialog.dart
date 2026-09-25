import 'package:flutter/material.dart';

import 'package:omi/backend/schema/dev_api_key.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Shows a newly created developer API key once. It cannot be shown again, so the sheet only
/// closes through Done (no swipe-down, no scrim tap, no X).
class DevApiKeyCreatedSheet extends StatelessWidget {
  final DevApiKeyCreated apiKey;

  const DevApiKeyCreatedSheet({super.key, required this.apiKey});

  static Future<void> show(BuildContext context, DevApiKeyCreated apiKey) {
    return showOmiSheet(
      context: context,
      showCloseButton: false,
      isDismissible: false,
      enableDrag: false,
      builder: (_) => DevApiKeyCreatedSheet(apiKey: apiKey),
    );
  }

  Future<void> _copyKey(BuildContext context) => OmiClipboard.copy(context, apiKey.key, what: context.l10n.apiKey);

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Success header
          const Icon(Icons.check_circle, color: OmiColors.success, size: 40),
          const SizedBox(height: OmiSpacing.md),
          Text(l10n.apiKeyCreated, textAlign: TextAlign.center, style: OmiType.title3),
          const SizedBox(height: 6),
          Text(
            apiKey.name,
            textAlign: TextAlign.center,
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
          ),
          const SizedBox(height: OmiSpacing.xl),
          // Warning banner
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: OmiColors.warning.withValues(alpha: 0.1),
              borderRadius: OmiRadius.mdAll,
              border: Border.all(color: OmiColors.warning.withValues(alpha: 0.2)),
            ),
            child: Row(
              children: [
                const Icon(Icons.warning_amber_rounded, color: OmiColors.warning, size: 20),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: Text(
                    l10n.saveKeyWarning,
                    style: OmiType.footnote.copyWith(color: OmiColors.warning, fontWeight: FontWeight.w500),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: OmiSpacing.lg),
          // Key display (tap to copy)
          Material(
            color: OmiColors.surface2,
            borderRadius: OmiRadius.mdAll,
            child: InkWell(
              borderRadius: OmiRadius.mdAll,
              onTap: () => _copyKey(context),
              child: Padding(
                padding: const EdgeInsets.all(OmiSpacing.md),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            l10n.yourApiKey,
                            style: OmiType.caption.copyWith(
                              color: OmiColors.textTertiary,
                              fontWeight: FontWeight.w600,
                              letterSpacing: 0.5,
                            ),
                          ),
                        ),
                        const Icon(Icons.copy, size: 14, color: OmiColors.textTertiary),
                        const SizedBox(width: OmiSpacing.xxs),
                        Text(l10n.tapToCopy, style: OmiType.caption.copyWith(color: OmiColors.textTertiary)),
                      ],
                    ),
                    const SizedBox(height: OmiSpacing.sm),
                    SelectableText(
                      apiKey.key,
                      onTap: () => _copyKey(context),
                      style:
                          OmiType.subhead.copyWith(fontFamily: 'monospace', fontWeight: FontWeight.w500, height: 1.4),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 28),
          // Buttons
          Row(
            children: [
              Expanded(
                child: OmiButton.secondary(
                  label: l10n.copyKey,
                  icon: Icons.copy,
                  expand: true,
                  onPressed: () => _copyKey(context),
                ),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: OmiButton(label: l10n.done, expand: true, onPressed: () => Navigator.of(context).pop()),
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}

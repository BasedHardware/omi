import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class McpApiKeyListItem extends StatelessWidget {
  final McpApiKey apiKey;

  const McpApiKeyListItem({super.key, required this.apiKey});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
            child: const FaIcon(FontAwesomeIcons.key, color: OmiColors.textTertiary, size: 16),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  apiKey.name,
                  style: OmiType.callout.copyWith(fontWeight: FontWeight.w500),
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: OmiSpacing.xxs),
                Text(
                  apiKey.keyPrefix,
                  style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontFamily: 'monospace'),
                ),
              ],
            ),
          ),
          const SizedBox(width: OmiSpacing.sm),
          OmiButton.destructive(
            label: context.l10n.revoke,
            size: OmiButtonSize.compact,
            // Not `=>`: a returned future would spin the button while the dialog is open.
            onPressed: () {
              _confirmRevoke(context);
            },
          ),
        ],
      ),
    );
  }

  /// Revoking a key cannot be undone, so it is confirmed every time (docs/ux-contract.md §4).
  Future<void> _confirmRevoke(BuildContext context) async {
    final provider = Provider.of<McpProvider>(context, listen: false);
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.revokeKeyQuestion,
      message: context.l10n.revokeKeyConfirmation(apiKey.name),
      confirmLabel: context.l10n.revoke,
      destructive: true,
    );
    if (confirmed) provider.deleteKey(apiKey.id);
  }
}

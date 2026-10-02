import 'package:flutter/material.dart';

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
    return OmiSettingsRow(
      leading: const OmiSettingsIconTile(OmiLineGlyph.key),
      title: apiKey.name,
      subtitle: apiKey.keyPrefix,
      trailing: OmiIconButton(
        icon: const OmiLineIcon(OmiLineGlyph.trash),
        label: context.l10n.revoke,
        isDestructive: true,
        // Not `=>`: a returned future would spin the button while the dialog is open.
        onPressed: () {
          _confirmRevoke(context);
        },
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

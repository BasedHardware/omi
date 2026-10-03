import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/dev_api_key.dart';
import 'package:omi/providers/dev_api_key_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// One developer API key: name, prefix and creation date, its scopes, and Revoke.
///
/// A row inside the Developer API group (the group draws the card and the separators).
class DevApiKeyListItem extends StatelessWidget {
  final DevApiKey apiKey;

  const DevApiKeyListItem({super.key, required this.apiKey});

  /// "Read · Write", "Full Access" or "Read Only": what the key can do, for the row's subtitle.
  String _scopeLabel(BuildContext context, List<String>? scopes) {
    if (scopes == null || scopes.isEmpty) return context.l10n.readOnlyScope;

    final hasRead = scopes.any((s) => s.endsWith(':read'));
    final hasWrite = scopes.any((s) => s.endsWith(':write'));

    if (hasRead && hasWrite && scopes.length == 8) return context.l10n.fullAccessScope;
    return [
      if (hasRead) context.l10n.readScope,
      if (hasWrite) context.l10n.writeScope,
    ].join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    return OmiSettingsRow(
      leading: const OmiSettingsIconTile(OmiLineGlyph.key),
      title: apiKey.name,
      subtitle: '${apiKey.keyPrefix}*** · ${OmiDateFormat.of(context).date(apiKey.createdAt)}\n'
          '${_scopeLabel(context, apiKey.scopes)}',
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
    final provider = Provider.of<DevApiKeyProvider>(context, listen: false);
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

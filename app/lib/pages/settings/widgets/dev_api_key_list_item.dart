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

  List<Widget> _buildScopeChips(BuildContext context, List<String>? scopes) {
    if (scopes == null || scopes.isEmpty) {
      return [_buildChip(context.l10n.readOnlyScope)];
    }

    final hasRead = scopes.any((s) => s.endsWith(':read'));
    final hasWrite = scopes.any((s) => s.endsWith(':write'));

    if (hasRead && hasWrite && scopes.length == 8) {
      return [_buildChip(context.l10n.fullAccessScope)];
    }

    final chips = <Widget>[];
    if (hasRead) chips.add(_buildChip(context.l10n.readScope));
    if (hasWrite) chips.add(_buildChip(context.l10n.writeScope));

    return chips;
  }

  Widget _buildChip(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: OmiSpacing.xxs),
      decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
      child: Text(
        label,
        style: OmiType.caption.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(OmiSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(OmiSpacing.xs),
                decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
                child: const Icon(Icons.key, color: OmiColors.textTertiary, size: 18),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      apiKey.name,
                      style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: OmiSpacing.xxs),
                    Text(
                      '${apiKey.keyPrefix}***  •  ${OmiDateFormat.of(context).date(apiKey.createdAt)}',
                      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: OmiSpacing.xs),
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
          const SizedBox(height: OmiSpacing.sm),
          Wrap(spacing: OmiSpacing.xs, runSpacing: OmiSpacing.xs, children: _buildScopeChips(context, apiKey.scopes)),
        ],
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

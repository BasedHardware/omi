import 'package:flutter/material.dart';

import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Shows a newly created MCP key once, with Copy and Done.
class McpApiKeyCreatedDialog extends StatelessWidget {
  final McpApiKeyCreated apiKey;

  const McpApiKeyCreatedDialog({super.key, required this.apiKey});

  @override
  Widget build(BuildContext context) {
    return OmiAlertDialog(
      title: context.l10n.keyCreated,
      message: context.l10n.keyCreatedMessage,
      // SelectableText needs a Material ancestor inside the Cupertino dialog.
      content: Material(
        type: MaterialType.transparency,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(OmiSpacing.sm),
          decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
          child: SelectableText(apiKey.key, style: OmiType.footnote.copyWith(fontFamily: 'monospace')),
        ),
      ),
      actions: [
        OmiDialogAction(
          label: context.l10n.copy,
          onPressed: () => OmiClipboard.copy(context, apiKey.key, what: context.l10n.keyWord),
        ),
        OmiDialogAction(label: context.l10n.done, isDefault: true, onPressed: () => Navigator.of(context).pop()),
      ],
    );
  }
}

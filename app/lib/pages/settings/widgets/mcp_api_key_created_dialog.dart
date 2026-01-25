import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';

class McpApiKeyCreatedDialog extends StatelessWidget {
  final McpApiKeyCreated apiKey;

  const McpApiKeyCreatedDialog({super.key, required this.apiKey});

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(context.l10n.keyCreated),
      content: SingleChildScrollView(
        child: ListBody(
          children: <Widget>[
            Text(context.l10n.keyCreatedMessage),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surface,
                borderRadius: BorderRadius.circular(8),
              ),
              child: SelectableText(
                apiKey.key,
                style: const TextStyle(fontFamily: 'monospace'),
              ),
            ),
          ],
        ),
      ),
      actions: <Widget>[
        TextButton(
          child: Text(context.l10n.done),
          onPressed: () {
            Navigator.of(context).pop();
          },
        ),
        ElevatedButton(
          child: Text(context.l10n.copy),
          style: ElevatedButton.styleFrom(
            foregroundColor: Colors.white,
            backgroundColor: Theme.of(context).colorScheme.secondary,
          ),
          onPressed: () {
            Clipboard.setData(ClipboardData(text: apiKey.key));
            AppSnackbar.showSnackbar(context.l10n.copiedToClipboard(context.l10n.keyWord));
          },
        ),
      ],
    );
  }
}

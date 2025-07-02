import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';

class McpApiKeyCreatedDialog extends StatelessWidget {
  final McpApiKeyCreated apiKey;

  const McpApiKeyCreatedDialog({super.key, required this.apiKey});

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('API Key Created'),
      content: SingleChildScrollView(
        child: ListBody(
          children: <Widget>[
            const Text('Your new API key has been created. Please copy it now. You will not be able to see it again.'),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.grey.shade800,
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
          child: const Text('Copy'),
          onPressed: () {
            Clipboard.setData(ClipboardData(text: apiKey.key));
            AppSnackbar.showSnackbar('API Key copied to clipboard.');
          },
        ),
        ElevatedButton(
          child: const Text('Done'),
          onPressed: () {
            Navigator.of(context).pop();
          },
        ),
      ],
    );
  }
}

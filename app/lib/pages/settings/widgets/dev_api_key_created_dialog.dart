import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/dev_api_key.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';

class DevApiKeyCreatedDialog extends StatelessWidget {
  final DevApiKeyCreated apiKey;

  const DevApiKeyCreatedDialog({super.key, required this.apiKey});

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Developer Key Created'),
      content: SingleChildScrollView(
        child: ListBody(
          children: <Widget>[
            const Text(
                'Your new developer API key has been created. Please copy it now. You will not be able to see it again.'),
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
          child: const Text('Done'),
          onPressed: () {
            Navigator.of(context).pop();
          },
        ),
        ElevatedButton(
          child: const Text('Copy'),
          style: ElevatedButton.styleFrom(
            foregroundColor: Colors.white,
            backgroundColor: Theme.of(context).colorScheme.secondary,
          ),
          onPressed: () {
            Clipboard.setData(ClipboardData(text: apiKey.key));
            AppSnackbar.showSnackbar('Developer key copied to clipboard.');
          },
        ),
      ],
    );
  }
}

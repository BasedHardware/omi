import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:provider/provider.dart';

class McpApiKeyListItem extends StatelessWidget {
  final McpApiKey apiKey;

  const McpApiKeyListItem({super.key, required this.apiKey});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 2,
      color: Theme.of(context).colorScheme.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 0.0, vertical: 8.0),
        title: Text(
          apiKey.name,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Text(
          '${apiKey.keyPrefix}  •  ${DateFormat.yMMMd().format(apiKey.createdAt)}',
          style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
        ),
        trailing: TextButton(
          onPressed: () => _showDeleteConfirmation(context, apiKey),
          child: const Text('Revoke', style: TextStyle(color: Colors.redAccent)),
        ),
      ),
    );
  }

  void _showDeleteConfirmation(BuildContext context, McpApiKey apiKey) {
    showDialog(
      context: context,
      builder: (BuildContext dialogContext) {
        return AlertDialog(
          title: const Text('Revoke Key?'),
          content: Text('Are you sure you want to revoke the key "${apiKey.name}"? This action cannot be undone.'),
          actions: <Widget>[
            TextButton(
              child: const Text('Cancel'),
              onPressed: () => Navigator.of(dialogContext).pop(),
            ),
            TextButton(
              child: const Text('Revoke', style: TextStyle(color: Colors.red)),
              onPressed: () {
                Provider.of<McpProvider>(context, listen: false).deleteKey(apiKey.id);
                Navigator.of(dialogContext).pop();
              },
            ),
          ],
        );
      },
    );
  }
}

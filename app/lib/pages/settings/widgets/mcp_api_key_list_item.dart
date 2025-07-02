import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:provider/provider.dart';
import 'package:timeago/timeago.dart' as timeago;

class McpApiKeyListItem extends StatelessWidget {
  final McpApiKey apiKey;

  const McpApiKeyListItem({super.key, required this.apiKey});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
      child: ListTile(
        title: Text(apiKey.name),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 4),
            Text('Key: ${apiKey.keyPrefix}...'),
            const SizedBox(height: 4),
            Text('Created: ${DateFormat.yMMMd().format(apiKey.createdAt)}'),
            const SizedBox(height: 4),
            Text(
                'Last used: ${apiKey.lastUsedAt == null ? 'Never' : timeago.format(apiKey.lastUsedAt!)}'),
          ],
        ),
        trailing: IconButton(
          icon: const Icon(Icons.delete, color: Colors.redAccent),
          onPressed: () => _confirmDelete(context),
        ),
      ),
    );
  }

  void _confirmDelete(BuildContext context) {
    showDialog(
      context: context,
      builder: (BuildContext dialogContext) {
        return AlertDialog(
          title: const Text('Delete API Key?'),
          content: Text('Are you sure you want to delete the key "${apiKey.name}"? This action cannot be undone.'),
          actions: <Widget>[
            TextButton(
              child: const Text('Cancel'),
              onPressed: () {
                Navigator.of(dialogContext).pop();
              },
            ),
            TextButton(
              child: const Text('Delete', style: TextStyle(color: Colors.red)),
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

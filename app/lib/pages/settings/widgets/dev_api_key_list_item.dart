import 'package:flutter/material.dart';

import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/dev_api_key.dart';
import 'package:omi/providers/dev_api_key_provider.dart';

class DevApiKeyListItem extends StatelessWidget {
  final DevApiKey apiKey;

  const DevApiKeyListItem({super.key, required this.apiKey});

  List<Widget> _buildScopeChips(List<String>? scopes) {
    if (scopes == null || scopes.isEmpty) {
      return [
        _buildChip('Read Only', const Color(0xFF3B82F6)),
      ];
    }

    final hasRead = scopes.any((s) => s.endsWith(':read'));
    final hasWrite = scopes.any((s) => s.endsWith(':write'));

    if (hasRead && hasWrite && scopes.length == 6) {
      return [_buildChip('Full Access', const Color(0xFF10B981))];
    }

    final chips = <Widget>[];
    if (hasRead) chips.add(_buildChip('Read', const Color(0xFF3B82F6)));
    if (hasWrite) chips.add(_buildChip('Write', const Color(0xFF8B5CF6)));

    return chips;
  }

  Widget _buildChip(String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1A),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF2C2C2E), width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: const Color(0xFF8B5CF6).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(Icons.key, color: Color(0xFF8B5CF6), size: 18),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      apiKey.name,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${apiKey.keyPrefix}***  •  ${DateFormat.yMMMd().format(apiKey.createdAt)}',
                      style: const TextStyle(
                        color: Color(0xFF8E8E93),
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),
              GestureDetector(
                onTap: () => _showDeleteConfirmation(context, apiKey),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: const Color(0xFFEF4444).withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: const Text(
                    'Revoke',
                    style: TextStyle(
                      color: Color(0xFFEF4444),
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _buildScopeChips(apiKey.scopes),
          ),
        ],
      ),
    );
  }

  void _showDeleteConfirmation(BuildContext context, DevApiKey apiKey) {
    showDialog(
      context: context,
      builder: (BuildContext dialogContext) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Text(
            'Revoke Key?',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
          ),
          content: Text(
            'Are you sure you want to revoke the key "${apiKey.name}"? This action cannot be undone.',
            style: TextStyle(color: Colors.grey.shade400),
          ),
          actions: <Widget>[
            TextButton(
              child: Text('Cancel', style: TextStyle(color: Colors.grey.shade400)),
              onPressed: () => Navigator.of(dialogContext).pop(),
            ),
            TextButton(
              child: const Text('Revoke', style: TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w600)),
              onPressed: () {
                Provider.of<DevApiKeyProvider>(context, listen: false).deleteKey(apiKey.id);
                Navigator.of(dialogContext).pop();
              },
            ),
          ],
        );
      },
    );
  }
}

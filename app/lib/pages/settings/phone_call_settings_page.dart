import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/widgets/dialog.dart';

class PhoneCallSettingsPage extends StatelessWidget {
  const PhoneCallSettingsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('Phone Call Settings'),
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
      ),
      body: Consumer<PhoneCallProvider>(
        builder: (context, provider, _) {
          return Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Your Verified Numbers',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: Colors.white),
                ),
                const SizedBox(height: 6),
                Text(
                  "When you call someone, they'll see this number on their phone",
                  style: TextStyle(fontSize: 14, color: Colors.grey[500]),
                ),
                const SizedBox(height: 24),
                if (provider.verifiedNumbers.isEmpty)
                  _buildEmptyState()
                else
                  ...provider.verifiedNumbers.map(
                    (number) => _buildNumberRow(context, provider, number.id, number.phoneNumber, number.verifiedAt),
                  ),
                const Spacer(),
                if (provider.verifiedNumbers.isNotEmpty)
                  _buildDeleteButton(
                      context, provider, provider.verifiedNumbers.first.id, provider.verifiedNumbers.first.phoneNumber),
                SizedBox(height: MediaQuery.of(context).viewPadding.bottom),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildEmptyState() {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24),
      child: Center(
        child: Text(
          'No verified numbers',
          style: TextStyle(fontSize: 15, color: Colors.grey[600]),
        ),
      ),
    );
  }

  Widget _buildNumberRow(
      BuildContext context, PhoneCallProvider provider, String id, String phoneNumber, String verifiedAt) {
    var timeAgo = _formatVerifiedAt(verifiedAt);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: const Color(0xFF2A2A2E),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(Icons.phone, color: Colors.grey[400], size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(phoneNumber,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500, color: Colors.white)),
                const SizedBox(height: 2),
                Text(timeAgo, style: TextStyle(fontSize: 13, color: Colors.grey[500])),
              ],
            ),
          ),
          Icon(Icons.check_circle, color: Colors.green[600], size: 24),
        ],
      ),
    );
  }

  Widget _buildDeleteButton(BuildContext context, PhoneCallProvider provider, String id, String phoneNumber) {
    return GestureDetector(
      onTap: () => _confirmDelete(context, provider, id, phoneNumber),
      child: Container(
        width: double.infinity,
        height: 56,
        decoration: BoxDecoration(
          color: Colors.red[900]!.withValues(alpha: 0.3),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.delete_outline, color: Colors.red[400], size: 20),
            const SizedBox(width: 8),
            Text(
              'Delete Phone Number',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500, color: Colors.red[400]),
            ),
          ],
        ),
      ),
    );
  }

  void _confirmDelete(BuildContext context, PhoneCallProvider provider, String id, String phoneNumber) {
    showDialog(
      context: context,
      builder: (ctx) => getDialog(
        ctx,
        () => Navigator.pop(ctx),
        () async {
          Navigator.pop(ctx);
          await provider.deleteNumber(id);
        },
        'Delete $phoneNumber?',
        "You'll need to verify again to make calls",
        okButtonText: 'Delete',
      ),
    );
  }

  String _formatVerifiedAt(String verifiedAt) {
    try {
      var dt = DateTime.parse(verifiedAt);
      var diff = DateTime.now().difference(dt);
      if (diff.inMinutes < 60) return 'Verified ${diff.inMinutes}m ago';
      if (diff.inHours < 24) return 'Verified ${diff.inHours}h ago';
      if (diff.inDays < 7) return 'Verified ${diff.inDays}d ago';
      return 'Verified on ${dt.month}/${dt.day}/${dt.year}';
    } catch (_) {
      return 'Verified';
    }
  }
}

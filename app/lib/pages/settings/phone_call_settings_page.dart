import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/dialog.dart';

class PhoneCallSettingsPage extends StatelessWidget {
  const PhoneCallSettingsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: Text(context.l10n.phoneCallSettingsTitle),
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
                Text(
                  context.l10n.yourVerifiedNumbers,
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: Colors.white),
                ),
                const SizedBox(height: 6),
                Text(
                  context.l10n.verifiedNumbersDescription,
                  style: TextStyle(fontSize: 14, color: Colors.grey[500]),
                ),
                const SizedBox(height: 24),
                if (provider.verifiedNumbers.isEmpty)
                  _buildEmptyState(context)
                else
                  ...provider.verifiedNumbers.map(
                    (number) => _buildNumberRow(context, provider, number.id, number.phoneNumber, number.verifiedAt),
                  ),
                const Spacer(),
                SizedBox(height: MediaQuery.of(context).viewPadding.bottom),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24),
      child: Center(
        child: Text(
          context.l10n.noVerifiedNumbers,
          style: TextStyle(fontSize: 15, color: Colors.grey[600]),
        ),
      ),
    );
  }

  Widget _buildNumberRow(
      BuildContext context, PhoneCallProvider provider, String id, String phoneNumber, String verifiedAt) {
    var timeAgo = _formatVerifiedAt(context, verifiedAt);
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
          GestureDetector(
            onTap: () => _confirmDelete(context, provider, id, phoneNumber),
            child: Icon(Icons.delete_outline, color: Colors.red[400], size: 22),
          ),
        ],
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
        context.l10n.deletePhoneNumberConfirm(phoneNumber),
        context.l10n.deletePhoneNumberWarning,
        okButtonText: context.l10n.phoneDeleteButton,
      ),
    );
  }

  String _formatVerifiedAt(BuildContext context, String verifiedAt) {
    try {
      var dt = DateTime.parse(verifiedAt);
      var diff = DateTime.now().difference(dt);
      if (diff.inMinutes < 60) return context.l10n.verifiedMinutesAgo(diff.inMinutes);
      if (diff.inHours < 24) return context.l10n.verifiedHoursAgo(diff.inHours);
      if (diff.inDays < 7) return context.l10n.verifiedDaysAgo(diff.inDays);
      return context.l10n.verifiedOnDate('${dt.month}/${dt.day}/${dt.year}');
    } catch (_) {
      return context.l10n.verifiedFallback;
    }
  }
}

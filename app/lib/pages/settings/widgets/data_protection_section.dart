import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/e2ee_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

// TODO(atlas): Move these to ARB l10n files
const _kEnableE2ee = 'Enable E2EE';
const _kRecoveryKey = 'Recovery Key';
const _kSaveKeyMessage = 'Save this key somewhere safe. You will need it to recover your encrypted memories if you switch devices. Without this key, E2E encrypted data is unrecoverable.';
const _kCopyToClipboard = 'Copy to Clipboard';
const _kSavedMyKey = "I've Saved My Key";
const _kShowRecoveryKey = 'Show Recovery Key';
const _kKeyWarning = '⚠️ If you lose your recovery key, your data cannot be recovered.';
const _kBackupReminder = 'Make sure to back up your key after enabling.';

extension StringExtension on String {
  String capitalize() {
    if (isEmpty) {
      return this;
    }
    return "${this[0].toUpperCase()}${substring(1)}";
  }
}

class DataProtectionSection extends StatefulWidget {
  const DataProtectionSection({super.key});

  @override
  State<DataProtectionSection> createState() => _DataProtectionSectionState();
}

class _DataProtectionSectionState extends State<DataProtectionSection> {
  @override
  void initState() {
    super.initState();
  }

  /// Show dialog to enable E2EE with warnings about key backup.
  void _showE2eeEnableDialog(BuildContext context) {
    final provider = Provider.of<UserProvider>(context, listen: false);

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF2c2c2e),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        title: Row(
          children: [
            const Icon(Icons.lock_person_outlined, color: Colors.white),
            const SizedBox(width: 10),
            Text(context.l10n.maximumSecurityE2ee,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ],
        ),
        content: RichText(
          text: TextSpan(
            style: TextStyle(color: Colors.white.withOpacity(0.8), height: 1.5, fontSize: 15),
            children: [
              const TextSpan(text: 'End-to-end encryption provides the highest level of data protection:\n\n'),
              const TextSpan(
                text: '🔒 Memories: ',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              const TextSpan(text: 'Encrypted on your device before reaching the server. Only you can read them.\n\n'),
              const TextSpan(
                text: '🔐 Conversations, chat & other data: ',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              const TextSpan(
                  text:
                      'Encrypted at rest on the server. The server processes audio for transcription but stored data is encrypted and cannot be read at rest.\n\n'),
              TextSpan(
                text: '$_kKeyWarning\n',
                style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.orangeAccent),
              ),
              const TextSpan(
                text: _kBackupReminder,
                style: TextStyle(fontStyle: FontStyle.italic),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child:
                Text(context.l10n.ok, style: const TextStyle(color: Colors.grey, fontWeight: FontWeight.bold)),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              _enableE2ee(context, provider);
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.deepPurple,
              foregroundColor: Colors.white,
            ),
            child: const Text(_kEnableE2ee),
          ),
        ],
      ),
    );
  }

  /// Generate key and start migration to e2ee level.
  Future<void> _enableE2ee(BuildContext context, UserProvider provider) async {
    try {
      final key = await provider.enableE2ee();
      if (!mounted) return;
      _showRecoveryKeyDialog(context, key);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to enable E2EE: $e'), backgroundColor: Colors.red),
      );
    }
  }

  /// Show the recovery key after E2EE is enabled.
  void _showRecoveryKeyDialog(BuildContext context, String key) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF2c2c2e),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        title: const Row(
          children: [
            Icon(Icons.key, color: Colors.orangeAccent),
            SizedBox(width: 10),
            Text(_kRecoveryKey, style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              _kSaveKeyMessage,
              style: TextStyle(color: Colors.white.withOpacity(0.8), height: 1.4),
            ),
            const SizedBox(height: 16),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.black26,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.deepPurple.shade300),
              ),
              child: SelectableText(
                key,
                style: const TextStyle(
                  color: Colors.white,
                  fontFamily: 'monospace',
                  fontSize: 12,
                ),
              ),
            ),
            const SizedBox(height: 12),
            Center(
              child: TextButton.icon(
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: key));
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Key copied to clipboard')),
                  );
                },
                icon: const Icon(Icons.copy, size: 16, color: Colors.deepPurple),
                label: const Text(_kCopyToClipboard, style: TextStyle(color: Colors.deepPurple)),
              ),
            ),
          ],
        ),
        actions: [
          ElevatedButton(
            onPressed: () => Navigator.of(ctx).pop(),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.deepPurple,
              foregroundColor: Colors.white,
            ),
            child: const Text(_kSavedMyKey),
          ),
        ],
      ),
    );
  }

  /// Show recovery key for an already-enabled E2EE setup.
  void _showExportKeyDialog(BuildContext context) async {
    final key = await E2eeService().exportKey();
    if (key == null || !mounted) return;
    _showRecoveryKeyDialog(context, key);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<UserProvider>(
      builder: (context, provider, child) {
        final isMigrating = provider.isMigrating;
        final migrationFailed = provider.migrationFailed;
        final isE2ee = provider.isE2eeEnabled;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (isMigrating || migrationFailed) _buildMigrationStatus(provider),
            if (isMigrating)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.only(bottom: 16, left: 8, right: 8),
                child: Text(
                  context.l10n.migrationInProgressMessage,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.secondary.withOpacity(0.9),
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ),
            _buildDefaultProtectionCard(context, isActive: !isE2ee),
            _buildE2eeCard(context, isActive: isE2ee),
            if (isE2ee) ...[
              const SizedBox(height: 8),
              _buildKeyManagementRow(context),
            ],
            const SizedBox(height: 12),
            _buildInfoRow(
              Icons.shield_outlined,
              context.l10n.dataAlwaysEncrypted,
            ),
          ],
        );
      },
    );
  }

  Widget _buildMigrationStatus(UserProvider provider) {
    if (provider.migrationFailed) {
      return Container(
        padding: const EdgeInsets.all(16),
        margin: const EdgeInsets.only(bottom: 24),
        decoration: BoxDecoration(
          color: Colors.red.withOpacity(0.15),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.red.shade300),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.error_outline, color: Colors.red.shade300, size: 20),
                const SizedBox(width: 8),
                Text(
                  context.l10n.migrationFailed,
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              provider.migrationMessage,
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey.shade300, fontSize: 14),
            ),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: () {
                provider.updateDataProtectionLevel(provider.targetLevel);
              },
              icon: const Icon(Icons.refresh),
              label: Text(context.l10n.retry),
              style: ElevatedButton.styleFrom(
                backgroundColor: Theme.of(context).colorScheme.secondary,
                foregroundColor: Colors.white,
              ),
            )
          ],
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(16),
      margin: const EdgeInsets.only(bottom: 24),
      decoration: BoxDecoration(
        color: Color(0xFF35343B).withOpacity(0.5),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.deepPurple.shade300),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.migratingFromTo(provider.sourceLevel.capitalize(), provider.targetLevel.capitalize()),
            style: const TextStyle(color: Colors.white, fontSize: 16, height: 1.4),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: LinearProgressIndicator(
                  value: provider.migrationTotalCount > 0
                      ? provider.migrationProcessedCount / provider.migrationTotalCount
                      : 0.0,
                  backgroundColor: Colors.grey.shade700,
                  color: Colors.deepPurple,
                  minHeight: 6,
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
              const SizedBox(width: 12),
              Text(
                provider.migrationTotalCount > 0
                    ? '${(provider.migrationProcessedCount / provider.migrationTotalCount * 100).toInt()}%'
                    : '0%',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                provider.migrationETA,
                style: const TextStyle(color: Colors.grey, fontSize: 12),
              ),
              Text(
                context.l10n.objectsCount(
                    provider.migrationProcessedCount.toString(), provider.migrationTotalCount.toString()),
                style: const TextStyle(color: Colors.grey, fontSize: 12),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDefaultProtectionCard(BuildContext context, {required bool isActive}) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isActive ? Colors.deepPurple.withOpacity(0.15) : const Color(0xFF1A1A1A),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isActive ? Theme.of(context).colorScheme.secondary : const Color(0xFF35343B),
          width: isActive ? 1.5 : 1.0,
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.verified_user_outlined,
            color: isActive ? Theme.of(context).colorScheme.secondary : Colors.grey.shade400,
            size: 28,
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      context.l10n.secureEncryption,
                      style: const TextStyle(
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                        fontSize: 16,
                      ),
                    ),
                    if (isActive) ...[
                      const SizedBox(width: 8),
                      const Icon(Icons.check_circle, color: Colors.green, size: 18),
                    ],
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  context.l10n.secureEncryptionDescription,
                  style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildE2eeCard(BuildContext context, {required bool isActive}) {
    return GestureDetector(
      onTap: isActive ? null : () => _showE2eeEnableDialog(context),
      child: Container(
        padding: const EdgeInsets.all(16),
        margin: const EdgeInsets.only(top: 12),
        decoration: BoxDecoration(
          color: isActive ? Colors.deepPurple.withOpacity(0.15) : const Color(0xFF1A1A1A),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isActive ? Colors.deepPurple : const Color(0xFF35343B),
            width: isActive ? 1.5 : 1.0,
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              Icons.lock_outline,
              color: isActive ? Colors.deepPurple : Colors.grey.shade400,
              size: 28,
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        context.l10n.endToEndEncryption,
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                          fontSize: 16,
                        ),
                      ),
                      const SizedBox(width: 8),
                      if (isActive)
                        const Icon(Icons.check_circle, color: Colors.green, size: 18)
                      else
                        Icon(Icons.arrow_forward_ios, color: Colors.grey.shade600, size: 14),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Maximum protection — memories encrypted on-device, all other data encrypted at rest',
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildKeyManagementRow(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4.0),
      child: Row(
        children: [
          TextButton.icon(
            onPressed: () => _showExportKeyDialog(context),
            icon: const Icon(Icons.key, size: 16, color: Colors.deepPurple),
            label: const Text(_kShowRecoveryKey, style: TextStyle(color: Colors.deepPurple, fontSize: 13)),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoRow(IconData icon, String text) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4.0, vertical: 4.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: Colors.grey, size: 16),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(color: Colors.grey, fontSize: 14, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}

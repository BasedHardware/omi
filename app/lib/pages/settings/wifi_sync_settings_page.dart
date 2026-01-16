import 'package:flutter/material.dart';

import 'package:omi/services/services.dart';
import 'package:omi/utils/l10n_extensions.dart';

class WifiSyncSettingsPage extends StatefulWidget {
  final String? initialSsid;
  final String? initialPassword;
  final Function(String ssid, String password)? onCredentialsSaved;
  final Function()? onCredentialsCleared;

  const WifiSyncSettingsPage({
    super.key,
    this.initialSsid,
    this.initialPassword,
    this.onCredentialsSaved,
    this.onCredentialsCleared,
  });

  @override
  State<WifiSyncSettingsPage> createState() => _WifiSyncSettingsPageState();
}

class _WifiSyncSettingsPageState extends State<WifiSyncSettingsPage> {
  late TextEditingController _ssidController;
  late TextEditingController _passwordController;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    _ssidController = TextEditingController(text: widget.initialSsid ?? '');
    _passwordController = TextEditingController(text: widget.initialPassword ?? '');
  }

  @override
  void dispose() {
    _ssidController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _saveCredentials() async {
    final ssid = _ssidController.text.trim();
    final password = _passwordController.text;

    if (ssid.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(context.l10n.pleaseEnterHotspotName)),
      );
      return;
    }

    setState(() => _isSaving = true);

    try {
      final walService = ServiceManager.instance().wal;
      final syncs = walService.getSyncs();
      await syncs.sdcard.setWifiCredentials(ssid, password);

      widget.onCredentialsSaved?.call(ssid, password);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.wifiCredentialsSaved)),
        );
        Navigator.pop(context, true);
      }
    } finally {
      if (mounted) {
        setState(() => _isSaving = false);
      }
    }
  }

  Future<void> _clearCredentials() async {
    final walService = ServiceManager.instance().wal;
    final syncs = walService.getSyncs();
    await syncs.sdcard.clearWifiCredentials();

    widget.onCredentialsCleared?.call();

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(context.l10n.wifiCredentialsCleared)),
      );
      Navigator.pop(context, true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasExistingCredentials = widget.initialSsid != null && widget.initialSsid!.isNotEmpty;

    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: Text(context.l10n.wifiSyncSettings),
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Info box
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.blue.withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.blue.withOpacity(0.3)),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.info_outline, color: Colors.blue.shade300, size: 22),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.l10n.enterHotspotCredentials,
                          style: TextStyle(
                            color: Colors.blue.shade200,
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          context.l10n.wifiSyncUsesHotspot,
                          style: TextStyle(
                            color: Colors.blue.shade300,
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 28),

            // SSID Field
            Text(
              context.l10n.hotspotNameSsid,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _ssidController,
              style: const TextStyle(color: Colors.white),
              decoration: InputDecoration(
                hintText: context.l10n.exampleIphoneHotspot,
                hintStyle: TextStyle(color: Colors.grey.shade600),
                filled: true,
                fillColor: const Color(0xFF2A2A2E),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide.none,
                ),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
              ),
            ),
            const SizedBox(height: 20),

            // Password Field
            Text(
              context.l10n.password,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _passwordController,
              obscureText: true,
              style: const TextStyle(color: Colors.white),
              decoration: InputDecoration(
                hintText: context.l10n.enterHotspotPassword,
                hintStyle: TextStyle(color: Colors.grey.shade600),
                filled: true,
                fillColor: const Color(0xFF2A2A2E),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide.none,
                ),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
              ),
            ),
            const SizedBox(height: 32),

            // Save Button
            SizedBox(
              width: double.infinity,
              height: 52,
              child: ElevatedButton(
                onPressed: _isSaving ? null : _saveCredentials,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: Colors.black,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: _isSaving
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black),
                      )
                    : Text(
                        context.l10n.saveCredentials,
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                      ),
              ),
            ),

            // Clear button (only show if credentials exist)
            if (hasExistingCredentials) ...[
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: TextButton(
                  onPressed: _clearCredentials,
                  child: Text(
                    context.l10n.clearCredentials,
                    style: TextStyle(color: Colors.red.shade400, fontSize: 14),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

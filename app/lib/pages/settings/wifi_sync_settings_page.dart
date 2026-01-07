import 'package:flutter/material.dart';
import 'package:omi/services/devices/wifi_sync_error.dart';
import 'package:omi/services/services.dart';

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
  String? _ssidError;
  String? _passwordError;

  @override
  void initState() {
    super.initState();
    _ssidController = TextEditingController(text: widget.initialSsid ?? '');
    _passwordController = TextEditingController(text: widget.initialPassword ?? '');

    // Add listeners for real-time validation
    _ssidController.addListener(_validateSsid);
    _passwordController.addListener(_validatePassword);
  }

  @override
  void dispose() {
    _ssidController.removeListener(_validateSsid);
    _passwordController.removeListener(_validatePassword);
    _ssidController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  void _validateSsid() {
    final ssid = _ssidController.text.trim();
    final error = WifiCredentialsValidator.validateSsid(ssid);
    if (_ssidError != error) {
      setState(() => _ssidError = error);
    }
  }

  void _validatePassword() {
    final password = _passwordController.text;
    final error = WifiCredentialsValidator.validatePassword(password);
    if (_passwordError != error) {
      setState(() => _passwordError = error);
    }
  }

  Future<void> _saveCredentials() async {
    final ssid = _ssidController.text.trim();
    final password = _passwordController.text;

    // Validate before saving
    final ssidError = WifiCredentialsValidator.validateSsid(ssid);
    final passwordError = WifiCredentialsValidator.validatePassword(password);

    setState(() {
      _ssidError = ssidError;
      _passwordError = passwordError;
    });

    if (ssidError != null || passwordError != null) {
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
          const SnackBar(
            content: Text('WiFi credentials saved'),
            backgroundColor: Colors.green,
          ),
        );
        Navigator.pop(context, true);
      }
    } on WifiSyncException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(e.message),
            backgroundColor: Colors.red,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to save credentials: $e'),
            backgroundColor: Colors.red,
          ),
        );
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
        const SnackBar(content: Text('WiFi credentials cleared')),
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
        title: const Text('WiFi Sync Settings'),
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
                          'Enter your phone\'s hotspot credentials',
                          style: TextStyle(
                            color: Colors.blue.shade200,
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'WiFi sync uses your phone as a hotspot. Find your hotspot name and password in Settings > Personal Hotspot.',
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
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Hotspot Name (SSID)',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  '${_ssidController.text.length}/${WifiCredentialsValidator.maxSsidLength}',
                  style: TextStyle(
                    color: _ssidError != null ? Colors.red.shade400 : Colors.grey.shade500,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _ssidController,
              style: const TextStyle(color: Colors.white),
              maxLength: WifiCredentialsValidator.maxSsidLength,
              decoration: InputDecoration(
                hintText: 'e.g. iPhone Hotspot',
                hintStyle: TextStyle(color: Colors.grey.shade600),
                filled: true,
                fillColor: const Color(0xFF2A2A2E),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: _ssidError != null ? BorderSide(color: Colors.red.shade400, width: 1) : BorderSide.none,
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: _ssidError != null ? BorderSide(color: Colors.red.shade400, width: 1) : BorderSide.none,
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(
                    color: _ssidError != null ? Colors.red.shade400 : Colors.blue.shade400,
                    width: 1,
                  ),
                ),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                counterText: '', // Hide default counter
              ),
            ),
            if (_ssidError != null) ...[
              const SizedBox(height: 4),
              Text(
                _ssidError!,
                style: TextStyle(color: Colors.red.shade400, fontSize: 12),
              ),
            ],
            const SizedBox(height: 20),

            // Password Field
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Password',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  '${_passwordController.text.length}/${WifiCredentialsValidator.maxPasswordLength}',
                  style: TextStyle(
                    color: _passwordError != null ? Colors.red.shade400 : Colors.grey.shade500,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _passwordController,
              obscureText: true,
              style: const TextStyle(color: Colors.white),
              maxLength: WifiCredentialsValidator.maxPasswordLength,
              decoration: InputDecoration(
                hintText: 'Enter hotspot password',
                hintStyle: TextStyle(color: Colors.grey.shade600),
                filled: true,
                fillColor: const Color(0xFF2A2A2E),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide:
                      _passwordError != null ? BorderSide(color: Colors.red.shade400, width: 1) : BorderSide.none,
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide:
                      _passwordError != null ? BorderSide(color: Colors.red.shade400, width: 1) : BorderSide.none,
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(
                    color: _passwordError != null ? Colors.red.shade400 : Colors.blue.shade400,
                    width: 1,
                  ),
                ),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                counterText: '',
              ),
            ),
            if (_passwordError != null) ...[
              const SizedBox(height: 4),
              Text(
                _passwordError!,
                style: TextStyle(color: Colors.red.shade400, fontSize: 12),
              ),
            ],
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
                    : const Text(
                        'Save Credentials',
                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
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
                    'Clear Credentials',
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

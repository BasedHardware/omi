import 'package:flutter/material.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';

class CustomBackendUrlDialog extends StatefulWidget {
  const CustomBackendUrlDialog({super.key});

  static Future<bool?> show(BuildContext context) {
    return showDialog<bool>(
      context: context,
      builder: (context) => const CustomBackendUrlDialog(),
    );
  }

  @override
  State<CustomBackendUrlDialog> createState() => _CustomBackendUrlDialogState();
}

class _CustomBackendUrlDialogState extends State<CustomBackendUrlDialog> {
  late final TextEditingController _controller;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: SharedPreferencesUtil().customBackendUrl);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  String? _validateUrl(String url) {
    if (url.isEmpty) return null;
    final uri = Uri.tryParse(url);
    if (uri == null || uri.host.isEmpty || (uri.scheme != 'http' && uri.scheme != 'https')) {
      return 'Please enter a valid HTTP or HTTPS URL';
    }
    return null;
  }

  void _onSave() {
    final raw = _controller.text.trim();
    if (raw.isEmpty) {
      _onReset();
      return;
    }

    final validationError = _validateUrl(raw);
    if (validationError != null) {
      setState(() => _errorMessage = validationError);
      return;
    }

    var normalized = raw;
    if (!normalized.endsWith('/')) {
      normalized = '$normalized/';
    }

    SharedPreferencesUtil().customBackendUrl = normalized;
    Env.overrideApiBaseUrl(normalized);
    _showMessage('Backend URL set to $normalized');
    Navigator.of(context).pop(true);
  }

  void _onReset() {
    SharedPreferencesUtil().customBackendUrl = '';
    Env.resetApiBaseUrlOverride();
    _showMessage('Backend URL reset to default');
    Navigator.of(context).pop(true);
  }

  void _showMessage(String message) {
    if (globalNavigatorKey.currentState != null) {
      AppSnackbar.showSnackbar(message);
    } else {
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        SnackBar(content: Text(message), duration: const Duration(seconds: 2)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final defaultUrl = Env.defaultApiBaseUrl;
    final isCustom = SharedPreferencesUtil().customBackendUrl.isNotEmpty;

    return AlertDialog(
      backgroundColor: const Color(0xFF1C1C1E),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: const Text(
        'Custom Backend URL',
        style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
      ),
      content: SizedBox(
        width: double.maxFinite,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Configure a custom backend URL to connect Omi to a self-hosted instance.',
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Default Backend:',
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 12, fontWeight: FontWeight.w500),
                  ),
                  const SizedBox(height: 2),
                  SelectableText(
                    defaultUrl,
                    style: const TextStyle(color: Colors.white, fontSize: 13, fontFamily: 'monospace'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _controller,
              keyboardType: TextInputType.url,
              autocorrect: false,
              enableSuggestions: false,
              style: const TextStyle(color: Colors.white, fontSize: 15),
              decoration: InputDecoration(
                labelText: 'Backend URL',
                hintText: 'https://api.example.com/',
                errorText: _errorMessage,
                labelStyle: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                hintStyle: TextStyle(color: Colors.grey.shade600, fontSize: 14),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                filled: true,
                fillColor: const Color(0xFF2C2C2E),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: BorderSide.none,
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: Colors.white12, width: 1),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: Colors.white38, width: 1),
                ),
                errorBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: Colors.redAccent, width: 1),
                ),
                focusedErrorBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: Colors.redAccent, width: 1),
                ),
              ),
              onChanged: (_) {
                if (_errorMessage != null) {
                  setState(() => _errorMessage = null);
                }
              },
            ),
            const SizedBox(height: 12),
            Text(
              'Self-hosted backends typically require LOCAL_DEVELOPMENT=true on the server to bypass Firebase auth verification.',
              style: TextStyle(color: Colors.grey.shade500, fontSize: 12, height: 1.3),
            ),
          ],
        ),
      ),
      actionsPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      actions: [
        if (isCustom)
          TextButton(
            onPressed: _onReset,
            child: const Text(
              'Reset',
              style: TextStyle(color: Color(0xFFFF453A), fontWeight: FontWeight.w500),
            ),
          ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text(
            'Cancel',
            style: TextStyle(color: Color(0xFF8E8E93)),
          ),
        ),
        ElevatedButton(
          onPressed: _onSave,
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.white,
            foregroundColor: Colors.black,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          ),
          child: const Text(
            'Save',
            style: TextStyle(fontWeight: FontWeight.w600),
          ),
        ),
      ],
    );
  }
}

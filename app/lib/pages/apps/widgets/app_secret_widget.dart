import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';

class AppSecretWidget extends StatefulWidget {
  final App app;
  final Function(String) onSecretUpdated;

  const AppSecretWidget({
    Key? key,
    required this.app,
    required this.onSecretUpdated,
  }) : super(key: key);

  @override
  State<AppSecretWidget> createState() => _AppSecretWidgetState();
}

class _AppSecretWidgetState extends State<AppSecretWidget> {
  bool _isSecretVisible = false;
  bool _isLoading = false;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'App Secret',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'This secret is used to authenticate your webhook requests. Keep it secure and never share it.',
          style: TextStyle(
            color: Colors.grey,
            fontSize: 14,
          ),
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 6.0),
          margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
          decoration: BoxDecoration(
            color: Colors.grey.shade800,
            borderRadius: BorderRadius.circular(10.0),
          ),
          width: double.infinity,
          child: Row(
            children: [
              Expanded(
                child: Text(
                  _isSecretVisible ? (widget.app.appSecret ?? 'No secret generated') : '••••••••••••••••',
                  style: const TextStyle(
                    color: Colors.white,
                    fontFamily: 'monospace',
                  ),
                ),
              ),
              IconButton(
                icon: Icon(
                  _isSecretVisible ? Icons.visibility_off : Icons.visibility,
                  color: Colors.grey,
                ),
                onPressed: () {
                  setState(() {
                    _isSecretVisible = !_isSecretVisible;
                  });
                },
              ),
              IconButton(
                icon: const Icon(
                  Icons.copy,
                  color: Colors.grey,
                ),
                onPressed: () {
                  if (widget.app.appSecret != null) {
                    Clipboard.setData(ClipboardData(text: widget.app.appSecret!));
                    AppSnackbar.showSnackbar('Secret copied to clipboard');
                  }
                },
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        ElevatedButton(
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.red.shade800,
          ),
          onPressed: _isLoading
              ? null
              : () async {
                  setState(() {
                    _isLoading = true;
                  });
                  final newSecret = await revokeAppSecret(widget.app.id);
                  if (newSecret != null) {
                    widget.onSecretUpdated(newSecret);
                    AppSnackbar.showSnackbar('App secret revoked and new one generated');
                  } else {
                    AppSnackbar.showSnackbarError('Failed to revoke app secret');
                  }
                  setState(() {
                    _isLoading = false;
                  });
                },
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_isLoading)
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                )
              else
                const Icon(Icons.refresh),
              const SizedBox(width: 8),
              const Text('Revoke & Generate New Secret'),
            ],
          ),
        ),
      ],
    );
  }
} 
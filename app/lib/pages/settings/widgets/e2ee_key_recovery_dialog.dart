import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/user_provider.dart';

class E2eeKeyRecoveryDialog extends StatefulWidget {
  const E2eeKeyRecoveryDialog({super.key});

  @override
  State<E2eeKeyRecoveryDialog> createState() => _E2eeKeyRecoveryDialogState();
}

class _E2eeKeyRecoveryDialogState extends State<E2eeKeyRecoveryDialog> {
  final _controller = TextEditingController();
  bool _isRecovering = false;
  String? _error;
  bool _success = false;
  bool _showLostKeyInfo = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _recover() async {
    final key = _controller.text.trim();
    if (key.isEmpty) return;

    setState(() {
      _isRecovering = true;
      _error = null;
    });

    final provider = context.read<UserProvider>();
    final result = await provider.recoverE2eeKey(key);

    if (!mounted) return;

    if (result) {
      setState(() {
        _success = true;
        _isRecovering = false;
      });
      await Future.delayed(const Duration(seconds: 1));
      if (mounted) Navigator.of(context).pop();
    } else {
      setState(() {
        _isRecovering = false;
        _error = "Wrong key — doesn't match the one used to encrypt your data";
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: Dialog(
        backgroundColor: const Color(0xFF1A1A1A),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: _showLostKeyInfo ? _buildLostKeyView() : _buildRecoveryView(),
        ),
      ),
    );
  }

  Widget _buildRecoveryView() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(
            color: Colors.deepPurple.withValues(alpha: 0.2),
            shape: BoxShape.circle,
          ),
          child: const Icon(Icons.lock_outline, color: Colors.deepPurple, size: 28),
        ),
        const SizedBox(height: 16),
        const Text(
          'Recovery Key Required',
          style: TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.bold,
            fontSize: 18,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          'Your E2EE encryption key is missing. Paste your recovery key to restore access to your encrypted data.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
        ),
        const SizedBox(height: 20),
        if (_success) ...[
          const Icon(Icons.check_circle, color: Colors.green, size: 48),
          const SizedBox(height: 8),
          const Text(
            'Key recovered successfully',
            style: TextStyle(color: Colors.green, fontSize: 14),
          ),
        ] else ...[
          TextField(
            controller: _controller,
            maxLines: 3,
            style: const TextStyle(color: Colors.white, fontSize: 13, fontFamily: 'monospace'),
            decoration: InputDecoration(
              hintText: 'Paste recovery key',
              hintStyle: TextStyle(color: Colors.grey.shade600),
              filled: true,
              fillColor: const Color(0xFF2A2A2A),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
              contentPadding: const EdgeInsets.all(14),
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(
              _error!,
              style: TextStyle(color: Colors.red.shade300, fontSize: 13),
              textAlign: TextAlign.center,
            ),
          ],
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton(
              onPressed: _isRecovering ? null : _recover,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.deepPurple,
                disabledBackgroundColor: Colors.deepPurple.withValues(alpha: 0.5),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              child: _isRecovering
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Text(
                      'Recover',
                      style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                    ),
            ),
          ),
          const SizedBox(height: 12),
          GestureDetector(
            onTap: () => setState(() => _showLostKeyInfo = true),
            child: Text(
              'I lost my recovery key',
              style: TextStyle(
                color: Colors.grey.shade500,
                fontSize: 13,
                decoration: TextDecoration.underline,
                decorationColor: Colors.grey.shade500,
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildLostKeyView() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.warning_amber_rounded, color: Colors.orangeAccent, size: 48),
        const SizedBox(height: 16),
        const Text(
          'Recovery Key Lost',
          style: TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.bold,
            fontSize: 18,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          'Without the recovery key, you\'ll need to disable E2EE from another device where you\'re logged in, or contact support to reset your encryption.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
        ),
        const SizedBox(height: 20),
        SizedBox(
          width: double.infinity,
          height: 48,
          child: OutlinedButton(
            onPressed: () => setState(() => _showLostKeyInfo = false),
            style: OutlinedButton.styleFrom(
              side: const BorderSide(color: Colors.grey),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            child: const Text(
              'Go back',
              style: TextStyle(color: Colors.white, fontSize: 16),
            ),
          ),
        ),
      ],
    );
  }
}

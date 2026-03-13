import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'dart:convert';
import 'dart:async';

class E2eeQrDialog extends StatefulWidget {
  final String base64Key;
  const E2eeQrDialog({super.key, required this.base64Key});

  @override
  State<E2eeQrDialog> createState() => _E2eeQrDialogState();
}

class _E2eeQrDialogState extends State<E2eeQrDialog> {
  Timer? _timer;
  int _secondsLeft = 60;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      setState(() {
        _secondsLeft--;
        if (_secondsLeft <= 0) {
          Navigator.of(context).pop();
        }
      });
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final qrData = jsonEncode({
      'type': 'omi_e2ee_key',
      'key': widget.base64Key,
      'v': 1,
    });

    return Dialog(
      backgroundColor: const Color(0xFF1A1A1A),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.qr_code_2, color: Colors.white, size: 28),
                SizedBox(width: 10),
                Text('Pair with Web',
                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 18)),
              ],
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
              ),
              child: QrImageView(
                data: qrData,
                version: QrVersions.auto,
                size: 220,
                backgroundColor: Colors.white,
                errorCorrectionLevel: QrErrorCorrectLevel.M,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              'Scan this QR code on omi.me to unlock your encrypted data',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.timer_outlined, color: Colors.orangeAccent, size: 16),
                const SizedBox(width: 4),
                Text(
                  'Expires in ${_secondsLeft}s',
                  style: const TextStyle(color: Colors.orangeAccent, fontSize: 13),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '⚠️ Only scan on a trusted device',
              style: TextStyle(color: Colors.red.shade300, fontSize: 12),
            ),
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Close', style: TextStyle(color: Colors.grey)),
            ),
          ],
        ),
      ),
    );
  }
}

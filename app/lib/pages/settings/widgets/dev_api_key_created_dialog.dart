import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/backend/schema/dev_api_key.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';

class DevApiKeyCreatedSheet extends StatefulWidget {
  final DevApiKeyCreated apiKey;

  const DevApiKeyCreatedSheet({super.key, required this.apiKey});

  @override
  State<DevApiKeyCreatedSheet> createState() => _DevApiKeyCreatedSheetState();
}

class _DevApiKeyCreatedSheetState extends State<DevApiKeyCreatedSheet> {
  bool _copied = false;

  void _copyKey() {
    Clipboard.setData(ClipboardData(text: widget.apiKey.key));
    setState(() => _copied = true);
    AppSnackbar.showSnackbar('API key copied to clipboard');
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF0F0F0F),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Handle bar
          Center(
            child: Container(
              margin: const EdgeInsets.only(top: 12, bottom: 8),
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: const Color(0xFF3C3C43),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          // Success header
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
            child: Column(
              children: [
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        const Color(0xFF10B981).withValues(alpha: 0.2),
                        const Color(0xFF10B981).withValues(alpha: 0.05),
                      ],
                    ),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.check_circle, color: Color(0xFF10B981), size: 40),
                ),
                const SizedBox(height: 16),
                const Text(
                  'API Key Created!',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 22,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  widget.apiKey.name,
                  style: const TextStyle(
                    color: Color(0xFF8E8E93),
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          // Warning banner
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFFF59E0B).withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFF59E0B).withValues(alpha: 0.2)),
              ),
              child: Row(
                children: [
                  Icon(Icons.warning_amber_rounded, color: Colors.amber.shade600, size: 20),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      'Save this key now! You won\'t be able to see it again.',
                      style: TextStyle(
                        color: Color(0xFFF59E0B),
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),
          // Key display
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: GestureDetector(
              onTap: _copyKey,
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A1A),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(
                    color: _copied ? const Color(0xFF10B981) : const Color(0xFF2C2C2E),
                    width: _copied ? 1.5 : 1,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Text(
                          'YOUR API KEY',
                          style: TextStyle(
                            color: Color(0xFF8E8E93),
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.5,
                          ),
                        ),
                        const Spacer(),
                        AnimatedContainer(
                          duration: const Duration(milliseconds: 200),
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: _copied ? const Color(0xFF10B981).withValues(alpha: 0.15) : const Color(0xFF252525),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                _copied ? Icons.check : Icons.copy,
                                size: 14,
                                color: _copied ? const Color(0xFF10B981) : const Color(0xFF8E8E93),
                              ),
                              const SizedBox(width: 4),
                              Text(
                                _copied ? 'Copied!' : 'Tap to copy',
                                style: TextStyle(
                                  color: _copied ? const Color(0xFF10B981) : const Color(0xFF8E8E93),
                                  fontSize: 11,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    SelectableText(
                      widget.apiKey.key,
                      style: TextStyle(
                        fontFamily: 'monospace',
                        color: _copied ? const Color(0xFF10B981) : const Color(0xFF8B5CF6),
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        height: 1.4,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 28),
          // Buttons
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _copyKey,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: _copied ? const Color(0xFF10B981) : const Color(0xFF8B5CF6),
                      side: BorderSide(
                        color: _copied ? const Color(0xFF10B981) : const Color(0xFF8B5CF6),
                        width: 1.5,
                      ),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(_copied ? Icons.check : Icons.copy, size: 18),
                        const SizedBox(width: 8),
                        Text(
                          _copied ? 'Copied!' : 'Copy Key',
                          style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF252525),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      elevation: 0,
                    ),
                    child: const Text(
                      'Done',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          SizedBox(height: MediaQuery.of(context).padding.bottom),
        ],
      ),
    );
  }
}

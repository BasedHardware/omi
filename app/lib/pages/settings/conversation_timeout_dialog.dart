import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';

class ConversationTimeoutDialog {
  /// Opens the conversation timeout settings as a full page.
  static Future<void> show(BuildContext context) async {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (context) => const _ConversationTimeoutPage()),
    );
  }
}

class _ConversationTimeoutPage extends StatefulWidget {
  const _ConversationTimeoutPage();

  @override
  State<_ConversationTimeoutPage> createState() => _ConversationTimeoutPageState();
}

class _ConversationTimeoutPageState extends State<_ConversationTimeoutPage> {
  late int _selectedDuration;

  @override
  void initState() {
    super.initState();
    _selectedDuration = SharedPreferencesUtil().conversationSilenceDuration;
  }

  void _save() {
    SharedPreferencesUtil().conversationSilenceDuration = _selectedDuration;
    Navigator.of(context).pop();

    String message;
    if (_selectedDuration == -1) {
      message = context.l10n.conversationEndAfterHours;
    } else {
      final minutes = _selectedDuration ~/ 60;
      message = context.l10n.conversationEndAfterMinutes(minutes);
    }
    AppSnackbar.showSnackbar(message);
  }

  @override
  Widget build(BuildContext context) {
    final timeoutOptions = [
      _TimeoutOption(label: context.l10n.timeout2Minutes, value: 120, description: context.l10n.timeout2MinutesDesc),
      _TimeoutOption(label: context.l10n.timeout5Minutes, value: 300, description: context.l10n.timeout5MinutesDesc),
      _TimeoutOption(label: context.l10n.timeout10Minutes, value: 600, description: context.l10n.timeout10MinutesDesc),
      _TimeoutOption(label: context.l10n.timeout30Minutes, value: 1800, description: context.l10n.timeout30MinutesDesc),
      _TimeoutOption(label: context.l10n.timeout4Hours, value: -1, description: context.l10n.timeout4HoursDesc),
    ];

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        elevation: 0,
        leading: IconButton(
          icon: const Padding(
            padding: EdgeInsets.only(left: 2, top: 1),
            child: FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(
          context.l10n.conversationTimeout,
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
        centerTitle: true,
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
              children: [
                Text(
                  context.l10n.conversationTimeoutDesc,
                  style: const TextStyle(
                    color: Color(0xFF8E8E93),
                    fontSize: 14,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 24),
                ...timeoutOptions.map((option) {
                  final isSelected = _selectedDuration == option.value;
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: GestureDetector(
                      onTap: () {
                        HapticFeedback.lightImpact();
                        setState(() {
                          _selectedDuration = option.value;
                        });
                      },
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                            color: isSelected ? Colors.white : const Color(0xFF2C2C2E),
                            width: isSelected ? 1.5 : 1,
                          ),
                          color: isSelected ? Colors.white.withValues(alpha: 0.05) : Colors.transparent,
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    option.label,
                                    style: TextStyle(
                                      color: isSelected ? Colors.white : const Color(0xFFE5E5E7),
                                      fontSize: 16,
                                      fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    option.description,
                                    style: TextStyle(
                                      color: isSelected ? const Color(0xFFAEAEB2) : const Color(0xFF8E8E93),
                                      fontSize: 13,
                                      height: 1.4,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 12),
                            AnimatedOpacity(
                              duration: const Duration(milliseconds: 200),
                              opacity: isSelected ? 1.0 : 0.0,
                              child: Container(
                                width: 24,
                                height: 24,
                                decoration: const BoxDecoration(
                                  color: Colors.white,
                                  shape: BoxShape.circle,
                                ),
                                child: const Icon(Icons.check, color: Colors.black, size: 16),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                }),
              ],
            ),
          ),
          // Save button
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
              child: SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  onPressed: _save,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: Colors.black,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    elevation: 0,
                  ),
                  child: Text(
                    context.l10n.save,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TimeoutOption {
  final String label;
  final int value;
  final String description;

  const _TimeoutOption({
    required this.label,
    required this.value,
    required this.description,
  });
}

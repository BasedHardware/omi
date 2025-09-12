import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';

class ConversationTimeoutDialog {
  static Future<void> show(BuildContext context) async {
    final currentDuration = SharedPreferencesUtil().conversationSilenceDuration;
    int selectedDuration = currentDuration;

    // Timeout options: 2 mins, 5 mins, 10 mins, 30 mins, never
    final timeoutOptions = [
      {'label': '2 minutes', 'value': 120, 'description': 'End conversation after 2 minutes of silence'},
      {'label': '5 minutes', 'value': 300, 'description': 'End conversation after 5 minutes of silence'},
      {'label': '10 minutes', 'value': 600, 'description': 'End conversation after 10 minutes of silence'},
      {'label': '30 minutes', 'value': 1800, 'description': 'End conversation after 30 minutes of silence'},
      {'label': 'Never', 'value': -1, 'description': 'Conversations will only end manually'},
    ];

    await showDialog(
      context: context,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setState) {
            return AlertDialog(
              backgroundColor: const Color(0xFF1A1A1A),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              title: const Text(
                'Conversation Timeout',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                ),
              ),
              content: SizedBox(
                width: double.maxFinite,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Choose how long to wait in silence before automatically ending a conversation:',
                      style: TextStyle(
                        color: Color(0xFF8E8E93),
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 16),
                    ...timeoutOptions.map((option) {
                      final isSelected = selectedDuration == option['value'];
                      return Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: Material(
                          color: Colors.transparent,
                          child: InkWell(
                            borderRadius: BorderRadius.circular(12),
                            onTap: () {
                              setState(() {
                                selectedDuration = option['value'] as int;
                              });
                            },
                            child: Container(
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: isSelected ? Colors.white : const Color(0xFF3C3C43),
                                  width: isSelected ? 2 : 1,
                                ),
                                color: isSelected ? const Color(0xFF2C2C2E) : Colors.transparent,
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          option['label'] as String,
                                          style: TextStyle(
                                            color: isSelected ? Colors.white : const Color(0xFFE5E5E7),
                                            fontSize: 16,
                                            fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          option['description'] as String,
                                          style: TextStyle(
                                            color: isSelected ? const Color(0xFFAEAEB2) : const Color(0xFF8E8E93),
                                            fontSize: 12,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  if (isSelected)
                                    const Icon(
                                      Icons.check_circle,
                                      color: Colors.white,
                                      size: 20,
                                    ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () {
                    Navigator.of(context).pop();
                  },
                  child: const Text(
                    'Cancel',
                    style: TextStyle(color: Color(0xFF8E8E93)),
                  ),
                ),
                TextButton(
                  onPressed: () {
                    SharedPreferencesUtil().conversationSilenceDuration = selectedDuration;
                    Navigator.of(context).pop();

                    // Show confirmation
                    String message;
                    if (selectedDuration == -1) {
                      message = 'Conversations will now only end manually';
                    } else {
                      final minutes = selectedDuration ~/ 60;
                      message = 'Conversations will now end after $minutes minute${minutes == 1 ? '' : 's'} of silence';
                    }
                    AppSnackbar.showSnackbar(message);
                  },
                  child: const Text(
                    'Save',
                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            );
          },
        );
      },
    );
  }
}

import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

class ConfirmationDialog extends StatelessWidget {
  final String title;
  final String description;
  final String checkboxText;
  final bool checkboxValue;
  final void Function(bool? value) updateCheckboxValue;
  final String? cancelText;
  final String? confirmText;
  final void Function() onConfirm;
  final void Function() onCancel;

  const ConfirmationDialog({
    super.key,
    required this.title,
    required this.description,
    required this.checkboxText,
    required this.checkboxValue,
    required this.updateCheckboxValue,
    this.cancelText,
    this.confirmText,
    required this.onConfirm,
    required this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    if (Platform.isAndroid) {
      return AlertDialog(
        contentPadding: const EdgeInsets.only(top: 10, left: 24, right: 24, bottom: 10),
        title: Text(title),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 16),
            Text(
              description,
              textAlign: TextAlign.start,
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                SizedBox(
                  width: 20,
                  height: 20,
                  child: Checkbox(
                    value: checkboxValue,
                    onChanged: updateCheckboxValue,
                  ),
                ),
                const SizedBox(width: 8),
                Text(checkboxText),
              ],
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: onCancel,
            child: Text(cancelText ?? "Cancel", style: const TextStyle(color: Colors.white)),
          ),
          TextButton(
            onPressed: onConfirm,
            child: Text(confirmText ?? "Confirm", style: const TextStyle(color: Colors.white)),
          ),
        ],
      );
    } else {
      return CupertinoAlertDialog(
        title: Text(title),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 16),
            Text(
              description,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                SizedBox(
                  width: 20,
                  height: 20,
                  child: CupertinoCheckbox(
                    value: checkboxValue,
                    onChanged: updateCheckboxValue,
                  ),
                ),
                const SizedBox(width: 8),
                Text(checkboxText),
              ],
            ),
          ],
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: onCancel,
            child: Text(cancelText ?? "Cancel", style: const TextStyle(color: Colors.white)),
          ),
          CupertinoDialogAction(
            onPressed: onConfirm,
            child: Text(confirmText ?? "Confirm", style: const TextStyle(color: Colors.white)),
          ),
        ],
      );
    }
  }
}

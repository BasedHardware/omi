import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

class ConfirmationDialog extends StatefulWidget {
  final String title;
  final String description;
  final String checkboxText;
  final bool checkboxValue;
  final void Function(bool value) onCheckboxChanged;
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
    required this.onCheckboxChanged,
    this.cancelText,
    this.confirmText,
    required this.onConfirm,
    required this.onCancel,
  });

  @override
  State<ConfirmationDialog> createState() => _ConfirmationDialogState();
}

class _ConfirmationDialogState extends State<ConfirmationDialog> {
  late bool _checkboxValue;

  @override
  void initState() {
    super.initState();
    _checkboxValue = widget.checkboxValue;
  }

  void _updateCheckboxValue(bool? value) {
    debugPrint("checked option ${value ?? false}");
    debugPrint("checked ${_checkboxValue}");
    if (value != null) {
      setState(() {
        _checkboxValue = value;
      });
      widget.onCheckboxChanged(value);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (Platform.isAndroid) {
      return AlertDialog(
        contentPadding: const EdgeInsets.only(top: 10, left: 24, right: 24, bottom: 10),
        title: Text(widget.title),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 16),
            Text(
              widget.description,
              textAlign: TextAlign.start,
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.start,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Checkbox(
                  value: _checkboxValue,
                  onChanged: _updateCheckboxValue,
                ),
                Text(widget.checkboxText),
              ],
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: widget.onCancel,
            child: Text(widget.cancelText ?? "Cancel", style: const TextStyle(color: Colors.white)),
          ),
          TextButton(
            onPressed: widget.onConfirm,
            child: Text(widget.confirmText ?? "Confirm", style: const TextStyle(color: Colors.white)),
          ),
        ],
      );
    } else {
      return CupertinoAlertDialog(
        title: Text(widget.title),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 16),
            Text(
              widget.description,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 14),
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.start,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                CupertinoCheckbox(
                  value: _checkboxValue,
                  onChanged: _updateCheckboxValue,
                ),
                Text(widget.checkboxText),
              ],
            ),
          ],
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: widget.onCancel,
            child: Text(widget.cancelText ?? "Cancel", style: const TextStyle(color: Colors.white, fontSize: 14)),
          ),
          CupertinoDialogAction(
            onPressed: widget.onConfirm,
            child: Text(widget.confirmText ?? "Confirm", style: const TextStyle(color: Colors.white, fontSize: 14)),
          ),
        ],
      );
    }
  }
}

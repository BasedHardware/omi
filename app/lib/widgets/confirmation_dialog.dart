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
        backgroundColor: Colors.grey.shade900,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        contentPadding: const EdgeInsets.only(top: 20, left: 24, right: 24, bottom: 10),
        title: Text(
          widget.title,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 16),
            Text(
              widget.description,
              textAlign: TextAlign.start,
              style: TextStyle(
                color: Colors.grey.shade200,
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 20),
            Row(
              mainAxisAlignment: MainAxisAlignment.start,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Theme(
                  data: Theme.of(context).copyWith(
                    checkboxTheme: CheckboxThemeData(
                      fillColor: MaterialStateProperty.resolveWith<Color>(
                        (Set<MaterialState> states) {
                          if (states.contains(MaterialState.selected)) {
                            return Colors.deepPurple;
                          }
                          return Colors.grey.shade700;
                        },
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                  ),
                  child: Checkbox(
                    value: _checkboxValue,
                    onChanged: _updateCheckboxValue,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  widget.checkboxText,
                  style: TextStyle(
                    color: Colors.grey.shade300,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: widget.onCancel,
            style: TextButton.styleFrom(
              foregroundColor: Colors.grey.shade300,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            ),
            child: Text(widget.cancelText ?? "Cancel"),
          ),
          TextButton(
            onPressed: widget.onConfirm,
            style: TextButton.styleFrom(
              foregroundColor: Colors.white,
              backgroundColor: Colors.deepPurple,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            child: Text(widget.confirmText ?? "Confirm"),
          ),
        ],
      );
    } else {
      return CupertinoAlertDialog(
        title: Text(
          widget.title,
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: Colors.white,
          ),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 16),
            Text(
              widget.description,
              textAlign: TextAlign.start,
              style: TextStyle(
                fontSize: 14,
                color: Colors.grey.shade200,
              ),
            ),
            const SizedBox(height: 20),
            Row(
              mainAxisAlignment: MainAxisAlignment.start,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                CupertinoCheckbox(
                  value: _checkboxValue,
                  onChanged: _updateCheckboxValue,
                  activeColor: Colors.deepPurple,
                ),
                const SizedBox(width: 8),
                Text(
                  widget.checkboxText,
                  style: TextStyle(
                    fontSize: 14,
                    color: Colors.grey.shade300,
                  ),
                ),
              ],
            ),
          ],
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: widget.onCancel,
            isDestructiveAction: false,
            child: Text(
              widget.cancelText ?? "Cancel", 
              style: TextStyle(
                fontSize: 16,
                color: Colors.grey.shade300,
              ),
            ),
          ),
          CupertinoDialogAction(
            onPressed: widget.onConfirm,
            isDefaultAction: true,
            child: Text(
              widget.confirmText ?? "Confirm", 
              style: const TextStyle(
                fontSize: 16,
                color: Colors.deepPurple,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      );
    }
  }
}

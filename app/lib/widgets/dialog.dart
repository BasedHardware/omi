import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:omi/utils/platform/platform_service.dart';

//TODO: switch to required named parameters
getDialog(
  BuildContext context,
  Function onCancel,
  Function onConfirm,
  String title,
  String content, {
  bool singleButton = false,
  String okButtonText = 'Ok',
  String cancelButtonText = 'Cancel',
}) {
  var actions = singleButton
      ? [
          TextButton(
            onPressed: () => onCancel(),
            child: Text(okButtonText, style: const TextStyle(color: Colors.white)),
          )
        ]
      : [
          TextButton(
            onPressed: () => onCancel(),
            child: Text(cancelButtonText, style: const TextStyle(color: Colors.grey)),
          ),
          TextButton(
            onPressed: () => onConfirm(),
            child: Text(
              okButtonText,
              style: TextStyle(
                color: okButtonText == 'Delete'
                    ? Colors.red
                    : okButtonText == 'Reprocess'
                        ? Colors.orange
                        : Colors.deepPurple,
              ),
            ),
          ),
        ];

  if (PlatformService.isApple) {
    return CupertinoAlertDialog(
      title: Text(title, style: const TextStyle(color: Colors.white)),
      content: Text(content, style: const TextStyle(color: Colors.white70)),
      actions: actions,
    );
  }

  return AlertDialog(
    backgroundColor: const Color(0xFF1F1F25),
    title: Text(title, style: const TextStyle(color: Colors.white)),
    content: Text(content, style: const TextStyle(color: Colors.white70)),
    actions: actions,
  );
}

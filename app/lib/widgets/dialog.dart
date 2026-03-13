import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_service.dart';

Future<bool> showDeleteConversationDialog(BuildContext context) async {
  return await showDialog<bool>(
        context: context,
        builder: (ctx) {
          final actions = [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: Text(context.l10n.cancel, style: const TextStyle(color: Colors.white)),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: Text(context.l10n.confirm, style: const TextStyle(color: Colors.red)),
            ),
          ];

          if (PlatformService.isApple) {
            return CupertinoAlertDialog(
              title: Text(context.l10n.deleteConversationTitle),
              content: Text(context.l10n.deleteConversationMessage),
              actions: actions,
            );
          }
          return AlertDialog(
            title: Text(context.l10n.deleteConversationTitle),
            content: Text(context.l10n.deleteConversationMessage),
            actions: actions,
          );
        },
      ) ??
      false;
}

getDialog(
  BuildContext context,
  Function onCancel,
  Function onConfirm,
  String title,
  String content, {
  bool singleButton = false,
  String? okButtonText,
  String? cancelButtonText,
}) {
  final okText = okButtonText ?? context.l10n.ok;
  final cancelText = cancelButtonText ?? context.l10n.cancel;

  var actions = singleButton
      ? [
          TextButton(
            onPressed: () => onCancel(),
            child: Text(okText, style: const TextStyle(color: Colors.white)),
          )
        ]
      : [
          TextButton(
            onPressed: () => onCancel(),
            child: Text(cancelText, style: const TextStyle(color: Colors.white)),
          ),
          TextButton(onPressed: () => onConfirm(), child: Text(okText, style: const TextStyle(color: Colors.white))),
        ];
  if (PlatformService.isApple) {
    return CupertinoAlertDialog(title: Text(title), content: Text(content), actions: actions);
  }
  return AlertDialog(title: Text(title), content: Text(content), actions: actions);
}

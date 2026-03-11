import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_service.dart';

class DeleteConversationOptions {
  final bool deleteAssociatedData;

  DeleteConversationOptions({required this.deleteAssociatedData});
}

Future<DeleteConversationOptions?> showDeleteConversationDialog(BuildContext context) async {
  bool deleteAssociatedData = false;

  return showDialog<DeleteConversationOptions>(
    context: context,
    builder: (ctx) {
      return StatefulBuilder(
        builder: (context, setState) {
          final checkbox = GestureDetector(
            onTap: () => setState(() => deleteAssociatedData = !deleteAssociatedData),
            child: Row(
              children: [
                SizedBox(
                  width: 24,
                  height: 24,
                  child: Checkbox(
                    value: deleteAssociatedData,
                    onChanged: (v) => setState(() => deleteAssociatedData = v ?? false),
                    activeColor: Colors.deepPurple,
                    checkColor: Colors.white,
                    side: const BorderSide(color: Colors.white54),
                    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                ),
                const SizedBox(width: 8),
                Flexible(
                  child: Text(
                    context.l10n.deleteAssociatedData,
                    style: const TextStyle(fontSize: 14),
                  ),
                ),
              ],
            ),
          );

          final wrappedCheckbox = Padding(
            padding: const EdgeInsets.only(top: 16),
            child: checkbox,
          );
          final content =
              PlatformService.isApple ? Material(color: Colors.transparent, child: wrappedCheckbox) : wrappedCheckbox;

          final actions = [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(null),
              child: Text(context.l10n.cancel, style: const TextStyle(color: Colors.white)),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(
                DeleteConversationOptions(deleteAssociatedData: deleteAssociatedData),
              ),
              child: Text(context.l10n.confirm, style: const TextStyle(color: Colors.red)),
            ),
          ];

          if (PlatformService.isApple) {
            return CupertinoAlertDialog(
              title: Text(context.l10n.deleteConversationTitle),
              content: content,
              actions: actions,
            );
          }
          return AlertDialog(
            title: Text(context.l10n.deleteConversationTitle),
            content: content,
            actions: actions,
          );
        },
      );
    },
  );
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

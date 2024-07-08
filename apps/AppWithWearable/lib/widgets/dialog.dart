import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

getDialog(BuildContext context, Function onCancel, Function onConfirm, String title, String content,
    {bool singleButton = false}) {
  var actions = singleButton
      ? [
          TextButton(
            onPressed: () => onCancel(),
            child: const Text('Ok', style: TextStyle(color: Colors.white)),
          )
        ]
      : [
          TextButton(
            onPressed: () => onCancel(),
            child: const Text('Cancel', style: TextStyle(color: Colors.white)),
          ),
          TextButton(onPressed: () => onConfirm(), child: const Text('Confirm', style: TextStyle(color: Colors.white))),
        ];
  if (Platform.isIOS) {
    return CupertinoAlertDialog(title: Text(title), content: Text(content), actions: actions);
  }
  return AlertDialog(title: Text(title), content: Text(content), actions: actions);
}

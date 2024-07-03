import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

getDialog(BuildContext context, Function onCancel, Function onConfirm, String title, String content) {
  if (Platform.isIOS) {
    return CupertinoAlertDialog(
      title: Text(title),
      content: Text(content),
      actions: [
        TextButton(
          onPressed: () => onCancel(),
          child: const Text('Cancel', style: TextStyle(color: Colors.white)),
        ),
        TextButton(onPressed: () => onConfirm(), child: const Text('Confirm', style: TextStyle(color: Colors.white))),
      ],
    );
  }
  return AlertDialog(
    title: Text(title),
    content: Text(content),
    actions: [
      TextButton(
        onPressed: () => onCancel(),
        child: const Text('Cancel', style: TextStyle(color: Colors.white)),
      ),
      TextButton(onPressed: () => onConfirm(), child: const Text('Confirm', style: TextStyle(color: Colors.white))),
    ],
  );
}

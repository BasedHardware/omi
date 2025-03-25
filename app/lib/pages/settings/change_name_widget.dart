import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';

class ChangeNameWidget extends StatefulWidget {
  const ChangeNameWidget({super.key});

  @override
  State<ChangeNameWidget> createState() => _ChangeNameWidgetState();
}

class _ChangeNameWidgetState extends State<ChangeNameWidget> {
  late TextEditingController nameController;
  User? user;
  bool isSaving = false;

  @override
  void initState() {
    user = getFirebaseUser();
    nameController = TextEditingController(text: user?.displayName ?? '');
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    if (Platform.isIOS) {
      return CupertinoAlertDialog(
        content: Padding(
          padding: const EdgeInsets.all(8.0),
          child: Column(
            children: <Widget>[
              const Text('How Omi should call you?'),
              const SizedBox(height: 8),
              CupertinoTextField(
                controller: nameController,
                placeholderStyle: const TextStyle(color: Colors.white54),
                style: const TextStyle(color: Colors.white),
              ),
            ],
          ),
        ),
        actions: <Widget>[
          CupertinoDialogAction(
            textStyle: const TextStyle(color: Colors.white),
            onPressed: () {
              Navigator.of(context).pop();
            },
            child: const Text('Cancel'),
          ),
          CupertinoDialogAction(
            textStyle: const TextStyle(color: Colors.white),
            onPressed: () {
              if (nameController.text.isEmpty || nameController.text.trim().isEmpty) {
                AppSnackbar.showSnackbarError('Name cannot be empty');
                return;
              }
              SharedPreferencesUtil().givenName = nameController.text;
              updateGivenName(nameController.text);
              AppSnackbar.showSnackbar('Name updated successfully!');
              Navigator.of(context).pop();
            },
            child: const Text('Save'),
          ),
        ],
      );
    } else {
      return AlertDialog(
        content: Padding(
          padding: const EdgeInsets.all(8.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Text('How Omi should call you?'),
              const SizedBox(height: 8),
              TextField(
                controller: nameController,
                style: const TextStyle(color: Colors.white),
              ),
            ],
          ),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
            },
            child: const Text(
              'Cancel',
              style: TextStyle(color: Colors.white),
            ),
          ),
          TextButton(
            onPressed: () {
              if (nameController.text.isEmpty || nameController.text.trim().isEmpty) {
                AppSnackbar.showSnackbarError('Name cannot be empty');
                return;
              }
              SharedPreferencesUtil().givenName = nameController.text;
              updateGivenName(nameController.text);
              AppSnackbar.showSnackbar('Name updated successfully!');
              Navigator.of(context).pop();
            },
            child: const Text(
              'Save',
              style: TextStyle(color: Colors.white),
            ),
          ),
        ],
      );
    }
  }
}

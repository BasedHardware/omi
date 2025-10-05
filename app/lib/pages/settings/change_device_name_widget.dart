import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';

class ChangeDeviceNameWidget extends StatefulWidget {
  final BtDevice? device;
  final VoidCallback? onNameChanged;

  const ChangeDeviceNameWidget({
    super.key,
    this.device,
    this.onNameChanged,
  });

  @override
  State<ChangeDeviceNameWidget> createState() => _ChangeDeviceNameWidgetState();
}

class _ChangeDeviceNameWidgetState extends State<ChangeDeviceNameWidget> {
  late TextEditingController nameController;

  @override
  void initState() {
    super.initState();
    // Initialize with custom name if set, otherwise use device name
    final customName = widget.device != null ? SharedPreferencesUtil().getCustomDeviceName(widget.device!.id) : '';
    nameController = TextEditingController(
      text: customName.isNotEmpty ? customName : (widget.device?.name ?? ''),
    );
  }

  @override
  void dispose() {
    nameController.dispose();
    super.dispose();
  }

  void _saveName() {
    if (nameController.text.isEmpty || nameController.text.trim().isEmpty) {
      AppSnackbar.showSnackbarError('Device name cannot be empty');
      return;
    }
    if (widget.device != null) {
      SharedPreferencesUtil().setCustomDeviceName(
        widget.device!.id,
        nameController.text.trim(),
      );
    }
    AppSnackbar.showSnackbar('Device name updated successfully!');
    widget.onNameChanged?.call();
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    if (Platform.isIOS) {
      return CupertinoAlertDialog(
        content: Padding(
          padding: const EdgeInsets.all(8.0),
          child: Column(
            children: <Widget>[
              const Text('Rename your device'),
              const SizedBox(height: 8),
              CupertinoTextField(
                controller: nameController,
                placeholder: 'Enter device name',
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
            onPressed: _saveName,
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
              const Text('Rename your device'),
              const SizedBox(height: 8),
              TextField(
                controller: nameController,
                decoration: const InputDecoration(
                  hintText: 'Enter device name',
                ),
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
            onPressed: _saveName,
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

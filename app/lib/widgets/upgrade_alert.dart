// Copyright (c) 2023 Larry Aasen. All rights reserved.

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:upgrader/upgrader.dart';

class MyUpgrader extends Upgrader {
  MyUpgrader({super.debugLogging, super.debugDisplayOnce});

  @override
  bool isUpdateAvailable() {
    final storeVersion = currentAppStoreVersion;
    final installedVersion = currentInstalledVersion;
    // print('storeVersion=$storeVersion');
    // print('installedVersion=$installedVersion');
    return super.isUpdateAvailable();
  }
}

class MyUpgradeAlert extends UpgradeAlert {
  MyUpgradeAlert({
    super.key,
    super.upgrader,
    super.child,
    super.dialogStyle,
  });

  /// Override the [createState] method to provide a custom class
  /// with overridden methods.
  @override
  UpgradeAlertState createState() => MyUpgradeAlertState();
}

class MyUpgradeAlertState extends UpgradeAlertState {
  @override
  void showTheDialog({
    Key? key,
    required BuildContext context,
    required String? title,
    required String message,
    required String? releaseNotes,
    required bool barrierDismissible,
    required UpgraderMessages messages,
  }) {
    showDialog(
        context: context,
        builder: (BuildContext context) {
          if (widget.dialogStyle == UpgradeDialogStyle.cupertino) {
            return CupertinoAlertDialog(
              key: key,
              title: const Text(
                'New Version Available  🎉',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
              ),
              content: SingleChildScrollView(child: ListBody(children: <Widget>[Text(message)])),
              actions: <Widget>[
                TextButton(
                  child: Text('No', style: TextStyle(color: Colors.grey.shade200, fontSize: 16)),
                  onPressed: () {
                    onUserIgnored(context, true);
                    MixpanelManager().upgradeModalDismissed();
                  },
                ),
                TextButton(
                  child: const Text('Upgrade', style: TextStyle(color: Colors.white, fontSize: 16)),
                  onPressed: () {
                    onUserUpdated(context, !widget.upgrader.blocked());
                    MixpanelManager().upgradeModalClicked();
                  },
                ),
              ],
            );
          }
          return AlertDialog(
            key: key,
            title: const Text(
              'New Version Available  🎉',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
            ),
            content: SingleChildScrollView(child: ListBody(children: <Widget>[Text(message)])),
            actions: <Widget>[
              TextButton(
                child: Text('No', style: TextStyle(color: Colors.grey.shade200, fontSize: 16)),
                onPressed: () {
                  onUserIgnored(context, true);
                },
              ),
              TextButton(
                child: const Text('Upgrade', style: TextStyle(color: Colors.white, fontSize: 16)),
                onPressed: () {
                  onUserUpdated(context, !widget.upgrader.blocked());
                },
              ),
            ],
          );
        });
  }
}

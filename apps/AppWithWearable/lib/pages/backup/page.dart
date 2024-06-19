import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/backup/password.dart';
import 'package:friend_private/utils/backups.dart';

class BackupsPage extends StatefulWidget {
  const BackupsPage({super.key});

  @override
  State<BackupsPage> createState() => _BackupsPageState();
}

class _BackupsPageState extends State<BackupsPage> {
  var backupsEnabled = false;
  bool hasPasswordSet = false;

  @override
  void initState() {
    backupsEnabled = SharedPreferencesUtil().backupsEnabled;
    hasPasswordSet = SharedPreferencesUtil().hasBackupPassword;
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    var backupHoursAgo = SharedPreferencesUtil().lastBackupDate.isEmpty
        ? null
        : DateTime.now().difference(DateTime.parse(SharedPreferencesUtil().lastBackupDate));
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: const Text('Backups configuration'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(8),
        child: ListView(
          children: [
            const SizedBox(height: 16),
            CheckboxListTile(
              title: const Text(
                'Enable',
                style: TextStyle(fontSize: 16),
              ),
              subtitle: const Text('Cloud stored encrypted backups'),
              value: backupsEnabled,
              checkboxShape: const CircleBorder(),
              onChanged: (v) {
                // TODO: delete backup when unselected, create when set true?
                SharedPreferencesUtil().backupsEnabled = v!;
                setState(() {
                  backupsEnabled = v;
                });
                if (v) {
                  executeBackup().then((_) => setState(() {}));
                } else if (SharedPreferencesUtil().lastBackupDate != '') {
                  SharedPreferencesUtil().lastBackupDate = '';
                  setState(() {});
                  deleteBackupApi();
                }
              },
            ),
            ListTile(
              title: const Text('User ID'),
              subtitle: Text(SharedPreferencesUtil().uid),
              trailing: IconButton(onPressed: () {}, icon: const Icon(Icons.copy)),
            ),
            backupHoursAgo != null ? const SizedBox(height: 32) : Container(),
            backupHoursAgo != null
                ? ListTile(
                    title: const Text('Last backup'),
                    subtitle: Text(
                      '${backupHoursAgo.inHours == 0 ? backupHoursAgo.inMinutes : backupHoursAgo.inHours} ${backupHoursAgo.inHours == 0 ? 'minutes ago' : 'hours ago'}',
                      // include just now
                    ),
                    trailing: IconButton(
                      onPressed: () async {
                        await executeBackup();
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Backup completed!')),
                          // TODO: better snackbars UI here
                        );
                      },
                      icon: const Icon(Icons.refresh),
                    ),
                  )
                : const SizedBox(),
            backupsEnabled
                ? ListTile(
                    title: Text(hasPasswordSet ? 'Change password' : 'Set up a password'),
                    subtitle: const Text('Create a new backup'),
                    onTap: () async {
                      await Navigator.of(context).push(MaterialPageRoute(builder: (c) => const BackupPasswordPage()));
                      await executeBackup();
                      setState(() {});
                    },
                  )
                : const SizedBox(),
          ],
        ),
      ),
    );
  }
}

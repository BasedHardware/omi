import 'package:flutter/material.dart';
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

  @override
  void initState() {
    backupsEnabled = SharedPreferencesUtil().backupsEnabled;
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    var backupHoursAgo = DateTime.now().difference(DateTime.parse(SharedPreferencesUtil().lastBackupDate));
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
                SharedPreferencesUtil().backupsEnabled = v!;
                setState(() {
                  backupsEnabled = v;
                });
              },
            ),
            SharedPreferencesUtil().lastBackupDate.length > 10 ? const SizedBox(height: 32) : Container(),
            SharedPreferencesUtil().lastBackupDate.length > 10
                ? ListTile(
                    title: const Text('Last backup made'),
                    subtitle: Text(
                      '${backupHoursAgo.inHours == 0 ? backupHoursAgo.inMinutes : backupHoursAgo.inHours} ${backupHoursAgo.inHours == 0 ? 'minutes ago' : 'hours ago'}',
                      // include just now
                    ),
                    trailing: IconButton(
                      onPressed: () async {
                        await executeBackup();
                      },
                      icon: const Icon(Icons.refresh),
                    ),
                  )
                : const SizedBox(),
            ListTile(
              title: const Text('User ID'),
              subtitle: Text(SharedPreferencesUtil().uid),
              trailing: IconButton(onPressed: () {}, icon: const Icon(Icons.copy)),
            ),
            backupsEnabled
                ? ListTile(
                    title: const Text('Set up password'),
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

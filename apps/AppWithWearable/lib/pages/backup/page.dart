import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/api/server.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/backup/password.dart';
import 'package:friend_private/utils/backups.dart';
import 'package:share_plus/share_plus.dart';

class BackupsPage extends StatefulWidget {
  const BackupsPage({super.key});

  @override
  State<BackupsPage> createState() => _BackupsPageState();
}

class _BackupsPageState extends State<BackupsPage> {
  bool backupsEnabled = false;
  bool hasPasswordSet = false;
  bool loadingExportMemories = false;
  bool loadingImportMemories = false;

  bool backupInProgress = false;

  @override
  void initState() {
    backupsEnabled = SharedPreferencesUtil().backupsEnabled;
    hasPasswordSet = SharedPreferencesUtil().hasBackupPassword;
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    var now = DateTime.now();
    var lastBackupDate = SharedPreferencesUtil().lastBackupDate;
    var timeDiff = lastBackupDate.isEmpty ? null : now.difference(DateTime.parse(lastBackupDate));
    String timeAgo = '';
    if ((timeDiff?.inHours ?? 0) > 0) {
      timeAgo = '${timeDiff!.inHours} hour${timeDiff.inHours == 1 ? '' : 's'} ago';
    } else if ((timeDiff?.inMinutes ?? 0) > 0) {
      timeAgo = '${timeDiff!.inMinutes} minute${timeDiff.inMinutes == 1 ? '' : 's'} ago';
    } else if (timeDiff != null) {
      timeAgo = 'Just now';
    }

    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: const Text('Backups configuration'),
        actions: [
          IconButton(
              onPressed: () {
                showDialog(
                    context: context,
                    builder: (c) => AlertDialog(
                          title: const Text('How it works?'),
                          content: const Text(
                            'We take all your memories and encrypt them with a password you set, then we upload them to a secure server. '
                            '\n\nLater, whenever you want to recover your memories, you will need to provide the same password and the UID to decrypt your data and import it.',
                          ),
                          actions: [
                            TextButton(
                                onPressed: () {
                                  Navigator.of(context).pop();
                                },
                                child: const Text(
                                  'Close',
                                  style: TextStyle(color: Colors.white),
                                ))
                          ],
                        ));
              },
              icon: const Icon(color: Colors.white, Icons.info_outline))
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(8),
        child: ListView(
          children: [
            const SizedBox(height: 16),
            CheckboxListTile(
              contentPadding: const EdgeInsets.fromLTRB(16, 0, 8, 0),
              title: const Text(
                'Enable',
                style: TextStyle(fontSize: 16),
              ),
              subtitle: const Text('Enable cloud stored encrypted backups'),
              value: backupsEnabled,
              checkboxShape: const CircleBorder(),
              onChanged: (v) async {
                if (v! && !hasPasswordSet) {
                  await Navigator.of(context).push(MaterialPageRoute(builder: (c) => const BackupPasswordPage()));
                  hasPasswordSet = SharedPreferencesUtil().hasBackupPassword;
                  if (!hasPasswordSet) {
                    _snackBar('You must set a password to enable backups.', seconds: 2);
                    return;
                  }
                }

                SharedPreferencesUtil().backupsEnabled = v;
                setState(() => backupsEnabled = v);
                if (v) {
                  executeBackup().then((_) => setState(() {}));
                  _snackBar('Backups enabled  🎉');
                  MixpanelManager().backupsEnabled();
                } else if (SharedPreferencesUtil().lastBackupDate != '') {
                  SharedPreferencesUtil().lastBackupDate = '';
                  setState(() {});
                  deleteBackupApi();
                  _snackBar('Backups disabled  ✔');
                  MixpanelManager().backupsDisabled();
                }
              },
            ),
            ListTile(
              title: const Text('User ID'),
              subtitle: Text(SharedPreferencesUtil().uid),
              onTap: () {
                Clipboard.setData(ClipboardData(text: SharedPreferencesUtil().uid));
                _snackBar('Copied to clipboard  ✅');
                MixpanelManager().userIDCopied();
              },
              trailing: const Icon(Icons.copy, size: 20),
            ),
            timeAgo.isNotEmpty ? const SizedBox(height: 32) : Container(),
            timeAgo.isNotEmpty
                ? ListTile(
                    title: const Text('Last backup'),
                    subtitle: Text(timeAgo),
                    onTap: backupInProgress
                        ? null
                        : () async {
                            setState(() => backupInProgress = true);
                            await executeBackup();
                            setState(() {});
                            _snackBar('Backup completed  🎉');
                            setState(() => backupInProgress = false);
                          },
                    trailing: backupInProgress
                        ? const SizedBox(
                            height: 16,
                            width: 16,
                            child: CircularProgressIndicator(
                              color: Colors.white,
                              strokeWidth: 2,
                            ),
                          )
                        : const Icon(Icons.refresh, size: 20),
                  )
                : const SizedBox(),
            backupsEnabled
                ? ListTile(
                    title: Text(hasPasswordSet ? 'Change password' : 'Set up a password'),
                    trailing: const Icon(Icons.chevron_right_sharp, size: 28),
                    onTap: () async {
                      await Navigator.of(context).push(MaterialPageRoute(builder: (c) => const BackupPasswordPage()));
                      hasPasswordSet = SharedPreferencesUtil().hasBackupPassword;
                      await executeBackup();
                      setState(() {});
                    },
                  )
                : const SizedBox(),
            const SizedBox(height: 32),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Text(
                'IMPORTANT',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  decoration: TextDecoration.underline,
                ),
              ),
            ),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                'Store your User ID and Password in a safe place, this is what you will need later when trying to recover your memories in another device or when you had to reinstall the app.',
                style: TextStyle(color: Colors.white),
              ),
            ),
            const SizedBox(height: 64),
            SharedPreferencesUtil().devModeEnabled
                ? const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 16),
                    child: Text('Dev Mode Only 👩‍💻',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        )))
                : const SizedBox(),
            SharedPreferencesUtil().devModeEnabled ? const SizedBox(height: 8) : const SizedBox(),
            SharedPreferencesUtil().devModeEnabled
                ? ListTile(
                    title: const Text('Export Memories'),
                    subtitle: const Text('Export all your memories to a JSON file.'),
                    trailing: loadingExportMemories
                        ? const SizedBox(
                            height: 16,
                            width: 16,
                            child: CircularProgressIndicator(
                              color: Colors.white,
                              strokeWidth: 2,
                            ),
                          )
                        : const Icon(Icons.upload),
                    onTap: loadingExportMemories
                        ? null
                        : () async {
                            if (loadingExportMemories) return;
                            setState(() => loadingExportMemories = true);
                            File file = await MemoryProvider().exportMemoriesToFile();
                            final result =
                                await Share.shareXFiles([XFile(file.path)], text: 'Exported Memories from Friend');
                            if (result.status == ShareResultStatus.success) {
                              debugPrint('Thank you for sharing the picture!');
                            }
                            MixpanelManager().exportMemories();
                            // 54d2c392-57f1-46dc-b944-02740a651f7b
                            setState(() => loadingExportMemories = false);
                          },
                  )
                : const SizedBox(),
            SharedPreferencesUtil().devModeEnabled
                ? ListTile(
                    title: const Text('Import Memories'),
                    subtitle: const Text('Use with caution. All memories in the JSON file will be imported.'),
                    trailing: loadingImportMemories
                        ? const SizedBox(
                            height: 16,
                            width: 16,
                            child: CircularProgressIndicator(
                              color: Colors.white,
                              strokeWidth: 2,
                            ),
                          )
                        : const Icon(Icons.download),
                    onTap: () async {
                      if (loadingImportMemories) return;
                      setState(() => loadingImportMemories = true);
                      // open file picker
                      var file = await FilePicker.platform.pickFiles(
                        type: FileType.custom,
                        allowedExtensions: ['json'],
                      );
                      MixpanelManager().importMemories();
                      if (file == null) {
                        setState(() => loadingImportMemories = false);
                        return;
                      }
                      var xFile = file.files.first.xFile;
                      try {
                        var content = (await xFile.readAsString());
                        var decoded = jsonDecode(content);
                        List<Memory> memories = decoded.map<Memory>((e) => Memory.fromJson(e)).toList();
                        MemoryProvider().storeMemories(memories);
                        for (var i = 0; i < memories.length; i++) {
                          var memory = memories[i];
                          if (memory.structured.target == null || memory.discarded) continue;
                          var f = getEmbeddingsFromInput(memory.structured.target.toString()).then((vector) {
                            createPineconeVector(memory.id.toString(), vector, memory.createdAt);
                          });
                          if (i % 10 == 0) {
                            await f; // "wait" for previous 10 requests to finish
                            await Future.delayed(const Duration(seconds: 1));
                            debugPrint('Processing Memory: $i');
                          }
                        }
                        _snackBar('Memories imported, restart the app to see the changes. 🎉', seconds: 3);
                        MixpanelManager().importedMemories();
                      } catch (e) {
                        debugPrint(e.toString());
                        _snackBar('Make sure the file is a valid JSON file.');
                      }
                      setState(() => loadingImportMemories = false);
                    },
                  )
                : Container(),
          ],
        ),
      ),
    );
  }

  _snackBar(String content, {int seconds = 1}) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(content),
      duration: Duration(seconds: seconds),
    ));
  }
}

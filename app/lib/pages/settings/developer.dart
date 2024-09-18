import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/providers/developer_mode_provider.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

class DeveloperSettingsPage extends StatefulWidget {
  const DeveloperSettingsPage({super.key});

  @override
  State<DeveloperSettingsPage> createState() => _DeveloperSettingsPageState();
}

class _DeveloperSettingsPageState extends State<DeveloperSettingsPage> {
  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (context) => DeveloperModeProvider(),
      child: const _DeveloperSettingsPage(),
    );
  }
}

class _DeveloperSettingsPage extends StatefulWidget {
  const _DeveloperSettingsPage();

  @override
  State<_DeveloperSettingsPage> createState() => __DeveloperSettingsPageState();
}

class __DeveloperSettingsPageState extends State<_DeveloperSettingsPage> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Provider.of<DeveloperModeProvider>(context, listen: false).initialize();
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Consumer<DeveloperModeProvider>(
        builder: (context, provider, child) {
          return Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar: AppBar(
              backgroundColor: Theme.of(context).colorScheme.primary,
              title: const Text('Developer Settings'),
              actions: [
                TextButton(
                  onPressed: provider.savingSettingsLoading ? null : provider.saveSettings,
                  child: const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 4.0),
                    child: Text(
                      'Save',
                      style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 16),
                    ),
                  ),
                )
              ],
            ),
            body: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: ListView(
                children: [
                  const SizedBox(height: 32),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 0),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        'Transcription Model',
                        style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Center(
                    child: Container(
                      height: 60,
                      decoration: BoxDecoration(
                        border: Border.all(color: Colors.white),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      padding: const EdgeInsets.only(left: 16, right: 12, top: 8, bottom: 10),
                      child: DropdownButton<String>(
                        menuMaxHeight: 350,
                        value: SharedPreferencesUtil().transcriptionModel,
                        onChanged: (newValue) {
                          if (newValue == null) return;
                          if (newValue == SharedPreferencesUtil().transcriptionModel) return;
                          setState(() => SharedPreferencesUtil().transcriptionModel = newValue);

                          if (newValue == 'soniox') {
                            showDialog(
                              context: context,
                              barrierDismissible: false,
                              builder: (c) => getDialog(
                                context,
                                () => Navigator.of(context).pop(),
                                () => {},
                                'Model Limitations',
                                'Soniox model is only available for English, and with devices with latest firmware version 1.0.4. '
                                    'If you use a different configuration, it will fallback to deepgram.',
                                singleButton: true,
                              ),
                            );
                          }
                          // setState(() => _selectedLanguage = newValue);
                          // SharedPreferencesUtil().recordingsLanguage = _selectedLanguage;
                          // MixpanelManager().recordingLanguageChanged(_selectedLanguage);
                        },
                        dropdownColor: Colors.black,
                        style: const TextStyle(color: Colors.white, fontSize: 16),
                        underline: Container(height: 0, color: Colors.white),
                        isExpanded: true,
                        itemHeight: 48,
                        items: ['deepgram', 'soniox'].map<DropdownMenuItem<String>>((String value) {
                          return DropdownMenuItem<String>(
                            value: value,
                            child: Text(
                              value,
                              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                            ),
                          );
                        }).toList(),
                      ),
                    ),
                  ),
                  const SizedBox(height: 32.0),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Export Memories'),
                    subtitle: const Text('Export all your memories to a JSON file.'),
                    trailing: provider.loadingExportMemories
                        ? const SizedBox(
                            height: 16,
                            width: 16,
                            child: CircularProgressIndicator(
                              color: Colors.white,
                              strokeWidth: 1,
                            ),
                          )
                        : const Icon(Icons.upload),
                    onTap: provider.loadingExportMemories
                        ? null
                        : () async {
                            if (provider.loadingExportMemories) return;
                            setState(() => provider.loadingExportMemories = true);
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Memories Export Started. This may take a few seconds, please wait.'),
                                duration: Duration(seconds: 3),
                              ),
                            );
                            List<ServerMemory> memories = await getMemories(limit: 10000, offset: 0); // 10k for now
                            String json = const JsonEncoder.withIndent("     ").convert(memories);
                            final directory = await getApplicationDocumentsDirectory();
                            final file = File('${directory.path}/memories.json');
                            await file.writeAsString(json);

                            final result =
                                await Share.shareXFiles([XFile(file.path)], text: 'Exported Memories from Friend');
                            if (result.status == ShareResultStatus.success) {
                              debugPrint('Thank you for sharing the picture!');
                            }
                            MixpanelManager().exportMemories();
                            setState(() => provider.loadingExportMemories = false);
                          },
                  ),
                  const SizedBox(height: 16),
                  Divider(color: Colors.grey.shade500),
                  const SizedBox(height: 32),
                  const Text(
                    'Google Cloud Bucket',
                    style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Export new memories audio to Google Cloud Storage.',
                    style: TextStyle(color: Colors.grey.shade200, fontSize: 14),
                  ),
                  const SizedBox(height: 16.0),
                  TextField(
                    controller: provider.gcpCredentialsController,
                    obscureText: false,
                    autocorrect: false,
                    enableSuggestions: false,
                    enabled: true,
                    decoration: _getTextFieldDecoration('GCP Credentials (Base64)'),
                    style: const TextStyle(color: Colors.white),
                  ),
                  TextField(
                    controller: provider.gcpBucketNameController,
                    obscureText: false,
                    autocorrect: false,
                    enabled: true,
                    enableSuggestions: false,
                    decoration: _getTextFieldDecoration('GCP Bucket Name'),
                    style: const TextStyle(color: Colors.white),
                  ),
                  // KEEP ME?
                  // ListTile(
                  //   title: const Text('Import Memories'),
                  //   subtitle: const Text('Use with caution. All memories in the JSON file will be imported.'),
                  //   contentPadding: EdgeInsets.zero,
                  //   trailing: provider.loadingImportMemories
                  //       ? const SizedBox(
                  //           height: 16,
                  //           width: 16,
                  //           child: CircularProgressIndicator(
                  //             color: Colors.white,
                  //             strokeWidth: 2,
                  //           ),
                  //         )
                  //       : const Icon(Icons.download),
                  //   onTap: () async {
                  //     if (provider.loadingImportMemories) return;
                  //     setState(() => provider.loadingImportMemories = true);
                  //     // open file picker
                  //     var file = await FilePicker.platform.pickFiles(
                  //       type: FileType.custom,
                  //       allowedExtensions: ['json'],
                  //     );
                  //     MixpanelManager().importMemories();
                  //     if (file == null) {
                  //       setState(() => provider.loadingImportMemories = false);
                  //       return;
                  //     }
                  //     var xFile = file.files.first.xFile;
                  //     try {
                  //       var content = (await xFile.readAsString());
                  //       var decoded = jsonDecode(content);
                  //       // Export uses [ServerMemory] structure
                  //       List<ServerMemory> memories =
                  //           decoded.map<ServerMemory>((e) => ServerMemory.fromJson(e)).toList();
                  //       debugPrint('Memories: $memories');
                  //       var memoriesJson = memories.map((m) => m.toJson()).toList();
                  //       bool result = await migrateMemoriesToBackend(memoriesJson);
                  //       if (!result) {
                  //         SharedPreferencesUtil().scriptMigrateMemoriesToBack = false;
                  //         _snackBar('Failed to import memories. Make sure the file is a valid JSON file.', seconds: 3);
                  //       }
                  //       _snackBar('Memories imported, restart the app to see the changes. 🎉', seconds: 3);
                  //       MixpanelManager().importedMemories();
                  //       SharedPreferencesUtil().scriptMigrateMemoriesToBack = true;
                  //     } catch (e) {
                  //       debugPrint(e.toString());
                  //       _snackBar('Make sure the file is a valid JSON file.');
                  //     }
                  //     setState(() => provider.loadingImportMemories = false);
                  //   },
                  // ),
                  const SizedBox(height: 16),
                  Divider(color: Colors.grey.shade500),
                  const SizedBox(height: 32),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Events Webhooks',
                        style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                      ),
                      GestureDetector(
                        onTap: () {
                          launchUrl(Uri.parse('https://docs.omi.me/developer/plugins/Integrations/'));
                          MixpanelManager().pageOpened('Advanced Mode Docs');
                        },
                        child: const Padding(
                          padding: EdgeInsets.all(8.0),
                          child: Text(
                            'Docs',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  const Text(
                    'On memory created:',
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  ),
                  // const SizedBox(height: 4),
                  // const Text(
                  //   'Triggered when FRIEND creates a new memory.',
                  //   style: TextStyle(color: Colors.white, fontSize: 14),
                  // ),
                  TextField(
                    controller: provider.webhookOnMemoryCreated,
                    obscureText: false,
                    autocorrect: false,
                    enabled: true,
                    enableSuggestions: false,
                    decoration: _getTextFieldDecoration('Endpoint URL'),
                    style: const TextStyle(color: Colors.white),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'Real-time transcript received:',
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  ),
                  // const SizedBox(height: 4),
                  // const Text(
                  //   'Triggered as the transcript is being received.',
                  //   style: TextStyle(color: Colors.white, fontSize: 14),
                  // ),
                  TextField(
                    controller: provider.webhookOnTranscriptReceived,
                    obscureText: false,
                    autocorrect: false,
                    enabled: true,
                    enableSuggestions: false,
                    decoration: _getTextFieldDecoration('Endpoint URL'),
                    style: const TextStyle(color: Colors.white),
                  ),
                  const SizedBox(height: 64),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  _getTextFieldDecoration(String label, {IconButton? suffixIcon, bool canBeDisabled = false, String hintText = ''}) {
    return InputDecoration(
      labelText: label,
      enabled: true && canBeDisabled,
      hintText: hintText,
      // labelText: hintText,
      labelStyle: const TextStyle(
        fontSize: 16,
        color: Colors.grey,
        decoration: TextDecoration.underline,
      ),
      // bottom border
      enabledBorder: InputBorder.none,
      focusedBorder: const UnderlineInputBorder(
        borderSide: BorderSide(color: Colors.grey),
      ),
      suffixIcon: suffixIcon,
    );
  }

  _snackBar(String content, {int seconds = 1}) {
    AppSnackbar.showSnackbar(
      content,
      duration: Duration(seconds: seconds),
    );
  }
}

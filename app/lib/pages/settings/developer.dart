import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/providers/developer_mode_provider.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
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
                MaterialButton(
                  onPressed: provider.savingSettingsLoading ? null : provider.saveSettings,
                  color: Colors.transparent,
                  elevation: 0,
                  child: const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 4.0),
                    child: Text(
                      'Save',
                      style: TextStyle(color: Colors.deepPurple, fontWeight: FontWeight.w600, fontSize: 16),
                    ),
                  ),
                )
              ],
            ),
            body: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: ListView(
                children: [
                  const SizedBox(height: 32),
                  _getText('Store your audios in Google Cloud Storage', bold: true),
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
                  const SizedBox(height: 16),
                  ListTile(
                    title: const Text('Import Memories'),
                    subtitle: const Text('Use with caution. All memories in the JSON file will be imported.'),
                    contentPadding: EdgeInsets.zero,
                    trailing: provider.loadingImportMemories
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
                      if (provider.loadingImportMemories) return;
                      setState(() => provider.loadingImportMemories = true);
                      // open file picker
                      var file = await FilePicker.platform.pickFiles(
                        type: FileType.custom,
                        allowedExtensions: ['json'],
                      );
                      MixpanelManager().importMemories();
                      if (file == null) {
                        setState(() => provider.loadingImportMemories = false);
                        return;
                      }
                      var xFile = file.files.first.xFile;
                      try {
                        var content = (await xFile.readAsString());
                        var decoded = jsonDecode(content);
                        // Export uses [ServerMemory] structure
                        List<ServerMemory> memories =
                            decoded.map<ServerMemory>((e) => ServerMemory.fromJson(e)).toList();
                        debugPrint('Memories: $memories');
                        var memoriesJson = memories.map((m) => m.toJson()).toList();
                        bool result = await migrateMemoriesToBackend(memoriesJson);
                        if (!result) {
                          SharedPreferencesUtil().scriptMigrateMemoriesToBack = false;
                          _snackBar('Failed to import memories. Make sure the file is a valid JSON file.', seconds: 3);
                        }
                        _snackBar('Memories imported, restart the app to see the changes. 🎉', seconds: 3);
                        MixpanelManager().importedMemories();
                        SharedPreferencesUtil().scriptMigrateMemoriesToBack = true;
                      } catch (e) {
                        debugPrint(e.toString());
                        _snackBar('Make sure the file is a valid JSON file.');
                      }
                      setState(() => provider.loadingImportMemories = false);
                    },
                  ),
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
                              strokeWidth: 2,
                            ),
                          )
                        : const Icon(Icons.upload),
                    onTap: provider.loadingExportMemories
                        ? null
                        : () async {
                            if (provider.loadingExportMemories) return;
                            setState(() => provider.loadingExportMemories = true);
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
                            // 54d2c392-57f1-46dc-b944-02740a651f7b
                            setState(() => provider.loadingExportMemories = false);
                          },
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const SizedBox(height: 20),
                      Container(
                        width: double.infinity,
                        height: 2,
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      const SizedBox(height: 20),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text('Plugin Integrations Testing',
                              style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
                          GestureDetector(
                              onTap: () {
                                launchUrl(Uri.parse('https://docs.omi.me/developer/plugins/Integrations/'));
                                MixpanelManager().advancedModeDocsOpened();
                              },
                              child: const Padding(
                                padding: EdgeInsets.all(8.0),
                                child: Text(
                                  'Docs',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 14,
                                    decoration: TextDecoration.underline,
                                  ),
                                ),
                              ))
                        ],
                      ),
                      const SizedBox(height: 16),
                      const Text(
                        'On Memory Created:',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 16),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Triggered when FRIEND creates a new memory.',
                        style: TextStyle(color: Colors.white, fontSize: 14),
                      ),
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
                        'Real-Time Transcript Processing:',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 16),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Triggered as the transcript is being received.',
                        style: TextStyle(color: Colors.white, fontSize: 14),
                      ),
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

  _getText(String text, {bool canBeDisabled = false, bool underline = false, bool bold = false}) {
    return Text(
      text,
      style: TextStyle(
        color: true && canBeDisabled ? Colors.white.withOpacity(0.2) : Colors.white,
        decoration: underline ? TextDecoration.underline : TextDecoration.none,
        fontSize: 16,
        fontWeight: bold ? FontWeight.w600 : FontWeight.normal,
      ),
      // textAlign: TextAlign.center,
    );
  }
}

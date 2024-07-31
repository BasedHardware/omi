import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

class DeveloperSettingsPage extends StatefulWidget {
  const DeveloperSettingsPage({super.key});

  @override
  State<DeveloperSettingsPage> createState() => _DeveloperSettingsPageState();
}

class _DeveloperSettingsPageState extends State<DeveloperSettingsPage> {
  final TextEditingController gcpCredentialsController = TextEditingController();
  final TextEditingController gcpBucketNameController = TextEditingController();
  final TextEditingController deepgramAPIKeyController = TextEditingController();
  final TextEditingController openAIKeyController = TextEditingController();
  final TextEditingController webhookOnMemoryCreated = TextEditingController();
  final TextEditingController webhookOnTranscriptReceived = TextEditingController();

  bool savingSettingsLoading = false;
  bool useTranscriptServer = false;

  bool loadingExportMemories = false;
  bool loadingImportMemories = false;

  @override
  void initState() {
    openAIKeyController.text = SharedPreferencesUtil().openAIApiKey;
    useTranscriptServer = SharedPreferencesUtil().useTranscriptServer;
    deepgramAPIKeyController.text = SharedPreferencesUtil().deepgramApiKey;
    gcpCredentialsController.text = SharedPreferencesUtil().gcpCredentials;
    gcpBucketNameController.text = SharedPreferencesUtil().gcpBucketName;
    webhookOnMemoryCreated.text = SharedPreferencesUtil().webhookOnMemoryCreated;
    webhookOnTranscriptReceived.text = SharedPreferencesUtil().webhookOnTranscriptReceived;
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.primary,
          title: const Text('Developer Settings'),
          actions: [
            MaterialButton(
              onPressed: savingSettingsLoading ? null : saveSettings,
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
              _getText('Your own Developer Keys', bold: true),
              const SizedBox(height: 16.0),
              TextField(
                controller: openAIKeyController,
                obscureText: false,
                autocorrect: false,
                enabled: true,
                enableSuggestions: false,
                decoration: _getTextFieldDecoration('Open AI Key', hintText: 'sk-.......'),
                style: const TextStyle(color: Colors.white),
              ),
              const SizedBox(height: 16.0),
              // CheckboxListTile(
              //   contentPadding: EdgeInsets.zero,
              //   value: useDeepgram,
              //   onChanged: (s) {
              //     setState(() {
              //       useDeepgram = s!;
              //     });
              //   },
              //   title: const Text('Enable Deepgram'),
              //   checkboxShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
              // ),
              TextField(
                controller: deepgramAPIKeyController,
                obscureText: false,
                autocorrect: false,
                enabled: true,
                enableSuggestions: false,
                decoration: _getTextFieldDecoration('Deepgram API Key', hintText: ''),
                style: const TextStyle(color: Colors.white),
              ),
              const SizedBox(height: 40),
              _getText('Store your audios in Google Cloud Storage', bold: true),
              const SizedBox(height: 16.0),
              TextField(
                controller: gcpCredentialsController,
                obscureText: false,
                autocorrect: false,
                enableSuggestions: false,
                enabled: true,
                decoration: _getTextFieldDecoration('GCP Credentials (Base64)'),
                style: const TextStyle(color: Colors.white),
              ),
              TextField(
                controller: gcpBucketNameController,
                obscureText: false,
                autocorrect: false,
                enabled: true,
                enableSuggestions: false,
                decoration: _getTextFieldDecoration('GCP Bucket Name'),
                style: const TextStyle(color: Colors.white),
              ),
              const SizedBox(height: 16),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: useTranscriptServer,
                onChanged: (s) {
                  if (s == null) return;
                  if (!s) {
                    getDialog(
                      context,
                      () => Navigator.of(context).pop(),
                      () {
                        setState(() => useTranscriptServer = true);
                        Navigator.of(context).pop();
                      },
                      'Disabling Transcript Server',
                      'Disabling the transcript server means that you will be using deepgram and not based hardware for transcription. '
                          'This also means that some features will not be available.',
                    );
                    showDialog(
                      context: context,
                      builder: (c) => getDialog(
                        context,
                        () => Navigator.of(context).pop(),
                        () {
                          setState(() => useTranscriptServer = false);
                          Navigator.of(context).pop();
                        },
                        'Disabling Transcript Server',
                        'Disabling the transcript server means that you will be using deepgram and not based hardware for transcription. '
                            'This also means that some features will not be available.',
                      ),
                    );
                  } else {
                    setState(() => useTranscriptServer = s);
                  }
                },
                title: const Text('Transcript Server Enabled'),
                checkboxShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              SharedPreferencesUtil().devModeEnabled
                  ? ListTile(
                      contentPadding: EdgeInsets.zero,
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
                      contentPadding: EdgeInsets.zero,
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
                              upsertPineconeVector(memory.id.toString(), vector, memory.createdAt);
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
                        launchUrl(Uri.parse('https://docs.basedhardware.com/developer/plugins/Integrations/'));
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
                controller: webhookOnMemoryCreated,
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
                controller: webhookOnTranscriptReceived,
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
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(content),
      duration: Duration(seconds: seconds),
    ));
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

  void saveSettings() async {
    if (savingSettingsLoading) return;
    setState(() => savingSettingsLoading = true);
    final prefs = SharedPreferencesUtil();
    if (gcpCredentialsController.text.isNotEmpty && gcpBucketNameController.text.isNotEmpty) {
      try {
        await authenticateGCP(base64: gcpCredentialsController.text.trim());
      } catch (e) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Invalid GCP credentials or bucket name. Please check and try again.'),
        ));
        setState(() => savingSettingsLoading = false);
        return;
      }
    }

    // TODO: test openai + deepgram keys + bucket existence, before saving

    prefs.gcpCredentials = gcpCredentialsController.text.trim();
    prefs.gcpBucketName = gcpBucketNameController.text.trim();
    prefs.openAIApiKey = openAIKeyController.text.trim();
    prefs.deepgramApiKey = deepgramAPIKeyController.text.trim();
    prefs.webhookOnMemoryCreated = webhookOnMemoryCreated.text.trim();
    prefs.webhookOnTranscriptReceived = webhookOnTranscriptReceived.text.trim();
    prefs.useTranscriptServer = useTranscriptServer;

    MixpanelManager().settingsSaved();
    setState(() => savingSettingsLoading = false);
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Settings saved!')));
  }
}

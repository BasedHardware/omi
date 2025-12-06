import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:flutter/services.dart';
import 'package:omi/pages/settings/widgets/create_mcp_api_key_dialog.dart';
import 'package:omi/pages/settings/widgets/mcp_api_key_list_item.dart';
import 'package:omi/pages/settings/widgets/developer_api_keys_section.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/providers/dev_api_key_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/backend/preferences.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import 'widgets/appbar_with_banner.dart';
import 'widgets/toggle_section_widget.dart';

class DeveloperSettingsPage extends StatefulWidget {
  const DeveloperSettingsPage({super.key});

  @override
  State<DeveloperSettingsPage> createState() => _DeveloperSettingsPageState();
}

class _DeveloperSettingsPageState extends State<DeveloperSettingsPage> {
  late final DevApiKeyProvider _devApiKeyProvider;

  @override
  void initState() {
    super.initState();
    _devApiKeyProvider = DevApiKeyProvider();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Provider.of<DeveloperModeProvider>(context, listen: false).initialize();
      context.read<McpProvider>().fetchKeys();
      _devApiKeyProvider.fetchKeys();
    });
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: _devApiKeyProvider,
      child: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Consumer<DeveloperModeProvider>(
          builder: (context, provider, child) {
            return Scaffold(
              backgroundColor: Theme.of(context).colorScheme.primary,
              appBar: AppBarWithBanner(
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
                          style: TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                        ),
                      ),
                    )
                  ],
                ),
                showAppBar: provider.savingSettingsLoading,
                child: Container(
                  color: Colors.green,
                  child: const Center(
                    child: Text(
                      'Syncing Developer Settings...',
                      style: TextStyle(color: Colors.white, fontSize: 12),
                    ),
                  ),
                ),
              ),
              body: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    const SizedBox(height: 24),
                    const Text(
                      'Debug Logs',
                      style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Helps diagnose issues. Auto-deletes after 3 days.',
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                    ),
                    const SizedBox(height: 16),
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1A1A1A),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFF2C2C2E), width: 1),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text(
                                'Enable Debug Logs',
                                style: TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                              ),
                              Switch(
                                value: SharedPreferencesUtil().devLogsToFileEnabled,
                                onChanged: (v) async {
                                  await DebugLogManager.setEnabled(v);
                                  setState(() {});
                                },
                                activeColor: const Color(0xFF8B5CF6),
                              ),
                            ],
                          ),
                          const SizedBox(height: 16),
                          Row(
                            children: [
                              Expanded(
                                child: GestureDetector(
                                  onTap: () async {
                                    final files = await DebugLogManager.listLogFiles();
                                    if (files.isEmpty) {
                                      AppSnackbar.showSnackbarError('No log files found.');
                                      return;
                                    }
                                    if (files.length == 1) {
                                      final result =
                                          await Share.shareXFiles([XFile(files.first.path)], text: 'Omi debug log');
                                      if (result.status == ShareResultStatus.success) {
                                        debugPrint('Log shared');
                                      }
                                      return;
                                    }

                                    if (!mounted) return;
                                    final selected = await showModalBottomSheet<File>(
                                      context: context,
                                      backgroundColor: Theme.of(context).colorScheme.primary,
                                      shape: const RoundedRectangleBorder(
                                        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                                      ),
                                      builder: (ctx) {
                                        return SafeArea(
                                          child: ListView.separated(
                                            shrinkWrap: true,
                                            itemCount: files.length,
                                            separatorBuilder: (_, __) =>
                                                Divider(color: Colors.grey.shade800, height: 1),
                                            itemBuilder: (ctx, i) {
                                              final f = files[i];
                                              final name = f.uri.pathSegments.last;
                                              return ListTile(
                                                title: Text(name, style: const TextStyle(color: Colors.white)),
                                                trailing: const Icon(Icons.chevron_right, color: Colors.white70),
                                                onTap: () => Navigator.of(ctx).pop(f),
                                              );
                                            },
                                          ),
                                        );
                                      },
                                    );

                                    if (selected != null) {
                                      final result =
                                          await Share.shareXFiles([XFile(selected.path)], text: 'Omi debug log');
                                      if (result.status == ShareResultStatus.success) {
                                        debugPrint('Log shared');
                                      }
                                    }
                                  },
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                                    decoration: BoxDecoration(
                                      gradient: const LinearGradient(
                                        colors: [Color(0xFF8B5CF6), Color(0xFF7C3AED)],
                                      ),
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: const Row(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        Icon(Icons.upload_file, color: Colors.white, size: 18),
                                        SizedBox(width: 8),
                                        Text(
                                          'Share Logs',
                                          style: TextStyle(
                                            color: Colors.white,
                                            fontSize: 14,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              GestureDetector(
                                onTap: () async {
                                  await DebugLogManager.clear();
                                  AppSnackbar.showSnackbar('Debug log cleared');
                                },
                                child: Container(
                                  padding: const EdgeInsets.all(12),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFEF4444).withValues(alpha: 0.1),
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: const Icon(
                                    Icons.delete_outline,
                                    color: Color(0xFFEF4444),
                                    size: 20,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),
                    //TODO: Model selection commented out because Soniox model is no longer being used
                    // const SizedBox(height: 32),
                    // const Padding(
                    //   padding: EdgeInsets.symmetric(horizontal: 0),
                    //   child: Align(
                    //     alignment: Alignment.centerLeft,
                    //     child: Text(
                    //       'Transcription Model',
                    //       style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                    //     ),
                    //   ),
                    // ),
                    // const SizedBox(height: 14),
                    // Center(
                    //   child: Container(
                    //     height: 60,
                    //     decoration: BoxDecoration(
                    //       border: Border.all(color: Colors.white),
                    //       borderRadius: BorderRadius.circular(14),
                    //     ),
                    //     padding: const EdgeInsets.only(left: 16, right: 12, top: 8, bottom: 10),
                    //     child: DropdownButton<String>(
                    //       menuMaxHeight: 350,
                    //       value: SharedPreferencesUtil().transcriptionModel,
                    //       onChanged: (newValue) {
                    //         if (newValue == null) return;
                    //         if (newValue == SharedPreferencesUtil().transcriptionModel) return;
                    //         setState(() => SharedPreferencesUtil().transcriptionModel = newValue);
                    //         if (newValue == 'soniox') {
                    //           showDialog(
                    //             context: context,
                    //             barrierDismissible: false,
                    //             builder: (c) => getDialog(
                    //               context,
                    //               () => Navigator.of(context).pop(),
                    //               () => {},
                    //               'Model Limitations',
                    //               'Soniox model is only available for English, and with devices with latest firmware version 1.0.4. '
                    //                   'If you use a different configuration, it will fallback to deepgram.',
                    //               singleButton: true,
                    //             ),
                    //           );
                    //         }
                    //       },
                    //       dropdownColor: Colors.black,
                    //       style: const TextStyle(color: Colors.white, fontSize: 16),
                    //       underline: Container(height: 0, color: Colors.white),
                    //       isExpanded: true,
                    //       itemHeight: 48,
                    //       items: ['deepgram', 'soniox'].map<DropdownMenuItem<String>>((String value) {
                    //         // 'speechmatics'
                    //         return DropdownMenuItem<String>(
                    //           value: value,
                    //           child: Text(
                    //             value == 'deepgram'
                    //                 ? 'Deepgram (faster)'
                    //                 : value == 'speechmatics'
                    //                     ? 'Speechmatics (Experimental)'
                    //                     : 'Soniox (better quality)',
                    //             style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                    //           ),
                    //         );
                    //       }).toList(),
                    //     ),
                    //   ),
                    // ),
                    const SizedBox(height: 32.0),
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Export Conversations'),
                      subtitle: const Text('Export all your conversations to a JSON file.'),
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
                                  content:
                                      Text('Conversations Export Started. This may take a few seconds, please wait.'),
                                  duration: Duration(seconds: 3),
                                ),
                              );
                              List<ServerConversation> memories =
                                  await getConversations(limit: 10000, offset: 0); // 10k for now
                              String json = const JsonEncoder.withIndent("     ").convert(memories);
                              final directory = await getApplicationDocumentsDirectory();
                              final file = File('${directory.path}/conversations.json');
                              await file.writeAsString(json);

                              final result =
                                  await Share.shareXFiles([XFile(file.path)], text: 'Exported Conversations from Omi');
                              if (result.status == ShareResultStatus.success) {
                                debugPrint('Thank you for sharing the picture!');
                              }
                              MixpanelManager().exportMemories();
                              setState(() => provider.loadingExportMemories = false);
                            },
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
                    const SizedBox(height: 16),
                    const DeveloperApiKeysSection(),
                    const SizedBox(height: 16),
                    Divider(color: Colors.grey.shade500),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'MCP',
                          style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w500),
                        ),
                        GestureDetector(
                          onTap: () {
                            launchUrl(Uri.parse('https://docs.omi.me/doc/developer/MCP'));
                            MixpanelManager().pageOpened('MCP Docs');
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
                    const SizedBox(height: 10),
                    Text(
                      'To connect Omi with other applications to read, search, and manage your memories and conversations. Create a key to get started.',
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'API Keys',
                          style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                        ),
                        GestureDetector(
                          onTap: () => showDialog(
                            context: context,
                            builder: (context) => const CreateMcpApiKeyDialog(),
                          ),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                            decoration: BoxDecoration(
                              gradient: const LinearGradient(
                                colors: [Color(0xFF8B5CF6), Color(0xFF7C3AED)],
                              ),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: const Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.add, color: Colors.white, size: 16),
                                SizedBox(width: 6),
                                Text(
                                  'Create',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    Consumer<McpProvider>(
                      builder: (context, provider, child) {
                        if (provider.isLoading && provider.keys.isEmpty) {
                          return const Padding(
                            padding: EdgeInsets.all(32.0),
                            child: Center(
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF8B5CF6)),
                              ),
                            ),
                          );
                        }
                        if (provider.error != null) {
                          return Center(
                            child: Padding(
                              padding: const EdgeInsets.all(16.0),
                              child: Text(
                                'Error: ${provider.error}',
                                style: const TextStyle(color: Color(0xFFEF4444)),
                              ),
                            ),
                          );
                        }
                        if (provider.keys.isEmpty) {
                          return Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(32),
                            decoration: BoxDecoration(
                              color: const Color(0xFF1A1A1A),
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(color: const Color(0xFF2C2C2E)),
                            ),
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.center,
                              children: [
                                Container(
                                  padding: const EdgeInsets.all(16),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF252525),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: const Icon(
                                    Icons.key_off,
                                    color: Color(0xFF6C6C70),
                                    size: 32,
                                  ),
                                ),
                                const SizedBox(height: 16),
                                const Text(
                                  'No API keys yet',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                                const SizedBox(height: 6),
                                const Text(
                                  'Create your first key to get started',
                                  style: TextStyle(
                                    color: Color(0xFF8E8E93),
                                    fontSize: 13,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              ],
                            ),
                          );
                        }
                        return Column(
                          children: provider.keys.map((key) => McpApiKeyListItem(apiKey: key)).toList(),
                        );
                      },
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'Claude Desktop Integration',
                      style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Add the following to your claude_desktop_config.json file. Remember to replace "your_api_key_here" with a valid key.',
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                    ),
                    const SizedBox(height: 16),
                    GestureDetector(
                      onTap: () {
                        const config = '''{
  "mcpServers": {
    "omi": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "-e", "OMI_API_KEY=your_api_key_here", "omiai/mcp-server:latest"]
    }
  }
}''';
                        Clipboard.setData(const ClipboardData(text: config));
                        AppSnackbar.showSnackbar('Claude config copied to clipboard.');
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                            colors: [Color(0xFF8B5CF6), Color(0xFF7C3AED)],
                          ),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.copy, color: Colors.white, size: 18),
                            SizedBox(width: 8),
                            Text(
                              'Copy Config',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Divider(color: Colors.grey.shade500),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Webhooks',
                          style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w500),
                        ),
                        GestureDetector(
                          onTap: () {
                            launchUrl(Uri.parse('https://docs.omi.me/doc/developer/apps/Introduction'));
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
                    const SizedBox(height: 10),
                    Text(
                      'Configure webhooks to receive real-time notifications about conversations, transcripts, and audio data.',
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                    ),
                    const SizedBox(height: 16),
                    ToggleSectionWidget(
                      isSectionEnabled: provider.conversationEventsToggled,
                      sectionTitle: 'Conversation Events',
                      sectionDescription: 'Triggers when a new conversation is created.',
                      options: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                          decoration: BoxDecoration(
                            color: const Color(0xFF252525),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: const Color(0xFF2C2C2E), width: 1),
                          ),
                          child: TextField(
                            controller: provider.webhookOnConversationCreated,
                            obscureText: false,
                            autocorrect: false,
                            enabled: true,
                            enableSuggestions: false,
                            decoration: const InputDecoration(
                              hintText: 'Endpoint URL',
                              hintStyle: TextStyle(color: Color(0xFF6C6C70), fontSize: 14),
                              border: InputBorder.none,
                              contentPadding: EdgeInsets.symmetric(vertical: 12),
                            ),
                            style: const TextStyle(color: Colors.white, fontSize: 14),
                          ),
                        ),
                        const SizedBox(height: 16),
                      ],
                      onSectionEnabledChanged: provider.onConversationEventsToggled,
                    ),
                    ToggleSectionWidget(
                        isSectionEnabled: provider.transcriptsToggled,
                        sectionTitle: 'Real-time Transcript',
                        sectionDescription: 'Triggers when a new transcript is received.',
                        options: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                            decoration: BoxDecoration(
                              color: const Color(0xFF252525),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: const Color(0xFF2C2C2E), width: 1),
                            ),
                            child: TextField(
                              controller: provider.webhookOnTranscriptReceived,
                              obscureText: false,
                              autocorrect: false,
                              enabled: true,
                              enableSuggestions: false,
                              decoration: const InputDecoration(
                                hintText: 'Endpoint URL',
                                hintStyle: TextStyle(color: Color(0xFF6C6C70), fontSize: 14),
                                border: InputBorder.none,
                                contentPadding: EdgeInsets.symmetric(vertical: 12),
                              ),
                              style: const TextStyle(color: Colors.white, fontSize: 14),
                            ),
                          ),
                          const SizedBox(height: 16),
                        ],
                        onSectionEnabledChanged: provider.onTranscriptsToggled),
                    ToggleSectionWidget(
                        isSectionEnabled: provider.audioBytesToggled,
                        sectionTitle: 'Realtime Audio Bytes',
                        sectionDescription: 'Triggers when audio bytes are received.',
                        options: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                            decoration: BoxDecoration(
                              color: const Color(0xFF252525),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: const Color(0xFF2C2C2E), width: 1),
                            ),
                            child: TextField(
                              controller: provider.webhookAudioBytes,
                              obscureText: false,
                              autocorrect: false,
                              enabled: true,
                              enableSuggestions: false,
                              decoration: const InputDecoration(
                                hintText: 'Endpoint URL',
                                hintStyle: TextStyle(color: Color(0xFF6C6C70), fontSize: 14),
                                border: InputBorder.none,
                                contentPadding: EdgeInsets.symmetric(vertical: 12),
                              ),
                              style: const TextStyle(color: Colors.white, fontSize: 14),
                            ),
                          ),
                          const SizedBox(height: 12),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                            decoration: BoxDecoration(
                              color: const Color(0xFF252525),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: const Color(0xFF2C2C2E), width: 1),
                            ),
                            child: TextField(
                              controller: provider.webhookAudioBytesDelay,
                              obscureText: false,
                              autocorrect: false,
                              enabled: true,
                              enableSuggestions: false,
                              keyboardType: TextInputType.number,
                              decoration: const InputDecoration(
                                hintText: 'Every x seconds',
                                hintStyle: TextStyle(color: Color(0xFF6C6C70), fontSize: 14),
                                border: InputBorder.none,
                                contentPadding: EdgeInsets.symmetric(vertical: 12),
                              ),
                              style: const TextStyle(color: Colors.white, fontSize: 14),
                            ),
                          ),
                          const SizedBox(height: 16),
                        ],
                        onSectionEnabledChanged: provider.onAudioBytesToggled),
                    ToggleSectionWidget(
                      isSectionEnabled: provider.daySummaryToggled,
                      sectionTitle: 'Day Summary',
                      sectionDescription: 'Triggers when day summary is generated.',
                      options: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                          decoration: BoxDecoration(
                            color: const Color(0xFF252525),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: const Color(0xFF2C2C2E), width: 1),
                          ),
                          child: TextField(
                            controller: provider.webhookDaySummary,
                            obscureText: false,
                            autocorrect: false,
                            enabled: true,
                            enableSuggestions: false,
                            decoration: const InputDecoration(
                              hintText: 'Endpoint URL',
                              hintStyle: TextStyle(color: Color(0xFF6C6C70), fontSize: 14),
                              border: InputBorder.none,
                              contentPadding: EdgeInsets.symmetric(vertical: 12),
                            ),
                            style: const TextStyle(color: Colors.white, fontSize: 14),
                          ),
                        ),
                        const SizedBox(height: 16),
                      ],
                      onSectionEnabledChanged: provider.onDaySummaryToggled,
                    ),

                    // const Text(
                    //   'Websocket Real-time audio bytes:',
                    //   style: TextStyle(color: Colors.white, fontSize: 16),
                    // ),
                    // TextField(
                    //   controller: provider.webhookAudioBytes,
                    //   obscureText: false,
                    //   autocorrect: false,
                    //   enabled: true,
                    //   enableSuggestions: false,
                    //   decoration: _getTextFieldDecoration('Endpoint URL'),
                    //   style: const TextStyle(color: Colors.white),
                    // ),
                    const SizedBox(height: 16),
                    Divider(color: Colors.grey.shade500),
                    const SizedBox(height: 16),
                    const Text(
                      'Experimental',
                      style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Try the latest experimental features from Omi Team.',
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                    ),
                    const SizedBox(height: 16),
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1A1A1A),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFF2C2C2E), width: 1),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Transcription service diagnostic status',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 15,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                const Text(
                                  'Enable detailed diagnostic messages from the transcription service',
                                  style: TextStyle(
                                    color: Color(0xFF8E8E93),
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Checkbox(
                            value: provider.transcriptionDiagnosticEnabled,
                            onChanged: provider.onTranscriptionDiagnosticChanged,
                            activeColor: const Color(0xFF8B5CF6),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1A1A1A),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFF2C2C2E), width: 1),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Auto-create and tag new speakers',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 15,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                const Text(
                                  'Automatically create a new person when a name is detected in the transcript.',
                                  style: TextStyle(
                                    color: Color(0xFF8E8E93),
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Checkbox(
                            value: provider.autoCreateSpeakersEnabled,
                            onChanged: provider.onAutoCreateSpeakersChanged,
                            activeColor: const Color(0xFF8B5CF6),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                    Divider(color: Colors.grey.shade500),
                    const SizedBox(height: 16),
                    const Text(
                      'Pilot Features',
                      style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'These features are tests and no support is guaranteed.',
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                    ),
                    const SizedBox(height: 16),
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1A1A1A),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFF2C2C2E), width: 1),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Expanded(
                            child: Text(
                              'Suggest follow up question',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 15,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          Checkbox(
                            value: provider.followUpQuestionEnabled,
                            onChanged: provider.onFollowUpQuestionChanged,
                            activeColor: const Color(0xFF8B5CF6),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

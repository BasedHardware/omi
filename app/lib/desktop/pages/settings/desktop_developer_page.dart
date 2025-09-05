import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:flutter/services.dart';
import 'package:omi/pages/settings/widgets/create_mcp_api_key_dialog.dart';
import 'package:omi/pages/settings/widgets/mcp_api_key_list_item.dart';
import 'package:omi/pages/settings/widgets/toggle_section_widget.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/backend/preferences.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

class DesktopDeveloperSettingsPage extends StatefulWidget {
  const DesktopDeveloperSettingsPage({super.key});

  @override
  State<DesktopDeveloperSettingsPage> createState() => _DesktopDeveloperSettingsPageState();
}

class _DesktopDeveloperSettingsPageState extends State<DesktopDeveloperSettingsPage> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Provider.of<DeveloperModeProvider>(context, listen: false).initialize();
      context.read<McpProvider>().fetchKeys();
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
                      style: TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                    ),
                  ),
                )
              ],
            ),
            body: Stack(
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: ListView(
                    shrinkWrap: true,
                    children: [
                      const SizedBox(height: 24),
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Debug logs', style: TextStyle(color: Colors.white)),
                        subtitle: const Text('Helps diagnose issues. Auto-deletes after 3 days.', style: TextStyle(color: Colors.white70)),
                        value: SharedPreferencesUtil().devLogsToFileEnabled,
                        onChanged: (v) async {
                          await DebugLogManager.setEnabled(v);
                          setState(() {});
                        },
                      ),
                      Row(
                        children: [
                          Expanded(
                            child: ElevatedButton.icon(
                              icon: const Icon(Icons.upload_file, size: 16, color: Colors.white),
                              label: const Text('Share Logs', style: TextStyle(color: Colors.white)),
                              onPressed: () async {
                                final files = await DebugLogManager.listLogFiles();
                                if (files.isEmpty) {
                                  AppSnackbar.showSnackbarError('No log files found.');
                                  return;
                                }
                                if (files.length == 1) {
                                  final result = await Share.shareXFiles([XFile(files.first.path)], text: 'Omi debug log');
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
                                        separatorBuilder: (_, __) => Divider(color: Colors.grey.shade800, height: 1),
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
                                  final result = await Share.shareXFiles([XFile(selected.path)], text: 'Omi debug log');
                                  if (result.status == ShareResultStatus.success) {
                                    debugPrint('Log shared');
                                  }
                                }
                              },
                              style: ElevatedButton.styleFrom(
                                foregroundColor: Colors.white,
                                backgroundColor: Colors.grey.shade700,
                                minimumSize: const Size(double.infinity, 40),
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          IconButton(
                            tooltip: 'Clear log',
                            onPressed: () async {
                              await DebugLogManager.clear();
                              AppSnackbar.showSnackbar('Debug log cleared');
                            },
                            icon: const Icon(Icons.delete_outline, color: Colors.white),
                          ),
                        ],
                      ),
                      const SizedBox(height: 32.0),
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Export Conversations', style: TextStyle(color: Colors.white)),
                        subtitle: const Text('Export all your conversations to a JSON file.', style: TextStyle(color: Colors.white70)),
                        trailing: provider.loadingExportMemories
                            ? const SizedBox(
                                height: 16,
                                width: 16,
                                child: CircularProgressIndicator(
                                  color: Colors.white,
                                  strokeWidth: 1,
                                ),
                              )
                            : const Icon(Icons.upload, color: Colors.white),
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
                          TextButton.icon(
                            onPressed: () => showDialog(
                              context: context,
                              builder: (context) => const CreateMcpApiKeyDialog(),
                            ),
                            icon: const Icon(Icons.add, color: Colors.white, size: 18),
                            label: const Text('Create Key', style: TextStyle(color: Colors.white)),
                            style: TextButton.styleFrom(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                            ),
                          )
                        ],
                      ),
                      const SizedBox(height: 10),
                      Consumer<McpProvider>(
                        builder: (context, provider, child) {
                          if (provider.isLoading && provider.keys.isEmpty) {
                            return const Center(child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white));
                          }
                          if (provider.error != null) {
                            return Center(child: Text('Error: \${provider.error}', style: const TextStyle(color: Colors.white)));
                          }
                          if (provider.keys.isEmpty) {
                            return const Center(
                              child: Padding(
                                padding: EdgeInsets.all(16.0),
                                child: Text('No API keys found. Create one to get started.', style: TextStyle(color: Colors.white70)),
                              ),
                            );
                          }
                          return Column(
                            children: provider.keys.map((key) => McpApiKeyListItem(apiKey: key)).toList(),
                          );
                        },
                      ),
                      const SizedBox(height: 32),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Advanced Settings',
                            style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w500),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      Divider(color: Colors.grey.shade500),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          const Text(
                            'Webhooks',
                            style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w500),
                          ),
                          const Spacer(),
                          GestureDetector(
                            onTap: () {
                              launchUrl(Uri.parse('https://docs.omi.me/docs/developer/apps/Introduction'));
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
                      const SizedBox(
                        height: 10,
                      ),
                      ToggleSectionWidget(
                        isSectionEnabled: provider.conversationEventsToggled,
                        sectionTitle: 'Conversation Events',
                        sectionDescription: 'Triggers when a new conversation is created.',
                        options: [
                          TextField(
                            controller: provider.webhookOnConversationCreated,
                            obscureText: false,
                            autocorrect: false,
                            enabled: true,
                            enableSuggestions: false,
                            decoration: _getTextFieldDecoration('Endpoint URL'),
                            style: const TextStyle(color: Colors.white),
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
                            TextField(
                              controller: provider.webhookOnTranscriptReceived,
                              obscureText: false,
                              autocorrect: false,
                              enabled: true,
                              enableSuggestions: false,
                              decoration: _getTextFieldDecoration('Endpoint URL'),
                              style: const TextStyle(color: Colors.white),
                            ),
                            const SizedBox(height: 16),
                          ],
                          onSectionEnabledChanged: provider.onTranscriptsToggled),
                      ToggleSectionWidget(
                          isSectionEnabled: provider.audioBytesToggled,
                          sectionTitle: 'Realtime Audio Bytes',
                          sectionDescription: 'Triggers when audio bytes are received.',
                          options: [
                            TextField(
                              controller: provider.webhookAudioBytes,
                              obscureText: false,
                              autocorrect: false,
                              enabled: true,
                              enableSuggestions: false,
                              decoration: _getTextFieldDecoration('Endpoint URL'),
                              style: const TextStyle(color: Colors.white),
                            ),
                            TextField(
                              controller: provider.webhookAudioBytesDelay,
                              obscureText: false,
                              autocorrect: false,
                              enabled: true,
                              enableSuggestions: false,
                              keyboardType: TextInputType.number,
                              decoration: _getTextFieldDecoration('Every x seconds'),
                              style: const TextStyle(color: Colors.white),
                            ),
                            const SizedBox(height: 16),
                          ],
                          onSectionEnabledChanged: provider.onAudioBytesToggled),
                      ToggleSectionWidget(
                        isSectionEnabled: provider.daySummaryToggled,
                        sectionTitle: 'Day Summary',
                        sectionDescription: 'Triggers when day summary is generated.',
                        options: [
                          TextField(
                            controller: provider.webhookDaySummary,
                            obscureText: false,
                            autocorrect: false,
                            enabled: true,
                            enableSuggestions: false,
                            decoration: _getTextFieldDecoration('Endpoint URL'),
                            style: const TextStyle(color: Colors.white),
                          ),
                          const SizedBox(height: 16),
                        ],
                        onSectionEnabledChanged: provider.onDaySummaryToggled,
                      ),
                      const SizedBox(height: 16),
                      Divider(color: Colors.grey.shade500),
                      const SizedBox(height: 32),
                      const Text(
                        'Experimental',
                        style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w500),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Try the latest experimental features from Omi Team.',
                        style: TextStyle(color: Colors.grey.shade200, fontSize: 14),
                      ),
                      const SizedBox(height: 16.0),
                      CheckboxListTile(
                        contentPadding: const EdgeInsets.all(0),
                        title: const Text(
                          'Transcription service diagnostic status',
                          style: TextStyle(color: Colors.white, fontSize: 16),
                        ),
                        subtitle: const Text(
                          'Enable detailed diagnostic messages from the transcription service',
                          style: TextStyle(color: Colors.grey, fontSize: 12),
                        ),
                        value: provider.transcriptionDiagnosticEnabled,
                        onChanged: provider.onTranscriptionDiagnosticChanged,
                      ),
                      const SizedBox(height: 16.0),
                      CheckboxListTile(
                        contentPadding: const EdgeInsets.all(0),
                        title: const Text(
                          'Auto-create and tag new speakers',
                          style: TextStyle(color: Colors.white, fontSize: 16),
                        ),
                        subtitle: const Text(
                          'Automatically create a new person when a name is detected in the transcript.',
                          style: TextStyle(color: Colors.grey, fontSize: 12),
                        ),
                        value: provider.autoCreateSpeakersEnabled,
                        onChanged: provider.onAutoCreateSpeakersChanged,
                      ),
                      const SizedBox(height: 16.0),
                      const SizedBox(height: 36),
                      const Text(
                        'Pilot Features',
                        style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w500),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'These features are tests and no support is guaranteed.',
                        style: TextStyle(color: Colors.grey.shade200, fontSize: 14),
                      ),
                      const SizedBox(height: 16.0),
                      CheckboxListTile(
                        contentPadding: const EdgeInsets.all(0),
                        title: const Text(
                          'Suggest follow up question',
                          style: TextStyle(color: Colors.white, fontSize: 16),
                        ),
                        value: provider.followUpQuestionEnabled,
                        onChanged: provider.onFollowUpQuestionChanged,
                      ),

                    ],
                  ),
                ),
                if (provider.savingSettingsLoading)
                  Container(
                    color: Colors.black54,
                    child: const Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          CircularProgressIndicator(color: Colors.white),
                          SizedBox(height: 16),
                          Text(
                            'Syncing Developer Settings...',
                            style: TextStyle(color: Colors.white, fontSize: 16),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
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
      labelStyle: const TextStyle(
        fontSize: 16,
        color: Colors.grey,
        decoration: TextDecoration.underline,
      ),
      enabledBorder: InputBorder.none,
      focusedBorder: const UnderlineInputBorder(
        borderSide: BorderSide(color: Colors.grey),
      ),
      suffixIcon: suffixIcon,
    );
  }
}

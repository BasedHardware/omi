import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/conversations.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/providers/developer_mode_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:friend_private/pages/settings/widgets.dart';

import 'widgets/appbar_with_banner.dart';
import 'widgets/toggle_section_widget.dart';

class DeveloperSettingsPage extends StatefulWidget {
  const DeveloperSettingsPage({super.key});

  @override
  State<DeveloperSettingsPage> createState() => _DeveloperSettingsPageState();
}

class _DeveloperSettingsPageState extends State<DeveloperSettingsPage> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Provider.of<DeveloperModeProvider>(context, listen: false).initialize();
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
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 16),
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
            body: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 16),
                  // Actions Section
                  Padding(
                    padding: const EdgeInsets.fromLTRB(4, 0, 0, 12),
                    child: Text(
                      'ACTIONS',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.5),
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                  CustomListTile(
                    title: 'Export Conversations',
                    onTap: provider.loadingExportMemories
                        ? () {}
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
                            List<ServerConversation> memories = await getConversations(limit: 10000, offset: 0);
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
                    icon: Icons.upload_outlined,
                    subtitle: 'Export all your conversations to a JSON file.',
                    trailingIcon: provider.loadingExportMemories ? null : Icons.chevron_right_rounded,
                    showChevron: false,
                  ),

                  // Webhooks Section
                  Padding(
                    padding: const EdgeInsets.fromLTRB(4, 32, 0, 12),
                    child: Text(
                      'WEBHOOKS',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.5),
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                  Container(
                    decoration: BoxDecoration(
                      color: const Color.fromARGB(255, 18, 18, 18),
                      borderRadius: BorderRadius.circular(12.0),
                      border: Border.all(
                        color: Colors.white.withOpacity(0.15),
                        width: 1,
                      ),
                    ),
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Column(
                      children: [
                        ToggleSectionWidget(
                          isSectionEnabled: provider.conversationEventsToggled,
                          sectionTitle: 'Conversation Events',
                          sectionDescription: 'Triggers when a new conversation is created.',
                          icon: Icons.chat_bubble_outline,
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
                        const SizedBox(height: 8),
                        ToggleSectionWidget(
                          isSectionEnabled: provider.transcriptsToggled,
                          sectionTitle: 'Real-time Transcript',
                          sectionDescription: 'Triggers when a new transcript is received.',
                          icon: Icons.text_snippet_outlined,
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
                          onSectionEnabledChanged: provider.onTranscriptsToggled,
                        ),
                        ToggleSectionWidget(
                          isSectionEnabled: provider.audioBytesToggled,
                          sectionTitle: 'Realtime Audio Bytes',
                          sectionDescription: 'Triggers when audio bytes are received.',
                          icon: Icons.multitrack_audio_outlined,
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
                          onSectionEnabledChanged: provider.onAudioBytesToggled,
                        ),
                        ToggleSectionWidget(
                          isSectionEnabled: provider.daySummaryToggled,
                          sectionTitle: 'Day Summary',
                          sectionDescription: 'Triggers when day summary is generated.',
                          icon: Icons.summarize_outlined,
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
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                          child: InkWell(
                            onTap: () {
                              launchUrl(Uri.parse('https://docs.omi.me/docs/developer/apps/Introduction'));
                              MixpanelManager().pageOpened('Advanced Mode Docs');
                            },
                            child: Row(
                              children: [
                                Container(
                                  padding: const EdgeInsets.all(8),
                                  decoration: BoxDecoration(
                                    color: const Color.fromARGB(255, 28, 28, 28),
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: const Icon(
                                    Icons.menu_book_outlined,
                                    color: Colors.white,
                                    size: 22,
                                  ),
                                ),
                                const SizedBox(width: 16),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      const Text(
                                        'Webhook Documentation',
                                        style: TextStyle(
                                          color: Colors.white,
                                          fontSize: 16,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        'Learn how to use webhooks with Omi',
                                        style: TextStyle(
                                          color: Colors.white.withOpacity(0.5),
                                          fontSize: 14,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                const Icon(
                                  Icons.chevron_right_rounded,
                                  color: Colors.white,
                                  size: 20,
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                  // Experimental Section
                  Padding(
                    padding: const EdgeInsets.fromLTRB(4, 32, 0, 12),
                    child: Text(
                      'EXPERIMENTAL',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.5),
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                  Text(
                    'Try the latest experimental features from Omi Team.',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 14,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Container(
                    decoration: BoxDecoration(
                      color: const Color.fromARGB(255, 18, 18, 18),
                      borderRadius: BorderRadius.circular(12.0),
                      border: Border.all(
                        color: Colors.white.withOpacity(0.15),
                        width: 1,
                      ),
                    ),
                    padding: EdgeInsets.zero,
                    child: ToggleSectionWidget(
                      isSectionEnabled: provider.localSyncEnabled,
                      sectionTitle: 'Local Sync',
                      sectionDescription: 'Try the latest experimental features from Omi Team.',
                      icon: Icons.sync_outlined,
                      options: const [],
                      onSectionEnabledChanged: provider.onLocalSyncEnabledChanged,
                    ),
                  ),

                  // Pilot Features Section
                  Padding(
                    padding: const EdgeInsets.fromLTRB(4, 24, 0, 12),
                    child: Text(
                      'PILOT FEATURES',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.5),
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                  Text(
                    'These features are tests and no support is guaranteed.',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 14,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Container(
                    decoration: BoxDecoration(
                      color: const Color.fromARGB(255, 18, 18, 18),
                      borderRadius: BorderRadius.circular(12.0),
                      border: Border.all(
                        color: Colors.white.withOpacity(0.15),
                        width: 1,
                      ),
                    ),
                    padding: EdgeInsets.zero,
                    child: ToggleSectionWidget(
                      isSectionEnabled: provider.followUpQuestionEnabled,
                      sectionTitle: 'Suggest follow up question',
                      sectionDescription: 'These features are tests and no support is guaranteed.',
                      icon: Icons.question_answer_outlined,
                      options: const [],
                      onSectionEnabledChanged: provider.onFollowUpQuestionChanged,
                    ),
                  ),
                  const SizedBox(height: 24),
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
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(vertical: 4),
      labelStyle: const TextStyle(
        fontSize: 14,
        color: Colors.grey,
        height: 0.5,
      ),
      enabledBorder: InputBorder.none,
      focusedBorder: const UnderlineInputBorder(
        borderSide: BorderSide(color: Colors.grey),
      ),
      suffixIcon: suffixIcon,
    );
  }
}

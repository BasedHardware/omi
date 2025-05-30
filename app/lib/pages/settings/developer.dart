import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
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
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Provider.of<DeveloperModeProvider>(context, listen: false)
          .initialize();
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
                    onPressed: provider.savingSettingsLoading
                        ? null
                        : provider.saveSettings,
                    child: const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 4.0),
                      child: Text(
                        'Save',
                        style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w500,
                            fontSize: 16),
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
                  // Export section moved up
                  const SizedBox(height: 24.0),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Export Conversations'),
                    subtitle: const Text(
                        'Export all your conversations to a JSON file.'),
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
                            setState(
                                () => provider.loadingExportMemories = true);
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text(
                                    'Conversations Export Started. This may take a few seconds, please wait.'),
                                duration: Duration(seconds: 3),
                              ),
                            );
                            List<ServerConversation> memories =
                                await getConversations(
                                    limit: 10000, offset: 0); // 10k for now
                            String json = const JsonEncoder.withIndent("     ")
                                .convert(memories);
                            final directory =
                                await getApplicationDocumentsDirectory();
                            final file =
                                File('${directory.path}/conversations.json');
                            await file.writeAsString(json);

                            final result = await Share.shareXFiles(
                                [XFile(file.path)],
                                text: 'Exported Conversations from Omi');
                            if (result.status == ShareResultStatus.success) {
                              debugPrint('Thank you for sharing the picture!');
                            }
                            MixpanelManager().exportMemories();
                            setState(
                                () => provider.loadingExportMemories = false);
                          },
                  ),
                  const SizedBox(height: 16),
                  Divider(color: Colors.grey.shade500),
                  const SizedBox(height: 16),

                  // Webhooks section
                  Row(
                    children: [
                      const Text(
                        'Webhooks',
                        style: TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.w500),
                      ),
                      Spacer(),
                      GestureDetector(
                        onTap: () {
                          launchUrl(Uri.parse(
                              'https://docs.omi.me/docs/developer/apps/Introduction'));
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
                    sectionDescription:
                        'Triggers when a new conversation is created.',
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
                    onSectionEnabledChanged:
                        provider.onConversationEventsToggled,
                  ),
                  ToggleSectionWidget(
                      isSectionEnabled: provider.transcriptsToggled,
                      sectionTitle: 'Real-time Transcript',
                      sectionDescription:
                          'Triggers when a new transcript is received.',
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
                      sectionDescription:
                          'Triggers when audio bytes are received.',
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
                          decoration:
                              _getTextFieldDecoration('Every x seconds'),
                          style: const TextStyle(color: Colors.white),
                        ),
                        const SizedBox(height: 16),
                      ],
                      onSectionEnabledChanged: provider.onAudioBytesToggled),
                  ToggleSectionWidget(
                    isSectionEnabled: provider.daySummaryToggled,
                    sectionTitle: 'Day Summary',
                    sectionDescription:
                        'Triggers when day summary is generated.',
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

                  // Experimental section
                  const Text(
                    'Experimental',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w500),
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
                      'Local Sync',
                      style: TextStyle(color: Colors.white, fontSize: 16),
                    ),
                    value: provider.localSyncEnabled,
                    onChanged: provider.onLocalSyncEnabledChanged,
                  ),
                  const SizedBox(height: 16),
                  Divider(color: Colors.grey.shade500),
                  const SizedBox(height: 16),

                  // Pilot Features section
                  const Text(
                    'Pilot Features',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w500),
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
                  const SizedBox(height: 16),
                  Divider(color: Colors.grey.shade500),
                  const SizedBox(height: 16),

                  // Backend API Settings - moved to bottom
                  const Text(
                    'Backend API Settings',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w500),
                  ),
                  const SizedBox(height: 8.0),

                  // STT Server Settings
                  const Text(
                    'Speech-to-Text Server Settings',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w500),
                  ),
                  const SizedBox(height: 8.0),
                  Text(
                    'Configure which STT service to use for transcription',
                    style: TextStyle(color: Colors.grey.shade300, fontSize: 12),
                  ),
                  const SizedBox(height: 12.0),

                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'STT Server Type',
                              style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w500),
                            ),
                            const SizedBox(height: 4.0),
                            Container(
                              height: 40,
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 12),
                              decoration: BoxDecoration(
                                color: Colors.grey.shade800,
                                borderRadius: BorderRadius.circular(8.0),
                                border: Border.all(color: Colors.grey.shade600),
                              ),
                              child: DropdownButtonHideUnderline(
                                child: DropdownButton<String>(
                                  value: provider.sttServerType,
                                  isExpanded: true,
                                  dropdownColor: Colors.grey.shade800,
                                  style: const TextStyle(
                                      color: Colors.white, fontSize: 14),
                                  icon: const Icon(Icons.arrow_drop_down,
                                      color: Colors.white),
                                  items: const [
                                    DropdownMenuItem(
                                      value: 'traditional',
                                      child: Text(
                                          'Traditional (Deepgram/Soniox/etc)'),
                                    ),
                                    DropdownMenuItem(
                                      value: 'wyoming',
                                      child: Text('Wyoming'),
                                    ),
                                  ],
                                  onChanged: (String? newValue) {
                                    if (newValue != null) {
                                      provider.onSttServerTypeChanged(newValue);
                                    }
                                  },
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),

                  if (provider.sttServerType == 'wyoming') ...[
                    const SizedBox(height: 12.0),
                    Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'Wyoming Server IP Address',
                                style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 14,
                                    fontWeight: FontWeight.w500),
                              ),
                              const SizedBox(height: 4.0),
                              SizedBox(
                                height: 40,
                                child: TextField(
                                  controller:
                                      provider.wyomingServerIpController,
                                  style: const TextStyle(
                                      color: Colors.white, fontSize: 14),
                                  decoration: InputDecoration(
                                    hintText: '192.168.1.2:10300',
                                    hintStyle: TextStyle(
                                        color: Colors.grey.shade400,
                                        fontSize: 12),
                                    contentPadding: const EdgeInsets.symmetric(
                                        horizontal: 12, vertical: 8),
                                    border: OutlineInputBorder(
                                      borderRadius: BorderRadius.circular(8.0),
                                      borderSide: BorderSide(
                                          color: Colors.grey.shade600),
                                    ),
                                    enabledBorder: OutlineInputBorder(
                                      borderRadius: BorderRadius.circular(8.0),
                                      borderSide: BorderSide(
                                          color: Colors.grey.shade600),
                                    ),
                                    focusedBorder: OutlineInputBorder(
                                      borderRadius: BorderRadius.circular(8.0),
                                      borderSide: const BorderSide(
                                          color: Colors.blueAccent, width: 1.0),
                                    ),
                                    filled: true,
                                    fillColor: Colors.grey.shade800,
                                  ),
                                  keyboardType: TextInputType.text,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 8),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const SizedBox(height: 18),
                            SizedBox(
                              height: 40,
                              child: ElevatedButton(
                                onPressed: provider.serverOperationLoading
                                    ? null
                                    : () async {
                                        if (provider
                                            .wyomingServerIpController.text
                                            .trim()
                                            .isEmpty) {
                                          ScaffoldMessenger.of(context)
                                              .showSnackBar(
                                            const SnackBar(
                                              content: Text(
                                                  'Please enter Wyoming server IP'),
                                              duration: Duration(seconds: 2),
                                              backgroundColor: Colors.red,
                                            ),
                                          );
                                          return;
                                        }

                                        final success = await provider
                                            .testWyomingConnection(
                                          provider
                                              .wyomingServerIpController.text,
                                        );

                                        if (success) {
                                          ScaffoldMessenger.of(context)
                                              .showSnackBar(
                                            const SnackBar(
                                              content: Text(
                                                  'Wyoming connection successful!'),
                                              duration: Duration(seconds: 2),
                                              backgroundColor: Colors.green,
                                            ),
                                          );
                                        } else {
                                          ScaffoldMessenger.of(context)
                                              .showSnackBar(
                                            const SnackBar(
                                              content: Text(
                                                  'Failed to connect to Wyoming server'),
                                              duration: Duration(seconds: 2),
                                              backgroundColor: Colors.red,
                                            ),
                                          );
                                        }
                                      },
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.blue,
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 12),
                                  minimumSize: const Size(60, 40),
                                ),
                                child: provider.serverOperationLoading
                                    ? const SizedBox(
                                        width: 12,
                                        height: 12,
                                        child: CircularProgressIndicator(
                                          color: Colors.white,
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : const Text(
                                        'Test',
                                        style: TextStyle(
                                            color: Colors.white, fontSize: 12),
                                      ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ],

                  const SizedBox(height: 16.0),
                  Divider(color: Colors.grey.shade500),
                  const SizedBox(height: 16.0),

                  // Current active URL display
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Current Active Server',
                              style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w500),
                            ),
                            const SizedBox(height: 4.0),
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 10, vertical: 8),
                              decoration: BoxDecoration(
                                color: Colors.grey.shade800,
                                borderRadius: BorderRadius.circular(8.0),
                                border: Border.all(color: Colors.grey.shade700),
                              ),
                              child: Text(
                                provider.getCurrentActiveUrl(),
                                style: TextStyle(
                                    color: provider.currentCustomApiUrl.isEmpty
                                        ? Colors.blue
                                        : Colors.green,
                                    fontSize: 13,
                                    fontWeight: FontWeight.bold),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const SizedBox(
                              height: 18), // Align with the server display
                          SizedBox(
                            height: 36,
                            child: ElevatedButton(
                              onPressed: provider.serverOperationLoading
                                  ? null
                                  : () async {
                                      await provider.resetToOriginalUrl();
                                      // Show a quick success message
                                      ScaffoldMessenger.of(context)
                                          .showSnackBar(
                                        const SnackBar(
                                          content:
                                              Text('Reset to default server'),
                                          duration: Duration(seconds: 2),
                                          backgroundColor: Colors.blue,
                                        ),
                                      );
                                      // Force rebuild to update UI
                                      setState(() {});
                                    },
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.blue,
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 12),
                              ),
                              child: provider.serverOperationLoading
                                  ? const SizedBox(
                                      width: 12,
                                      height: 12,
                                      child: CircularProgressIndicator(
                                        color: Colors.white,
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Text(
                                      'Reset',
                                      style: TextStyle(
                                          color: Colors.white, fontSize: 12),
                                    ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 12.0),

                  // Custom URL Field
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Custom Backend URL',
                              style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w500),
                            ),
                            const SizedBox(height: 4.0),
                            SizedBox(
                              height: 36,
                              child: TextField(
                                controller: provider.customApiUrlController,
                                style: const TextStyle(
                                    color: Colors.white, fontSize: 13),
                                decoration: InputDecoration(
                                  hintText: 'https://your-backend.com/',
                                  hintStyle: TextStyle(
                                      color: Colors.grey.shade400,
                                      fontSize: 12),
                                  contentPadding: const EdgeInsets.symmetric(
                                      horizontal: 10, vertical: 8),
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(8.0),
                                    borderSide:
                                        const BorderSide(color: Colors.white),
                                  ),
                                  enabledBorder: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(8.0),
                                    borderSide:
                                        const BorderSide(color: Colors.white),
                                  ),
                                  focusedBorder: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(8.0),
                                    borderSide: const BorderSide(
                                        color: Colors.blueAccent, width: 1.0),
                                  ),
                                ),
                                keyboardType: TextInputType.url,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const SizedBox(height: 18), // Align with URL field
                          SizedBox(
                            height: 36,
                            child: ElevatedButton(
                              onPressed: provider.serverOperationLoading
                                  ? null
                                  : () async {
                                      if (provider.customApiUrlController.text
                                          .trim()
                                          .isEmpty) {
                                        ScaffoldMessenger.of(context)
                                            .showSnackBar(
                                          const SnackBar(
                                            content: Text('Please enter a URL'),
                                            duration: Duration(seconds: 2),
                                            backgroundColor: Colors.red,
                                          ),
                                        );
                                        return;
                                      }

                                      final success =
                                          await provider.addNewCustomApiUrl(
                                        provider.customApiUrlController.text,
                                      );

                                      if (success) {
                                        // Show success message
                                        ScaffoldMessenger.of(context)
                                            .showSnackBar(
                                          const SnackBar(
                                            content: Text('New server added'),
                                            duration: Duration(seconds: 2),
                                            backgroundColor: Colors.green,
                                          ),
                                        );
                                        await provider.selectCustomApiUrl(
                                            provider
                                                .customApiUrlController.text);
                                        setState(() {});
                                      } else {
                                        // Show error message
                                        ScaffoldMessenger.of(context)
                                            .showSnackBar(
                                          const SnackBar(
                                            content: Text(
                                                'Invalid URL or already exists'),
                                            duration: Duration(seconds: 2),
                                            backgroundColor: Colors.red,
                                          ),
                                        );
                                      }
                                    },
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.green,
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 12),
                                minimumSize: const Size(70, 36),
                              ),
                              child: provider.serverOperationLoading
                                  ? const SizedBox(
                                      width: 12,
                                      height: 12,
                                      child: CircularProgressIndicator(
                                        color: Colors.white,
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Text(
                                      'Add',
                                      style: TextStyle(
                                          color: Colors.white, fontSize: 12),
                                    ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),

                  // Saved URLs list
                  const SizedBox(height: 12.0),
                  if (provider.customApiUrls.isNotEmpty) ...[
                    const Text(
                      'Saved Servers',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(height: 4.0),
                    Container(
                      constraints: const BoxConstraints(maxHeight: 150),
                      decoration: BoxDecoration(
                        border: Border.all(color: Colors.grey),
                        borderRadius: BorderRadius.circular(8.0),
                      ),
                      child: provider.serverOperationLoading
                          ? const Center(
                              child: Padding(
                                padding: EdgeInsets.all(16.0),
                                child: CircularProgressIndicator(
                                    color: Colors.white),
                              ),
                            )
                          : ListView.separated(
                              shrinkWrap: true,
                              itemCount: provider.customApiUrls.length,
                              separatorBuilder: (context, index) =>
                                  const Divider(height: 1, color: Colors.grey),
                              itemBuilder: (context, index) {
                                final url = provider.customApiUrls[index];
                                return Dismissible(
                                  key: Key(url),
                                  direction: DismissDirection.endToStart,
                                  background: Container(
                                    color: Colors.red,
                                    alignment: Alignment.centerRight,
                                    padding: const EdgeInsets.only(right: 16),
                                    child: const Icon(
                                      Icons.delete,
                                      color: Colors.white,
                                    ),
                                  ),
                                  onDismissed: (direction) async {
                                    await provider.removeCustomApiUrl(url);
                                    // Show a quick success message
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      const SnackBar(
                                        content: Text('Server removed'),
                                        duration: Duration(seconds: 2),
                                        backgroundColor: Colors.red,
                                      ),
                                    );
                                    setState(() {});
                                  },
                                  child: ListTile(
                                    dense: true,
                                    contentPadding: const EdgeInsets.symmetric(
                                        horizontal: 12, vertical: 2),
                                    title: Text(
                                      url,
                                      style: const TextStyle(
                                          color: Colors.white, fontSize: 12),
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                    tileColor:
                                        provider.currentCustomApiUrl == url
                                            ? Colors.green.withOpacity(0.2)
                                            : null,
                                    trailing: Container(
                                      margin: const EdgeInsets.only(right: 12),
                                      child: IconButton(
                                        iconSize: 16,
                                        constraints: const BoxConstraints(
                                            maxWidth: 28, maxHeight: 28),
                                        padding: EdgeInsets.zero,
                                        icon: const Icon(
                                            Icons.check_circle_outline,
                                            color: Colors.green),
                                        onPressed: () async {
                                          await provider
                                              .selectCustomApiUrl(url);
                                          // Force rebuild to update UI
                                          setState(() {});
                                          // Show a quick success message
                                          ScaffoldMessenger.of(context)
                                              .showSnackBar(
                                            SnackBar(
                                              content: Text(
                                                  'Server changed to $url'),
                                              duration:
                                                  const Duration(seconds: 2),
                                              backgroundColor: Colors.green,
                                            ),
                                          );
                                        },
                                        tooltip: 'Select this server',
                                      ),
                                    ),
                                    onTap: () async {
                                      await provider.selectCustomApiUrl(url);
                                      // Force rebuild to update UI
                                      setState(() {});
                                      // Show a quick success message
                                      ScaffoldMessenger.of(context)
                                          .showSnackBar(
                                        SnackBar(
                                          content:
                                              Text('Server changed to $url'),
                                          duration: const Duration(seconds: 2),
                                          backgroundColor: Colors.green,
                                        ),
                                      );
                                    },
                                  ),
                                );
                              },
                            ),
                    ),
                  ],
                  const SizedBox(height: 24.0),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  _getTextFieldDecoration(String label,
      {IconButton? suffixIcon,
      bool canBeDisabled = false,
      String hintText = ''}) {
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
}

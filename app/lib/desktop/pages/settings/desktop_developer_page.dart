import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/settings/widgets/create_mcp_api_key_dialog.dart';
import 'package:omi/pages/settings/widgets/mcp_api_key_list_item.dart';
import 'package:omi/pages/settings/widgets/toggle_section_widget.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopDeveloperSettingsPage extends StatefulWidget {
  const DesktopDeveloperSettingsPage({super.key});

  @override
  State<DesktopDeveloperSettingsPage> createState() => _DesktopDeveloperSettingsPageState();
}

class _DesktopDeveloperSettingsPageState extends State<DesktopDeveloperSettingsPage> {
  bool _isReloading = false;
  late ScrollController _scrollController;

  @override
  void initState() {
    super.initState();
    _scrollController = ScrollController();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Provider.of<DeveloperModeProvider>(context, listen: false).initialize();
      if (mounted) {
        context.read<McpProvider>().fetchKeys();
      }
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _handleReload() async {
    if (_isReloading) return;

    setState(() {
      _isReloading = true;
    });

    // Scroll to top
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        0,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    }

    await Provider.of<DeveloperModeProvider>(context, listen: false).initialize();
    if (mounted) {
      await context.read<McpProvider>().fetchKeys();
    }

    if (mounted) {
      setState(() {
        _isReloading = false;
      });
    }
  }

  Widget _buildHeader(ResponsiveHelper responsive) {
    return Row(
      children: [
        OmiIconButton(
          icon: FontAwesomeIcons.arrowLeft,
          style: OmiIconButtonStyle.outline,
          size: 40,
          iconSize: 16,
          borderRadius: 12,
          onPressed: () => Navigator.of(context).pop(),
        ),
        const SizedBox(width: 16),
        Text(
          'Developer Settings',
          style: responsive.headlineLarge.copyWith(
            fontWeight: FontWeight.w400,
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return CallbackShortcuts(
        bindings: {
          const SingleActivator(LogicalKeyboardKey.keyR, meta: true): _handleReload,
        },
        child: Focus(
            autofocus: true,
            child: GestureDetector(
              onTap: () => FocusScope.of(context).unfocus(),
              child: Consumer<DeveloperModeProvider>(
                builder: (context, provider, child) {
                  return Scaffold(
                    backgroundColor: ResponsiveHelper.backgroundPrimary,
                    body: Stack(
                      children: [
                        Padding(
                          padding: EdgeInsets.symmetric(horizontal: responsive.spacing(baseSpacing: 24)),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              SizedBox(height: responsive.spacing(baseSpacing: 24)),
                              _buildHeader(responsive),
                              SizedBox(height: responsive.spacing(baseSpacing: 24)),
                              Expanded(
                                child: ListView(
                                  shrinkWrap: true,
                                  children: [
                                    Container(
                                      padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
                                      decoration: BoxDecoration(
                                        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                                        borderRadius: BorderRadius.circular(16),
                                        border: Border.all(
                                          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                                          width: 1,
                                        ),
                                      ),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Row(
                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                            children: [
                                              Column(
                                                crossAxisAlignment: CrossAxisAlignment.start,
                                                children: [
                                                  Text(
                                                    'Debug logs',
                                                    style: responsive.titleMedium.copyWith(
                                                      color: ResponsiveHelper.textPrimary,
                                                      fontWeight: FontWeight.w600,
                                                    ),
                                                  ),
                                                  SizedBox(height: responsive.spacing(baseSpacing: 4)),
                                                  Text(
                                                    'Helps diagnose issues. Auto-deletes after 3 days.',
                                                    style: responsive.bodyMedium.copyWith(
                                                      color: ResponsiveHelper.textSecondary,
                                                    ),
                                                  ),
                                                ],
                                              ),
                                              Switch(
                                                value: SharedPreferencesUtil().devLogsToFileEnabled,
                                                onChanged: (v) async {
                                                  await DebugLogManager.setEnabled(v);
                                                  setState(() {});
                                                },
                                                //activeThumbColor: ResponsiveHelper.purplePrimary,
                                              ),
                                            ],
                                          ),
                                          SizedBox(height: responsive.spacing(baseSpacing: 16)),
                                          Row(
                                            children: [
                                              Expanded(
                                                child: ElevatedButton.icon(
                                                  style: ElevatedButton.styleFrom(
                                                    backgroundColor:
                                                        ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                                                    foregroundColor: ResponsiveHelper.textPrimary,
                                                    padding: const EdgeInsets.symmetric(
                                                      horizontal: 16,
                                                      vertical: 12,
                                                    ),
                                                    minimumSize: const Size(double.infinity, 48),
                                                    shape: RoundedRectangleBorder(
                                                      borderRadius: BorderRadius.circular(12),
                                                      side: BorderSide(
                                                        color:
                                                            ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                                                        width: 1,
                                                      ),
                                                    ),
                                                  ),
                                                  icon: const Icon(
                                                    Icons.upload_file,
                                                    size: 16,
                                                    color: ResponsiveHelper.textPrimary,
                                                  ),
                                                  label: Text(
                                                    'Share Logs',
                                                    style: responsive.bodyMedium.copyWith(
                                                      color: ResponsiveHelper.textPrimary,
                                                      fontWeight: FontWeight.w500,
                                                    ),
                                                  ),
                                                  onPressed: () async {
                                                    final files = await DebugLogManager.listLogFiles();
                                                    if (files.isEmpty) {
                                                      AppSnackbar.showSnackbarError('No log files found.');
                                                      return;
                                                    }
                                                    if (files.length == 1) {
                                                      final result = await Share.shareXFiles([XFile(files.first.path)],
                                                          text: 'Omi debug log');
                                                      if (result.status == ShareResultStatus.success) {
                                                        Logger.debug('Log shared');
                                                      }
                                                      return;
                                                    }

                                                    if (!context.mounted) return;
                                                    final backgroundColor = Theme.of(context).colorScheme.primary;
                                                    final selected = await showModalBottomSheet<File>(
                                                      context: context,
                                                      backgroundColor: backgroundColor,
                                                      shape: const RoundedRectangleBorder(
                                                        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                                                      ),
                                                      builder: (ctx) {
                                                        return SafeArea(
                                                          child: ListView.separated(
                                                            shrinkWrap: true,
                                                            itemCount: files.length,
                                                            separatorBuilder: (ctx, index) => const Divider(height: 1),
                                                            itemBuilder: (ctx, index) {
                                                              final file = files[index];
                                                              return ListTile(
                                                                title: Text(
                                                                  file.path.split('/').last,
                                                                  style: TextStyle(
                                                                      color: Theme.of(ctx).colorScheme.onPrimary),
                                                                ),
                                                                subtitle: Text(
                                                                  '${(file.lengthSync() / 1024).toStringAsFixed(1)} KB',
                                                                  style: TextStyle(
                                                                    color: Theme.of(context)
                                                                        .colorScheme
                                                                        .onPrimary
                                                                        .withValues(alpha: 0.7),
                                                                  ),
                                                                ),
                                                                onTap: () => Navigator.pop(ctx, file),
                                                              );
                                                            },
                                                          ),
                                                        );
                                                      },
                                                    );
                                                    if (selected != null) {
                                                      final result = await Share.shareXFiles([XFile(selected.path)],
                                                          text: 'Omi debug log');
                                                      if (result.status == ShareResultStatus.success) {
                                                        Logger.debug('Log shared');
                                                      }
                                                    }
                                                  },
                                                ),
                                              ),
                                              SizedBox(width: responsive.spacing(baseSpacing: 12)),
                                              Container(
                                                decoration: BoxDecoration(
                                                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                                                  borderRadius: BorderRadius.circular(12),
                                                ),
                                                child: IconButton(
                                                  tooltip: 'Clear logs',
                                                  onPressed: () async {
                                                    await DebugLogManager.clear();
                                                    AppSnackbar.showSnackbar('Debug logs cleared');
                                                  },
                                                  icon: const Icon(
                                                    Icons.delete_outline,
                                                    color: ResponsiveHelper.textSecondary,
                                                    size: 20,
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ),
                                        ],
                                      ),
                                    ),

                                    SizedBox(height: responsive.spacing(baseSpacing: 32)),
                                    Container(
                                      padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
                                      decoration: BoxDecoration(
                                        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                                        borderRadius: BorderRadius.circular(16),
                                        border: Border.all(
                                          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                                          width: 1,
                                        ),
                                      ),
                                      child: ListTile(
                                        contentPadding: EdgeInsets.zero,
                                        title: Text(
                                          'Export Conversations',
                                          style: responsive.titleMedium.copyWith(
                                            color: ResponsiveHelper.textPrimary,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                        subtitle: Text(
                                          'Export all your conversations to a JSON file.',
                                          style: responsive.bodyMedium.copyWith(
                                            color: ResponsiveHelper.textSecondary,
                                          ),
                                        ),
                                        trailing: provider.loadingExportMemories
                                            ? const SizedBox(
                                                height: 16,
                                                width: 16,
                                                child: CircularProgressIndicator(
                                                  color: ResponsiveHelper.purplePrimary,
                                                  strokeWidth: 2,
                                                ),
                                              )
                                            : const Icon(
                                                Icons.upload,
                                                color: ResponsiveHelper.textSecondary,
                                              ),
                                        onTap: provider.loadingExportMemories
                                            ? null
                                            : () async {
                                                if (provider.loadingExportMemories) return;
                                                setState(() => provider.loadingExportMemories = true);
                                                ScaffoldMessenger.of(context).showSnackBar(
                                                  SnackBar(
                                                    content: Text(
                                                      'Conversations Export Started. This may take a few seconds, please wait.',
                                                      style: responsive.bodyMedium.copyWith(
                                                        color: ResponsiveHelper.textPrimary,
                                                      ),
                                                    ),
                                                    backgroundColor: ResponsiveHelper.backgroundSecondary,
                                                    duration: const Duration(seconds: 3),
                                                  ),
                                                );
                                                List<ServerConversation> memories =
                                                    await getConversations(limit: 10000, offset: 0); // 10k for now
                                                String json = const JsonEncoder.withIndent("     ").convert(memories);
                                                final directory = await getApplicationDocumentsDirectory();
                                                final file = File('${directory.path}/conversations.json');
                                                await file.writeAsString(json);

                                                final result = await Share.shareXFiles([XFile(file.path)],
                                                    text: 'Exported Conversations from Omi');
                                                if (result.status == ShareResultStatus.success) {
                                                  Logger.debug('Thank you for sharing the picture!');
                                                }
                                                MixpanelManager().exportMemories();
                                                setState(() => provider.loadingExportMemories = false);
                                              },
                                      ),
                                    ),
                                    SizedBox(height: responsive.spacing(baseSpacing: 16)),
                                    Container(
                                      padding: EdgeInsets.all(responsive.spacing(baseSpacing: 20)),
                                      decoration: BoxDecoration(
                                        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                                        borderRadius: BorderRadius.circular(16),
                                        border: Border.all(
                                          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                                          width: 1,
                                        ),
                                      ),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Row(
                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                            children: [
                                              Text(
                                                'MCP',
                                                style: responsive.titleLarge.copyWith(
                                                  color: ResponsiveHelper.textPrimary,
                                                  fontWeight: FontWeight.w600,
                                                ),
                                              ),
                                              GestureDetector(
                                                onTap: () {
                                                  launchUrl(Uri.parse('https://docs.omi.me/doc/developer/MCP'));
                                                  MixpanelManager().pageOpened('MCP Docs');
                                                },
                                                child: Padding(
                                                  padding: EdgeInsets.all(responsive.spacing(baseSpacing: 8)),
                                                  child: Text(
                                                    'Docs',
                                                    style: responsive.bodyMedium.copyWith(
                                                      color: ResponsiveHelper.purplePrimary,
                                                      decoration: TextDecoration.underline,
                                                      decorationColor: ResponsiveHelper.purplePrimary,
                                                    ),
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ),
                                          SizedBox(height: responsive.spacing(baseSpacing: 10)),
                                          Text(
                                            'To connect Omi with other applications to read, search, and manage your memories and conversations. Create a key to get started.',
                                            style: responsive.bodyMedium.copyWith(
                                              color: ResponsiveHelper.textSecondary,
                                            ),
                                          ),
                                          SizedBox(height: responsive.spacing(baseSpacing: 16)),
                                          Row(
                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                            children: [
                                              Text(
                                                'API Keys',
                                                style: responsive.titleMedium.copyWith(
                                                  color: ResponsiveHelper.textPrimary,
                                                  fontWeight: FontWeight.w500,
                                                ),
                                              ),
                                              TextButton.icon(
                                                onPressed: () => showDialog(
                                                  context: context,
                                                  builder: (context) => const CreateMcpApiKeyDialog(),
                                                ),
                                                icon: const Icon(
                                                  Icons.add,
                                                  color: ResponsiveHelper.textPrimary,
                                                  size: 18,
                                                ),
                                                label: Text(
                                                  'Create Key',
                                                  style: responsive.bodyMedium.copyWith(
                                                    color: ResponsiveHelper.textPrimary,
                                                  ),
                                                ),
                                                style: TextButton.styleFrom(
                                                  padding: EdgeInsets.symmetric(
                                                    horizontal: responsive.spacing(baseSpacing: 12),
                                                    vertical: responsive.spacing(baseSpacing: 8),
                                                  ),
                                                ),
                                              )
                                            ],
                                          ),
                                          SizedBox(height: responsive.spacing(baseSpacing: 10)),
                                          Consumer<McpProvider>(
                                            builder: (context, provider, child) {
                                              if (provider.isLoading && provider.keys.isEmpty) {
                                                return const Center(
                                                  child: CircularProgressIndicator(
                                                    strokeWidth: 2,
                                                    color: ResponsiveHelper.purplePrimary,
                                                  ),
                                                );
                                              }
                                              if (provider.error != null) {
                                                return Center(
                                                  child: Text(
                                                    'Error: ${provider.error}',
                                                    style: responsive.bodyMedium.copyWith(
                                                      color: ResponsiveHelper.textPrimary,
                                                    ),
                                                  ),
                                                );
                                              }
                                              if (provider.keys.isEmpty) {
                                                return Center(
                                                  child: Padding(
                                                    padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
                                                    child: Text(
                                                      'No API keys found. Create one to get started.',
                                                      style: responsive.bodyMedium.copyWith(
                                                        color: ResponsiveHelper.textSecondary,
                                                      ),
                                                    ),
                                                  ),
                                                );
                                              }
                                              return Column(
                                                children:
                                                    provider.keys.map((key) => McpApiKeyListItem(apiKey: key)).toList(),
                                              );
                                            },
                                          ),
                                        ],
                                      ),
                                    ),
                                    SizedBox(height: responsive.spacing(baseSpacing: 32)),
                                    Container(
                                      padding: EdgeInsets.all(responsive.spacing(baseSpacing: 20)),
                                      decoration: BoxDecoration(
                                        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                                        borderRadius: BorderRadius.circular(16),
                                        border: Border.all(
                                          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                                          width: 1,
                                        ),
                                      ),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            'Advanced Settings',
                                            style: responsive.titleLarge.copyWith(
                                              color: ResponsiveHelper.textPrimary,
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                          SizedBox(height: responsive.spacing(baseSpacing: 16)),
                                          Row(
                                            children: [
                                              Text(
                                                'Webhooks',
                                                style: responsive.titleMedium.copyWith(
                                                  color: ResponsiveHelper.textPrimary,
                                                  fontWeight: FontWeight.w500,
                                                ),
                                              ),
                                              const Spacer(),
                                              GestureDetector(
                                                onTap: () {
                                                  launchUrl(
                                                      Uri.parse('https://docs.omi.me/doc/developer/apps/Introduction'));
                                                  MixpanelManager().pageOpened('Advanced Mode Docs');
                                                },
                                                child: Padding(
                                                  padding: EdgeInsets.all(responsive.spacing(baseSpacing: 8)),
                                                  child: Text(
                                                    'Docs',
                                                    style: responsive.bodyMedium.copyWith(
                                                      color: ResponsiveHelper.purplePrimary,
                                                      decoration: TextDecoration.underline,
                                                      decorationColor: ResponsiveHelper.purplePrimary,
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
                                        ],
                                      ),
                                    ),
                                    SizedBox(height: responsive.spacing(baseSpacing: 32)),
                                    Container(
                                      padding: EdgeInsets.all(responsive.spacing(baseSpacing: 20)),
                                      decoration: BoxDecoration(
                                        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                                        borderRadius: BorderRadius.circular(16),
                                        border: Border.all(
                                          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                                          width: 1,
                                        ),
                                      ),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            'Experimental',
                                            style: responsive.titleLarge.copyWith(
                                              color: ResponsiveHelper.textPrimary,
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                          SizedBox(height: responsive.spacing(baseSpacing: 8)),
                                          Text(
                                            'Try the latest experimental features from Omi Team.',
                                            style: responsive.bodyMedium.copyWith(
                                              color: ResponsiveHelper.textSecondary,
                                            ),
                                          ),
                                          SizedBox(height: responsive.spacing(baseSpacing: 16)),
                                          CheckboxListTile(
                                            contentPadding: EdgeInsets.zero,
                                            title: Text(
                                              'Transcription service diagnostic status',
                                              style: responsive.bodyLarge.copyWith(
                                                color: ResponsiveHelper.textPrimary,
                                              ),
                                            ),
                                            subtitle: Text(
                                              'Enable detailed diagnostic messages from the transcription service',
                                              style: responsive.bodySmall.copyWith(
                                                color: ResponsiveHelper.textSecondary,
                                              ),
                                            ),
                                            value: provider.transcriptionDiagnosticEnabled,
                                            onChanged: provider.onTranscriptionDiagnosticChanged,
                                            activeColor: ResponsiveHelper.purplePrimary,
                                          ),
                                          SizedBox(height: responsive.spacing(baseSpacing: 16)),
                                          CheckboxListTile(
                                            contentPadding: EdgeInsets.zero,
                                            title: Text(
                                              'Auto-create and tag new speakers',
                                              style: responsive.bodyLarge.copyWith(
                                                color: ResponsiveHelper.textPrimary,
                                              ),
                                            ),
                                            subtitle: Text(
                                              'Automatically create a new person when a name is detected in the transcript.',
                                              style: responsive.bodySmall.copyWith(
                                                color: ResponsiveHelper.textSecondary,
                                              ),
                                            ),
                                            value: provider.autoCreateSpeakersEnabled,
                                            onChanged: provider.onAutoCreateSpeakersChanged,
                                            activeColor: ResponsiveHelper.purplePrimary,
                                          ),
                                        ],
                                      ),
                                    ),
                                    SizedBox(height: responsive.spacing(baseSpacing: 36)),
                                    Container(
                                      padding: EdgeInsets.all(responsive.spacing(baseSpacing: 20)),
                                      decoration: BoxDecoration(
                                        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
                                        borderRadius: BorderRadius.circular(16),
                                        border: Border.all(
                                          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                                          width: 1,
                                        ),
                                      ),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            'Pilot Features',
                                            style: responsive.titleLarge.copyWith(
                                              color: ResponsiveHelper.textPrimary,
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                          SizedBox(height: responsive.spacing(baseSpacing: 8)),
                                          Text(
                                            'These features are tests and no support is guaranteed.',
                                            style: responsive.bodyMedium.copyWith(
                                              color: ResponsiveHelper.textSecondary,
                                            ),
                                          ),
                                          SizedBox(height: responsive.spacing(baseSpacing: 16)),
                                          CheckboxListTile(
                                            contentPadding: EdgeInsets.zero,
                                            title: Text(
                                              'Suggest follow up question',
                                              style: responsive.bodyLarge.copyWith(
                                                color: ResponsiveHelper.textPrimary,
                                              ),
                                            ),
                                            value: provider.followUpQuestionEnabled,
                                            onChanged: provider.onFollowUpQuestionChanged,
                                            activeColor: ResponsiveHelper.purplePrimary,
                                          ),
                                        ],
                                      ),
                                    ),
                                    SizedBox(height: responsive.spacing(baseSpacing: 24)),

                                    // Save Button
                                    SizedBox(
                                      width: double.infinity,
                                      child: ElevatedButton(
                                        onPressed: provider.savingSettingsLoading ? null : provider.saveSettings,
                                        style: ElevatedButton.styleFrom(
                                          backgroundColor: ResponsiveHelper.purplePrimary,
                                          foregroundColor: ResponsiveHelper.textPrimary,
                                          padding: EdgeInsets.symmetric(
                                            horizontal: responsive.spacing(baseSpacing: 20),
                                            vertical: responsive.spacing(baseSpacing: 16),
                                          ),
                                          shape: RoundedRectangleBorder(
                                            borderRadius: BorderRadius.circular(12),
                                          ),
                                          minimumSize: const Size(double.infinity, 50),
                                        ),
                                        child: Text(
                                          'Save Settings',
                                          style: responsive.bodyLarge.copyWith(
                                            color: ResponsiveHelper.textPrimary,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                      ),
                                    ),
                                    SizedBox(height: responsive.spacing(baseSpacing: 32)),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (provider.savingSettingsLoading)
                          Container(
                            color: Colors.black54,
                            child: Center(
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const CircularProgressIndicator(color: ResponsiveHelper.purplePrimary),
                                  SizedBox(height: responsive.spacing(baseSpacing: 16)),
                                  Text(
                                    'Syncing Developer Settings...',
                                    style: responsive.bodyLarge.copyWith(
                                      color: ResponsiveHelper.textPrimary,
                                    ),
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
            )));
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

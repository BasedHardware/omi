import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/settings/widgets/create_mcp_api_key_dialog.dart';
import 'package:omi/pages/settings/widgets/mcp_api_key_list_item.dart';
import 'package:omi/pages/settings/widgets/developer_api_keys_section.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/pages/settings/conversation_timeout_dialog.dart';
import 'package:omi/pages/settings/import_history_page.dart';

class DeveloperSettingsPage extends StatefulWidget {
  const DeveloperSettingsPage({super.key});

  @override
  State<DeveloperSettingsPage> createState() => _DeveloperSettingsPageState();
}

class _DeveloperSettingsPageState extends State<DeveloperSettingsPage> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      context.read<McpProvider>().fetchKeys();
    });
    super.initState();
  }

  Widget _buildSectionContainer({required List<Widget> children}) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: children,
      ),
    );
  }

  Widget _buildSectionHeader(String title, {String? subtitle, Widget? trailing}) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, right: 4, bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (trailing != null) trailing,
            ],
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 6),
            Text(
              subtitle,
              style: TextStyle(
                color: Colors.grey.shade400,
                fontSize: 14,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildSttChip() {
    final useCustom = SharedPreferencesUtil().useCustomStt;
    final config = SharedPreferencesUtil().customSttConfig;
    final label = useCustom ? SttProviderConfig.get(config.provider).displayName : 'Omi';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Colors.grey,
          fontSize: 11,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildExperimentalItem({
    required String title,
    required String description,
    required IconData icon,
    required bool value,
    required ValueChanged<bool>? onChanged,
  }) {
    return Row(
      children: [
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: const Color(0xFF2A2A2E),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Center(
            child: FaIcon(icon, color: Colors.grey.shade400, size: 16),
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                description,
                style: TextStyle(
                  color: Colors.grey.shade500,
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ),
        Switch(
          value: value,
          onChanged: onChanged,
          activeColor: const Color(0xFF22C55E),
        ),
      ],
    );
  }

  Widget _buildWebhookItem({
    required String title,
    required String description,
    required IconData icon,
    required bool isEnabled,
    required ValueChanged<bool> onToggle,
    required TextEditingController controller,
    Widget? extraField,
  }) {
    return Column(
      children: [
        Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Center(
                child: FaIcon(icon, color: Colors.grey.shade400, size: 16),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    description,
                    style: TextStyle(
                      color: Colors.grey.shade500,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
            Switch(
              value: isEnabled,
              onChanged: onToggle,
              activeColor: const Color(0xFF22C55E),
            ),
          ],
        ),
        if (isEnabled) ...[
          const SizedBox(height: 12),
          _buildTextField(controller: controller, label: 'Endpoint URL'),
          if (extraField != null) ...[
            const SizedBox(height: 8),
            extraField,
          ],
        ],
      ],
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    String? hint,
    TextInputType? keyboardType,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF2C2C2E),
        borderRadius: BorderRadius.circular(10),
      ),
      child: TextField(
        controller: controller,
        keyboardType: keyboardType,
        style: const TextStyle(color: Colors.white, fontSize: 15),
        decoration: InputDecoration(
          labelText: label,
          hintText: hint,
          labelStyle: TextStyle(color: Colors.grey.shade400, fontSize: 14),
          hintStyle: TextStyle(color: Colors.grey.shade600, fontSize: 14),
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          border: InputBorder.none,
          enabledBorder: InputBorder.none,
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Colors.white24, width: 1),
          ),
        ),
      ),
    );
  }

  Widget _buildMcpConfigRow(String label, String value) {
    return GestureDetector(
      onTap: () {
        Clipboard.setData(ClipboardData(text: value));
        AppSnackbar.showSnackbar('$label copied');
      },
      child: Row(
        children: [
          Expanded(
            flex: 2,
            child: Text(
              label,
              style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
            ),
          ),
          Expanded(
            flex: 3,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              decoration: BoxDecoration(
                color: const Color(0xFF0D0D0D),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      value,
                      style: const TextStyle(
                        color: Colors.white,
                        fontFamily: 'Ubuntu Mono',
                        fontSize: 13,
                      ),
                    ),
                  ),
                  FaIcon(FontAwesomeIcons.copy, color: Colors.grey.shade600, size: 11),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildApiKeysList(BuildContext context) {
    return Consumer<McpProvider>(
      builder: (context, provider, child) {
        if (provider.isLoading && provider.keys.isEmpty) {
          return Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: const Color(0xFF1C1C1E),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Center(
              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
            ),
          );
        }
        if (provider.error != null) {
          return Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: const Color(0xFF1C1C1E),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Center(
              child: Text(
                'Error: ${provider.error}',
                style: TextStyle(color: Colors.red.shade300),
              ),
            ),
          );
        }
        if (provider.keys.isEmpty) {
          return Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: const Color(0xFF1C1C1E),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              children: [
                FaIcon(FontAwesomeIcons.key, color: Colors.grey.shade600, size: 28),
                const SizedBox(height: 12),
                Text(
                  'No API keys yet',
                  style: TextStyle(color: Colors.grey.shade400, fontSize: 15),
                ),
                const SizedBox(height: 4),
                Text(
                  'Create a key to get started',
                  style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                ),
              ],
            ),
          );
        }
        return _buildSectionContainer(
          children: provider.keys.asMap().entries.map((entry) {
            final index = entry.key;
            final key = entry.value;
            return Column(
              children: [
                McpApiKeyListItem(apiKey: key),
                if (index < provider.keys.length - 1) const Divider(height: 1, color: Color(0xFF3C3C43)),
              ],
            );
          }).toList(),
        );
      },
    );
  }

  Widget _buildDocsButton(String url, String label) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        onTap: () {
          launchUrl(Uri.parse(url));
          MixpanelManager().pageOpened('$label Docs');
        },
        borderRadius: BorderRadius.circular(20),
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text(
            'Docs',
            style: TextStyle(
              color: Colors.black,
              fontWeight: FontWeight.w600,
              fontSize: 12,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCreateKeyButton(VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.1),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const FaIcon(FontAwesomeIcons.plus, color: Colors.white, size: 10),
            const SizedBox(width: 6),
            const Text(
              'Create Key',
              style: TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Consumer<DeveloperModeProvider>(
        builder: (context, provider, child) {
          return Scaffold(
            backgroundColor: const Color(0xFF0D0D0D),
            appBar: AppBar(
              backgroundColor: const Color(0xFF0D0D0D),
              elevation: 0,
              leading: IconButton(
                icon: const FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
                onPressed: () => Navigator.of(context).pop(),
              ),
              title: const Text(
                'Developer Settings',
                style: TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
              ),
              centerTitle: true,
              actions: [
                TextButton(
                  onPressed: provider.savingSettingsLoading ? null : provider.saveSettings,
                  child: Text(
                    provider.savingSettingsLoading ? 'Saving...' : 'Save',
                    style: TextStyle(
                      color: provider.savingSettingsLoading ? Colors.grey : Colors.white,
                      fontWeight: FontWeight.w500,
                      fontSize: 16,
                    ),
                  ),
                ),
              ],
            ),
            body: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Persona Section
                  GestureDetector(
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (context) => const PersonaProfilePage(),
                          settings: const RouteSettings(
                            arguments: 'from_settings',
                          ),
                        ),
                      );
                      MixpanelManager().pageOpened('Developer Persona Settings');
                    },
                    child: Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1C1E),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: const Color(0xFF2A2A2E),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Center(
                              child: FaIcon(
                                FontAwesomeIcons.solidCircleUser,
                                color: Colors.grey.shade400,
                                size: 16,
                              ),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    const Text(
                                      'Persona',
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontSize: 16,
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                                      decoration: BoxDecoration(
                                        color: Colors.orange.withOpacity(0.2),
                                        borderRadius: BorderRadius.circular(10),
                                      ),
                                      child: const Text(
                                        'BETA',
                                        style: TextStyle(
                                          color: Colors.orange,
                                          fontSize: 10,
                                          fontWeight: FontWeight.w600,
                                          letterSpacing: 0.5,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'Configure your AI persona',
                                  style: TextStyle(
                                    color: Colors.grey.shade500,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          FaIcon(
                            FontAwesomeIcons.chevronRight,
                            color: Colors.grey.shade600,
                            size: 14,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),

                  // Transcription Section
                  GestureDetector(
                    onTap: () async {
                      await Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (context) => const TranscriptionSettingsPage(),
                        ),
                      );
                      if (mounted) {
                        setState(() {});
                      }
                    },
                    child: Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1C1E),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: const Color(0xFF2A2A2E),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Center(
                              child: FaIcon(
                                FontAwesomeIcons.microphone,
                                color: Colors.grey.shade400,
                                size: 16,
                              ),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Transcription',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'Configure STT provider',
                                  style: TextStyle(
                                    color: Colors.grey.shade500,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          _buildSttChip(),
                          const SizedBox(width: 8),
                          FaIcon(
                            FontAwesomeIcons.chevronRight,
                            color: Colors.grey.shade600,
                            size: 14,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),

                  // Conversation Timeout Section
                  GestureDetector(
                    onTap: () {
                      ConversationTimeoutDialog.show(context);
                    },
                    child: Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1C1E),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: const Color(0xFF2A2A2E),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Center(
                              child: FaIcon(
                                FontAwesomeIcons.clock,
                                color: Colors.grey.shade400,
                                size: 16,
                              ),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Conversation Timeout',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'Set when conversations auto-end',
                                  style: TextStyle(
                                    color: Colors.grey.shade500,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          FaIcon(
                            FontAwesomeIcons.chevronRight,
                            color: Colors.grey.shade600,
                            size: 14,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),

                  // Import Data Section
                  GestureDetector(
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (context) => const ImportHistoryPage(),
                        ),
                      );
                    },
                    child: Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1C1E),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: const Color(0xFF2A2A2E),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Center(
                              child: FaIcon(
                                FontAwesomeIcons.fileImport,
                                color: Colors.grey.shade400,
                                size: 16,
                              ),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Import Data',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'Import data from other sources',
                                  style: TextStyle(
                                    color: Colors.grey.shade500,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          FaIcon(
                            FontAwesomeIcons.chevronRight,
                            color: Colors.grey.shade600,
                            size: 14,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 32),

                  // Debug Logs Section
                  _buildSectionHeader('Debug & Diagnostics'),
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1C1C1E),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Column(
                      children: [
                        // Debug Logs toggle
                        Row(
                          children: [
                            Container(
                              width: 40,
                              height: 40,
                              decoration: BoxDecoration(
                                color: const Color(0xFF2A2A2E),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: Center(
                                child: FaIcon(
                                  FontAwesomeIcons.bug,
                                  color: Colors.grey.shade400,
                                  size: 16,
                                ),
                              ),
                            ),
                            const SizedBox(width: 14),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text(
                                    'Debug Logs',
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    SharedPreferencesUtil().devLogsToFileEnabled
                                        ? 'Auto-deletes after 3 days.'
                                        : 'Helps diagnose issues',
                                    style: TextStyle(
                                      color: Colors.grey.shade500,
                                      fontSize: 13,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Switch(
                              value: SharedPreferencesUtil().devLogsToFileEnabled,
                              onChanged: (v) async {
                                await DebugLogManager.setEnabled(v);
                                setState(() {});
                              },
                              activeColor: const Color(0xFF22C55E),
                            ),
                          ],
                        ),

                        // Action buttons when enabled
                        if (SharedPreferencesUtil().devLogsToFileEnabled) ...[
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
                                      backgroundColor: const Color(0xFF1C1C1E),
                                      shape: const RoundedRectangleBorder(
                                        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                                      ),
                                      builder: (ctx) {
                                        return SafeArea(
                                          child: Column(
                                            mainAxisSize: MainAxisSize.min,
                                            children: [
                                              Container(
                                                margin: const EdgeInsets.only(top: 8),
                                                height: 4,
                                                width: 36,
                                                decoration: BoxDecoration(
                                                  color: const Color(0xFF3C3C43),
                                                  borderRadius: BorderRadius.circular(2),
                                                ),
                                              ),
                                              const Padding(
                                                padding: EdgeInsets.all(16),
                                                child: Text(
                                                  'Select Log File',
                                                  style: TextStyle(
                                                    color: Colors.white,
                                                    fontSize: 18,
                                                    fontWeight: FontWeight.w600,
                                                  ),
                                                ),
                                              ),
                                              Flexible(
                                                child: ListView.separated(
                                                  shrinkWrap: true,
                                                  itemCount: files.length,
                                                  separatorBuilder: (_, __) =>
                                                      const Divider(height: 1, color: Color(0xFF3C3C43)),
                                                  itemBuilder: (ctx, i) {
                                                    final f = files[i];
                                                    final name = f.uri.pathSegments.last;
                                                    return ListTile(
                                                      title: Text(name, style: const TextStyle(color: Colors.white)),
                                                      trailing: const FaIcon(FontAwesomeIcons.chevronRight,
                                                          color: Color(0xFF3C3C43), size: 14),
                                                      onTap: () => Navigator.of(ctx).pop(f),
                                                    );
                                                  },
                                                ),
                                              ),
                                            ],
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
                                    padding: const EdgeInsets.symmetric(vertical: 12),
                                    decoration: BoxDecoration(
                                      color: const Color(0xFF2A2A2E),
                                      borderRadius: BorderRadius.circular(10),
                                    ),
                                    child: Row(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        FaIcon(FontAwesomeIcons.fileArrowUp, color: Colors.grey.shade300, size: 16),
                                        const SizedBox(width: 8),
                                        Text(
                                          'Share Logs',
                                          style: TextStyle(
                                            color: Colors.grey.shade300,
                                            fontSize: 14,
                                            fontWeight: FontWeight.w500,
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
                                  padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                                  decoration: BoxDecoration(
                                    color: Colors.red.withOpacity(0.15),
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: Row(
                                    children: [
                                      const FaIcon(FontAwesomeIcons.trash, color: Colors.redAccent, size: 14),
                                      const SizedBox(width: 6),
                                      const Text(
                                        'Clear',
                                        style: TextStyle(
                                          color: Colors.redAccent,
                                          fontSize: 14,
                                          fontWeight: FontWeight.w500,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  GestureDetector(
                    onTap: provider.loadingExportMemories
                        ? null
                        : () async {
                            if (provider.loadingExportMemories) return;
                            setState(() => provider.loadingExportMemories = true);
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Export started. This may take a few seconds...'),
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
                              debugPrint('Export shared');
                            }
                            MixpanelManager().exportMemories();
                            setState(() => provider.loadingExportMemories = false);
                          },
                    child: Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1C1E),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: const Color(0xFF2A2A2E),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Center(
                              child: FaIcon(
                                FontAwesomeIcons.fileExport,
                                color: Colors.grey.shade400,
                                size: 16,
                              ),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Export All Data',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'Export conversations to a JSON file',
                                  style: TextStyle(
                                    color: Colors.grey.shade500,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          if (provider.loadingExportMemories)
                            const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          else
                            FaIcon(
                              FontAwesomeIcons.chevronRight,
                              color: Colors.grey.shade400,
                              size: 16,
                            ),
                        ],
                      ),
                    ),
                  ),

                  const SizedBox(height: 32),

                  // Knowledge Graph Section
                  GestureDetector(
                    onTap: () {
                      showDialog(
                        context: context,
                        builder: (ctx) => AlertDialog(
                          backgroundColor: const Color(0xFF1C1C1E),
                          title: const Text('Delete Knowledge Graph?', style: TextStyle(color: Colors.white)),
                          content: const Text(
                            'This will delete all derived knowledge graph data (nodes and connections). Your original memories will remain safe. The graph will be rebuilt over time or upon next request.',
                            style: TextStyle(color: Colors.white70),
                          ),
                          actions: [
                            TextButton(
                              onPressed: () => Navigator.of(ctx).pop(),
                              child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
                            ),
                            TextButton(
                              onPressed: () async {
                                Navigator.of(ctx).pop();
                                try {
                                  // Call delete endpoint
                                  await KnowledgeGraphApi.deleteKnowledgeGraph();
                                  AppSnackbar.showSnackbar('Knowledge Graph deleted successfully');
                                } catch (e) {
                                  AppSnackbar.showSnackbarError('Failed to delete graph: $e');
                                }
                              },
                              child: const Text('Delete', style: TextStyle(color: Colors.redAccent)),
                            ),
                          ],
                        ),
                      );
                    },
                    child: Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1C1E),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: const Color(0xFF2A2A2E),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Center(
                              child: FaIcon(
                                FontAwesomeIcons.trash,
                                color: Colors.redAccent.shade100,
                                size: 16,
                              ),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Delete Knowledge Graph',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'Clear all nodes and connections',
                                  style: TextStyle(
                                    color: Colors.grey.shade500,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          FaIcon(
                            FontAwesomeIcons.chevronRight,
                            color: Colors.grey.shade600,
                            size: 14,
                          ),
                        ],
                      ),
                    ),
                  ),

                  const SizedBox(height: 32),

                  // Developer API Keys Section
                  const DeveloperApiKeysSection(),

                  const SizedBox(height: 32),

                  // MCP Section
                  Padding(
                    padding: const EdgeInsets.only(left: 4, right: 4, bottom: 12),
                    child: Row(
                      children: [
                        const Text(
                          'MCP',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const Spacer(),
                        _buildDocsButton('https://docs.omi.me/doc/developer/MCP', 'MCP'),
                        const SizedBox(width: 8),
                        _buildCreateKeyButton(() => showDialog(
                              context: context,
                              builder: (context) => const CreateMcpApiKeyDialog(),
                            )),
                      ],
                    ),
                  ),
                  _buildApiKeysList(context),

                  const SizedBox(height: 24),

                  // Claude Desktop Integration
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1C1C1E),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              width: 40,
                              height: 40,
                              decoration: BoxDecoration(
                                color: const Color(0xFF2A2A2E),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: Center(
                                child: FaIcon(FontAwesomeIcons.desktop, color: Colors.grey.shade400, size: 16),
                              ),
                            ),
                            const SizedBox(width: 14),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text(
                                    'Claude Desktop',
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    'Add to claude_desktop_config.json',
                                    style: TextStyle(
                                      color: Colors.grey.shade500,
                                      fontSize: 13,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        // Code block with JSON syntax highlighting
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: const Color(0xFF0D0D0D),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(color: const Color(0xFF2A2A2E), width: 1),
                          ),
                          child: RichText(
                            text: TextSpan(
                              style: const TextStyle(
                                fontFamily: 'Ubuntu Mono',
                                fontSize: 11,
                                height: 1.6,
                              ),
                              children: [
                                const TextSpan(text: '{\n', style: TextStyle(color: Colors.white)),
                                const TextSpan(text: '  ', style: TextStyle(color: Colors.white)),
                                TextSpan(text: '"mcpServers"', style: TextStyle(color: Colors.cyan.shade300)),
                                const TextSpan(text: ': {\n', style: TextStyle(color: Colors.white)),
                                const TextSpan(text: '    ', style: TextStyle(color: Colors.white)),
                                TextSpan(text: '"omi"', style: TextStyle(color: Colors.cyan.shade300)),
                                const TextSpan(text: ': {\n', style: TextStyle(color: Colors.white)),
                                const TextSpan(text: '      ', style: TextStyle(color: Colors.white)),
                                TextSpan(text: '"command"', style: TextStyle(color: Colors.cyan.shade300)),
                                const TextSpan(text: ': ', style: TextStyle(color: Colors.white)),
                                TextSpan(text: '"docker"', style: TextStyle(color: Colors.orange.shade300)),
                                const TextSpan(text: ',\n', style: TextStyle(color: Colors.white)),
                                const TextSpan(text: '      ', style: TextStyle(color: Colors.white)),
                                TextSpan(text: '"args"', style: TextStyle(color: Colors.cyan.shade300)),
                                const TextSpan(text: ': [\n', style: TextStyle(color: Colors.white)),
                                const TextSpan(text: '        ', style: TextStyle(color: Colors.white)),
                                TextSpan(text: '"run"', style: TextStyle(color: Colors.orange.shade300)),
                                const TextSpan(text: ', ', style: TextStyle(color: Colors.white)),
                                TextSpan(text: '"--rm"', style: TextStyle(color: Colors.orange.shade300)),
                                const TextSpan(text: ', ', style: TextStyle(color: Colors.white)),
                                TextSpan(text: '"-i"', style: TextStyle(color: Colors.orange.shade300)),
                                const TextSpan(text: ', ', style: TextStyle(color: Colors.white)),
                                TextSpan(text: '"-e"', style: TextStyle(color: Colors.orange.shade300)),
                                const TextSpan(text: ',\n', style: TextStyle(color: Colors.white)),
                                const TextSpan(text: '        ', style: TextStyle(color: Colors.white)),
                                TextSpan(
                                    text: '"OMI_API_KEY=<your_key>"', style: TextStyle(color: Colors.orange.shade300)),
                                const TextSpan(text: ',\n', style: TextStyle(color: Colors.white)),
                                const TextSpan(text: '        ', style: TextStyle(color: Colors.white)),
                                TextSpan(
                                    text: '"omiai/mcp-server:latest"', style: TextStyle(color: Colors.orange.shade300)),
                                const TextSpan(text: '\n      ]\n    }\n  }\n}', style: TextStyle(color: Colors.white)),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 12),
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
                            AppSnackbar.showSnackbar('Config copied to clipboard');
                          },
                          child: Container(
                            width: double.infinity,
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            decoration: BoxDecoration(
                              color: const Color(0xFF2A2A2E),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                FaIcon(FontAwesomeIcons.copy, color: Colors.grey.shade300, size: 14),
                                const SizedBox(width: 8),
                                Text(
                                  'Copy Config',
                                  style: TextStyle(
                                    color: Colors.grey.shade300,
                                    fontSize: 14,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 24),

                  // MCP Server Section
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1C1C1E),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              width: 40,
                              height: 40,
                              decoration: BoxDecoration(
                                color: const Color(0xFF2A2A2E),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: Center(
                                child: FaIcon(FontAwesomeIcons.server, color: Colors.grey.shade400, size: 16),
                              ),
                            ),
                            const SizedBox(width: 14),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text(
                                    'MCP Server',
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    'Connect AI assistants to your data',
                                    style: TextStyle(
                                      color: Colors.grey.shade500,
                                      fontSize: 13,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 20),

                        // Server URL
                        Text(
                          'Server URL',
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 12, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 8),
                        Builder(
                          builder: (context) {
                            final mcpUrl = '${Env.apiBaseUrl}v1/mcp/sse';
                            return GestureDetector(
                              onTap: () {
                                Clipboard.setData(ClipboardData(text: mcpUrl));
                                AppSnackbar.showSnackbar('URL copied');
                              },
                              child: Container(
                                width: double.infinity,
                                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF0D0D0D),
                                  borderRadius: BorderRadius.circular(10),
                                  border: Border.all(color: const Color(0xFF2A2A2E), width: 1),
                                ),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        mcpUrl,
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontFamily: 'Ubuntu Mono',
                                          fontSize: 13,
                                        ),
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    FaIcon(FontAwesomeIcons.copy, color: Colors.grey.shade500, size: 14),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),

                        const SizedBox(height: 20),
                        Divider(color: Colors.grey.shade800, height: 1),
                        const SizedBox(height: 20),

                        // API Key Auth Section
                        Text(
                          'API Key Auth',
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 12, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              flex: 2,
                              child: Text(
                                'Header',
                                style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                              ),
                            ),
                            Expanded(
                              flex: 3,
                              child: Text(
                                'Authorization: Bearer <key>',
                                style: TextStyle(
                                  color: Colors.grey.shade600,
                                  fontSize: 12,
                                  fontFamily: 'Ubuntu Mono',
                                ),
                              ),
                            ),
                          ],
                        ),

                        const SizedBox(height: 20),
                        Divider(color: Colors.grey.shade800, height: 1),
                        const SizedBox(height: 20),

                        // OAuth Section
                        Text(
                          'OAuth',
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 12, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 12),

                        // Client ID
                        _buildMcpConfigRow('Client ID', 'omi'),
                        const SizedBox(height: 8),

                        // Client Secret hint
                        Row(
                          children: [
                            Expanded(
                              flex: 2,
                              child: Text(
                                'Client Secret',
                                style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                              ),
                            ),
                            Expanded(
                              flex: 3,
                              child: Text(
                                'Use your MCP API key',
                                style: TextStyle(
                                  color: Colors.grey.shade600,
                                  fontSize: 13,
                                  fontStyle: FontStyle.italic,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 32),

                  // Webhooks Section
                  Padding(
                    padding: const EdgeInsets.only(left: 4, right: 4, bottom: 12),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Webhooks',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        _buildDocsButton('https://docs.omi.me/doc/developer/apps/Introduction', 'Webhooks'),
                      ],
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1C1C1E),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Column(
                      children: [
                        // Conversation Events
                        _buildWebhookItem(
                          title: 'Conversation Events',
                          description: 'New conversation created',
                          icon: FontAwesomeIcons.message,
                          isEnabled: provider.conversationEventsToggled,
                          onToggle: provider.onConversationEventsToggled,
                          controller: provider.webhookOnConversationCreated,
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        // Real-time Transcript
                        _buildWebhookItem(
                          title: 'Real-time Transcript',
                          description: 'Transcript received',
                          icon: FontAwesomeIcons.closedCaptioning,
                          isEnabled: provider.transcriptsToggled,
                          onToggle: provider.onTranscriptsToggled,
                          controller: provider.webhookOnTranscriptReceived,
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        // Realtime Audio Bytes
                        _buildWebhookItem(
                          title: 'Audio Bytes',
                          description: 'Audio data received',
                          icon: FontAwesomeIcons.waveSquare,
                          isEnabled: provider.audioBytesToggled,
                          onToggle: provider.onAudioBytesToggled,
                          controller: provider.webhookAudioBytes,
                          extraField: _buildTextField(
                            controller: provider.webhookAudioBytesDelay,
                            label: 'Interval (seconds)',
                            keyboardType: TextInputType.number,
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        // Day Summary
                        _buildWebhookItem(
                          title: 'Day Summary',
                          description: 'Summary generated',
                          icon: FontAwesomeIcons.calendarDay,
                          isEnabled: provider.daySummaryToggled,
                          onToggle: provider.onDaySummaryToggled,
                          controller: provider.webhookDaySummary,
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 32),

                  // Experimental Section
                  Padding(
                    padding: const EdgeInsets.only(left: 4, right: 4, bottom: 12),
                    child: const Text(
                      'Experimental',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1C1C1E),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Column(
                      children: [
                        // Transcription Diagnostics
                        _buildExperimentalItem(
                          title: 'Transcription Diagnostics',
                          description: 'Detailed diagnostic messages',
                          icon: FontAwesomeIcons.stethoscope,
                          value: provider.transcriptionDiagnosticEnabled,
                          onChanged: provider.onTranscriptionDiagnosticChanged,
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        // Auto-create Speakers
                        _buildExperimentalItem(
                          title: 'Auto-create Speakers',
                          description: 'Auto-create when name detected',
                          icon: FontAwesomeIcons.userPlus,
                          value: provider.autoCreateSpeakersEnabled,
                          onChanged: provider.onAutoCreateSpeakersChanged,
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        // Follow-up Questions
                        _buildExperimentalItem(
                          title: 'Follow-up Questions',
                          description: 'Suggest questions after conversations',
                          icon: FontAwesomeIcons.lightbulb,
                          value: provider.followUpQuestionEnabled,
                          onChanged: provider.onFollowUpQuestionChanged,
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        // Goal Tracker
                        _buildExperimentalItem(
                          title: 'Goal Tracker',
                          description: 'Track your personal goals on homepage',
                          icon: FontAwesomeIcons.bullseye,
                          value: provider.showGoalTrackerEnabled,
                          onChanged: provider.onShowGoalTrackerChanged,
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        // Daily Reflection
                        _buildExperimentalItem(
                          title: 'Daily Reflection',
                          description: 'Get a 9 PM reminder to reflect on your day',
                          icon: FontAwesomeIcons.moon,
                          value: provider.dailyReflectionEnabled,
                          onChanged: provider.onDailyReflectionChanged,
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 48),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

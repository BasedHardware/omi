import 'dart:io';

import 'package:flutter/material.dart';

import 'package:file_picker/file_picker.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/developer_firmware_flash_page.dart';
import 'package:omi/pages/settings/developer_mcp_section.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/pages/settings/widgets/developer_api_keys_section.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/firmware_update_build_policy.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';

/// Developer Settings: developer tools only (D4) — creator payouts, debug logs, API keys, MCP,
/// webhooks, experiments and custom firmware. Everyday settings live in top-level Settings.
///
/// Every switch applies when flipped. The webhook URL fields are the one editor on the page: they
/// wait for Save, and leaving with unsaved edits asks first (chat-apps-settings #2, nav #24).
class DeveloperSettingsPage extends StatelessWidget {
  const DeveloperSettingsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => DeveloperModeProvider()..initialize(),
      child: const _DeveloperSettingsPageView(),
    );
  }
}

class _DeveloperSettingsPageView extends StatefulWidget {
  const _DeveloperSettingsPageView();

  @override
  State<_DeveloperSettingsPageView> createState() => _DeveloperSettingsPageState();
}

class _DeveloperSettingsPageState extends State<_DeveloperSettingsPageView> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<McpProvider>().fetchKeys();
    });
  }

  // iPad requires a non-zero sharePositionOrigin (popover anchor) for the share sheet.
  Rect _shareOrigin() {
    if (!mounted) return const Rect.fromLTWH(0, 0, 100, 100);
    final box = context.findRenderObject() as RenderBox?;
    if (box != null && box.hasSize && box.size.width > 0 && box.size.height > 0) {
      return box.localToGlobal(Offset.zero) & box.size;
    }
    return const Rect.fromLTWH(0, 0, 100, 100);
  }

  /// Asks before throwing away unsaved webhook edits. Resolves whether the page may close.
  Future<bool> _confirmDiscard(DeveloperModeProvider provider) async {
    final l10n = context.l10n;
    final discard = await showOmiConfirm(
      context,
      title: l10n.discardChangesTitle,
      message: l10n.discardChangesMessage,
      confirmLabel: l10n.discard,
      cancelLabel: l10n.keepEditing,
      destructive: true,
    );
    if (discard) provider.discardWebhookChanges();
    return discard;
  }

  Future<void> _shareLogs() async {
    final l10n = context.l10n;
    final files = await DebugLogManager.listLogFiles();
    if (!mounted) return;
    if (files.isEmpty) {
      OmiFeedback.info(context, l10n.noLogFilesFound);
      return;
    }
    File? selected = files.length == 1 ? files.first : null;
    selected ??= await showOmiSheet<File>(
      context: context,
      title: l10n.selectLogFile,
      builder: (sheetContext) => SingleChildScrollView(
        child: OmiSettingsGroup(
          children: [
            for (final f in files)
              OmiSettingsRow(title: f.uri.pathSegments.last, onTap: () => Navigator.of(sheetContext).pop(f)),
          ],
        ),
      ),
    );
    if (selected == null || !mounted) return;
    final result = await SharePlus.instance.share(
      ShareParams(files: [XFile(selected.path)], text: l10n.omiDebugLog, sharePositionOrigin: _shareOrigin()),
    );
    if (result.status == ShareResultStatus.success) Logger.debug('Log shared');
  }

  Future<void> _pickFirmware(DeviceProvider provider) async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['zip'],
      dialogTitle: context.l10n.selectFirmwareZip,
    );
    if (result == null || result.files.isEmpty) return;
    final file = result.files.first;
    if (file.path == null || !mounted) return;
    await routeToPage(
      context,
      DeveloperFirmwareFlashPage(zipFilePath: file.path!, fileName: file.name, device: provider.pairedDevice!),
    );
  }

  Widget _buildDebugLogs() {
    final l10n = context.l10n;
    final enabled = SharedPreferencesUtil().devLogsToFileEnabled;
    return OmiSettingsGroup(
      header: l10n.debugAndDiagnostics,
      children: [
        OmiSettingsRow.toggle(
          leading: const FaIcon(FontAwesomeIcons.bug),
          title: l10n.debugLogs,
          subtitle: enabled ? l10n.autoDeletesAfterThreeDays : l10n.helpsDiagnoseIssues,
          value: enabled,
          onChanged: (v) async {
            await DebugLogManager.setEnabled(v);
            if (mounted) setState(() {});
          },
        ),
        if (enabled)
          Padding(
            padding: const EdgeInsets.all(OmiSpacing.md),
            child: Row(
              children: [
                Expanded(
                  child: OmiButton.secondary(
                    label: l10n.shareLogs,
                    leading: const FaIcon(FontAwesomeIcons.fileArrowUp),
                    size: OmiButtonSize.compact,
                    onPressed: _shareLogs,
                  ),
                ),
                const SizedBox(width: OmiSpacing.sm),
                OmiButton.destructive(
                  label: l10n.clear,
                  leading: const FaIcon(FontAwesomeIcons.trash),
                  size: OmiButtonSize.compact,
                  onPressed: () async {
                    final message = l10n.debugLogCleared;
                    await DebugLogManager.clear();
                    if (mounted) OmiFeedback.confirm(context, message);
                  },
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _buildWebhookItem({
    required String title,
    required String description,
    required FaIconData icon,
    required bool isEnabled,
    required ValueChanged<bool> onToggle,
    required TextEditingController controller,
    Widget? extraField,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OmiSettingsRow.toggle(
          leading: FaIcon(icon),
          title: title,
          subtitle: description,
          value: isEnabled,
          onChanged: onToggle,
        ),
        if (isEnabled)
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _DeveloperTextField(controller: controller, label: context.l10n.endpointUrl),
                if (extraField != null) ...[const SizedBox(height: OmiSpacing.xs), extraField],
              ],
            ),
          ),
      ],
    );
  }

  Widget _buildWebhooks(DeveloperModeProvider provider) {
    final l10n = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OmiSectionHeader(
          l10n.webhooks,
          trailing: const DeveloperDocsButton(
            url: 'https://docs.omi.me/doc/developer/apps/Introduction',
            analyticsLabel: 'Webhooks',
          ),
        ),
        OmiSettingsGroup(
          children: [
            _buildWebhookItem(
              title: l10n.conversationEvents,
              description: l10n.newConversationCreated,
              icon: FontAwesomeIcons.message,
              isEnabled: provider.conversationEventsToggled,
              onToggle: provider.onConversationEventsToggled,
              controller: provider.webhookOnConversationCreated,
            ),
            _buildWebhookItem(
              title: l10n.realTimeTranscript,
              description: l10n.transcriptReceived,
              icon: FontAwesomeIcons.closedCaptioning,
              isEnabled: provider.transcriptsToggled,
              onToggle: provider.onTranscriptsToggled,
              controller: provider.webhookOnTranscriptReceived,
            ),
            _buildWebhookItem(
              title: l10n.audioBytes,
              description: l10n.audioDataReceived,
              icon: FontAwesomeIcons.waveSquare,
              isEnabled: provider.audioBytesToggled,
              onToggle: provider.onAudioBytesToggled,
              controller: provider.webhookAudioBytes,
              extraField: _DeveloperTextField(
                controller: provider.webhookAudioBytesDelay,
                label: l10n.intervalSeconds,
                keyboardType: TextInputType.number,
              ),
            ),
            _buildWebhookItem(
              title: l10n.daySummary,
              description: l10n.summaryGenerated,
              icon: FontAwesomeIcons.calendarDay,
              isEnabled: provider.daySummaryToggled,
              onToggle: provider.onDaySummaryToggled,
              controller: provider.webhookDaySummary,
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildExperimental(DeveloperModeProvider provider) {
    final l10n = context.l10n;
    return OmiSettingsGroup(
      header: l10n.experimental,
      children: [
        OmiSettingsRow.toggle(
          leading: const FaIcon(FontAwesomeIcons.code),
          title: l10n.conversationDeveloperTools,
          subtitle: l10n.conversationDeveloperToolsDescription,
          value: SharedPreferencesUtil().devModeEnabled,
          onChanged: (v) => setState(() => SharedPreferencesUtil().devModeEnabled = v),
        ),
        OmiSettingsRow.toggle(
          leading: const FaIcon(FontAwesomeIcons.stethoscope),
          title: l10n.transcriptionDiagnostics,
          subtitle: l10n.detailedDiagnosticMessages,
          value: provider.transcriptionDiagnosticEnabled,
          onChanged: provider.onTranscriptionDiagnosticChanged,
        ),
        OmiSettingsRow.toggle(
          leading: const FaIcon(FontAwesomeIcons.userPlus),
          title: l10n.autoCreateSpeakers,
          subtitle: l10n.autoCreateWhenNameDetected,
          value: provider.autoCreateSpeakersEnabled,
          onChanged: provider.onAutoCreateSpeakersChanged,
        ),
        OmiSettingsRow.toggle(
          leading: const FaIcon(FontAwesomeIcons.microphoneSlash),
          title: l10n.vadGate,
          subtitle: l10n.vadGateDescription,
          value: provider.vadGateEnabled,
          onChanged: provider.onVadGateChanged,
        ),
      ],
    );
  }

  Widget _buildFirmware() {
    final deviceProvider = context.watch<DeviceProvider>();
    if (!FirmwareUpdateBuildPolicy.current.allowsOmiFirmwareUpdate ||
        !deviceProvider.isConnected ||
        deviceProvider.pairedDevice == null) {
      return const SizedBox.shrink();
    }
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.xxl),
      child: OmiSettingsGroup(
        header: l10n.firmware,
        headerSubtitle: l10n.flashCustomFirmwareDescription,
        children: [
          OmiSettingsRow(
            leading: const FaIcon(FontAwesomeIcons.microchip),
            title: l10n.flashCustomFirmware,
            onTap: () => _pickFirmware(deviceProvider),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<DeveloperModeProvider>(
      builder: (context, provider, child) {
        final dirty = provider.hasUnsavedWebhookChanges;
        return PopScope(
          canPop: !dirty,
          onPopInvokedWithResult: (didPop, _) async {
            if (didPop) return;
            if (await _confirmDiscard(provider) && context.mounted) Navigator.of(context).pop();
          },
          child: GestureDetector(
            onTap: () => FocusScope.of(context).unfocus(),
            child: Scaffold(
              appBar: AppBar(
                leading: const OmiBackButton(),
                title: Text(l10n.developerSettings),
                actions: [
                  if (dirty || provider.savingSettingsLoading)
                    Padding(
                      padding: const EdgeInsets.only(right: OmiSpacing.xs),
                      child: Center(
                        child: OmiButton.tertiary(
                          label: l10n.save,
                          size: OmiButtonSize.compact,
                          isLoading: provider.savingSettingsLoading,
                          onPressed: provider.saveSettings,
                        ),
                      ),
                    ),
                ],
              ),
              body: ListView(
                padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xs, OmiSpacing.lg, OmiSpacing.xxl),
                children: [
                  OmiSettingsGroup(
                    header: l10n.appCreators,
                    children: [
                      OmiSettingsRow(
                        leading: const FaIcon(FontAwesomeIcons.solidCreditCard),
                        title: l10n.creatorPayouts,
                        onTap: () => openSettingsDestination(context, SettingsDestination.creatorPayouts),
                      ),
                    ],
                  ),
                  const SizedBox(height: OmiSpacing.xxl),
                  _buildDebugLogs(),
                  const SizedBox(height: OmiSpacing.xxl),
                  const DeveloperApiKeysSection(),
                  const SizedBox(height: OmiSpacing.xxl),
                  const DeveloperMcpSection(),
                  const SizedBox(height: OmiSpacing.xxl),
                  _buildWebhooks(provider),
                  const SizedBox(height: OmiSpacing.xxl),
                  _buildExperimental(provider),
                  _buildFirmware(),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _DeveloperTextField extends StatelessWidget {
  const _DeveloperTextField({required this.controller, required this.label, this.keyboardType});

  final TextEditingController controller;
  final String label;
  final TextInputType? keyboardType;

  @override
  Widget build(BuildContext context) {
    const border = OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none);
    return TextField(
      controller: controller,
      keyboardType: keyboardType ?? TextInputType.url,
      autocorrect: false,
      style: OmiType.subhead,
      decoration: InputDecoration(
        labelText: label,
        labelStyle: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
        filled: true,
        fillColor: OmiColors.surface2,
        contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
        border: border,
        enabledBorder: border,
        focusedBorder: const OutlineInputBorder(
          borderRadius: OmiRadius.mdAll,
          borderSide: BorderSide(color: OmiColors.textTertiary),
        ),
      ),
    );
  }
}

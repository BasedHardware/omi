import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/firmware_mixin.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/pages/settings/conversation_timeout_dialog.dart';
import 'package:omi/pages/settings/import_history_page.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/pages/settings/widgets/create_mcp_api_key_dialog.dart';
import 'package:omi/pages/settings/widgets/developer_api_keys_section.dart';
import 'package:omi/pages/settings/widgets/mcp_api_key_list_item.dart';
import 'package:omi/providers/ambient_capture_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/services/ambient_capture/ambient_capture_health.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

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

class _DeveloperSettingsPageState extends State<_DeveloperSettingsPageView> with WidgetsBindingObserver {
  final List<Timer> _ambientPermissionRefreshTimers = [];
  bool _ambientSetupLoading = false;
  bool _ambientMicGranted = false;
  bool _ambientNotificationsGranted = false;
  bool _ambientBatteryExempt = false;
  bool _ambientAccessibilityEnabled = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      context.read<McpProvider>().fetchKeys();
      await _refreshAmbientSetupState();
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _scheduleAmbientPermissionRefresh();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    for (final timer in _ambientPermissionRefreshTimers) {
      timer.cancel();
    }
    _ambientPermissionRefreshTimers.clear();
    super.dispose();
  }

  void _scheduleAmbientPermissionRefresh({List<int> delaysMs = const [250, 1000, 2000]}) {
    if (!Platform.isAndroid) return;
    for (final delayMs in delaysMs) {
      final timer = Timer(Duration(milliseconds: delayMs), () {
        if (mounted) {
          _refreshAmbientSetupState();
        }
      });
      _ambientPermissionRefreshTimers.add(timer);
    }
  }

  ButtonStyle get _ambientPrimaryButtonStyle => ElevatedButton.styleFrom(
        backgroundColor: const Color(0xFF2563EB),
        foregroundColor: Colors.white,
        disabledBackgroundColor: const Color(0xFF2A2A2E),
        disabledForegroundColor: Colors.grey.shade600,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      );

  ButtonStyle get _ambientSuccessButtonStyle => ElevatedButton.styleFrom(
        backgroundColor: const Color(0xFF16A34A),
        foregroundColor: Colors.white,
        disabledBackgroundColor: const Color(0xFF2A2A2E),
        disabledForegroundColor: Colors.grey.shade600,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      );

  ButtonStyle get _ambientDangerButtonStyle => ElevatedButton.styleFrom(
        backgroundColor: const Color(0xFFB91C1C),
        foregroundColor: Colors.white,
        disabledBackgroundColor: const Color(0xFF2A2A2E),
        disabledForegroundColor: Colors.grey.shade600,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      );

  ButtonStyle get _ambientOutlineButtonStyle => OutlinedButton.styleFrom(
        foregroundColor: Colors.white,
        disabledForegroundColor: Colors.grey.shade600,
        side: BorderSide(color: Colors.grey.shade600),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      );

  ButtonStyle get _ambientTextButtonStyle => TextButton.styleFrom(
        foregroundColor: const Color(0xFF93C5FD),
        disabledForegroundColor: Colors.grey.shade600,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      );

  Future<void> _refreshAmbientSetupState() async {
    if (!Platform.isAndroid || !mounted) return;
    final ambientService = context.read<AmbientCaptureProvider>().service;
    final mic = await Permission.microphone.isGranted;
    final notifications = await Permission.notification.isGranted;
    final battery = await FlutterForegroundTask.isIgnoringBatteryOptimizations;
    var accessibility = false;
    try {
      accessibility = await ambientService.isAccessibilityEnabled();
    } catch (e) {
      Logger.debug('Ambient setup accessibility check failed: $e');
    }
    if (!mounted) return;
    setState(() {
      _ambientMicGranted = mic;
      _ambientNotificationsGranted = notifications;
      _ambientBatteryExempt = battery;
      _ambientAccessibilityEnabled = accessibility;
    });
  }

  Future<void> _runAmbientSetup() async {
    if (!Platform.isAndroid || _ambientSetupLoading) return;
    setState(() => _ambientSetupLoading = true);
    final prefs = SharedPreferencesUtil();
    final ambientService = context.read<AmbientCaptureProvider>().service;
    try {
      AmbientCaptureProvider.applyFullCoverageDefaults();

      final mic = await Permission.microphone.request();
      if (!mic.isGranted && mic.isPermanentlyDenied) {
        await openAppSettings();
      }
      await ForegroundUtil.requestPermissions();
      await _refreshAmbientSetupState();

      final wantsAccessibility =
          prefs.ambientCaptureAccessibilityModeEnabled || prefs.ambientCaptureCaptionFallbackEnabled;
      if (wantsAccessibility && !_ambientAccessibilityEnabled && mounted) {
        AppSnackbar.showSnackbar(
          'Enable Omi in Android Accessibility settings, then return here.',
          duration: const Duration(seconds: 4),
        );
        await ambientService.openAccessibilitySettings();
        _scheduleAmbientPermissionRefresh(delaysMs: const [500, 1200, 2200, 4000]);
        await _showAmbientSetupInstructions(
          title: 'Enable Accessibility Service',
          icon: Icons.accessibility_new,
          instructions: const [
            'Find Omi in Android Accessibility settings.',
            'Open it and turn on the Omi service.',
            'Confirm the Android permission dialog, then return to Omi.',
          ],
          note:
              'Accessibility is optional and only used for foreground-app awareness or caption fallback when you enable it.',
        );
      }
    } catch (e) {
      Logger.debug('Ambient setup failed: $e');
      AppSnackbar.showSnackbarError('Ambient setup failed: $e', duration: const Duration(seconds: 4));
    } finally {
      await _refreshAmbientSetupState();
      if (mounted) {
        setState(() => _ambientSetupLoading = false);
      }
    }
  }

  Future<void> _startAmbientCapture(AmbientCaptureProvider ambient) async {
    final prefs = SharedPreferencesUtil();
    if (!Platform.isAndroid) {
      AppSnackbar.showSnackbarError('Advanced Ambient Capture is Android-only.');
      return;
    }
    if (!prefs.advancedAmbientCaptureEnabled) {
      prefs.advancedAmbientCaptureEnabled = true;
    }
    if (prefs.ambientCaptureMode == 'off') {
      prefs.ambientCaptureMode = 'normal';
    }
    await _runAmbientSetup();
    if (!mounted) return;
    if (!_ambientMicGranted) {
      AppSnackbar.showSnackbarError('Microphone permission is required before ambient capture can start.');
      return;
    }
    if (!_ambientNotificationsGranted) {
      AppSnackbar.showSnackbarError('Notification permission is required for the foreground capture notification.');
      return;
    }

    final started = await ambient.start();
    if (!mounted) return;
    if (started) {
      final localOnly = !prefs.ambientCaptureRawAudioUploadEnabled;
      AppSnackbar.showSnackbarSuccess(
        localOnly
            ? 'Ambient capture started. Audio is local-only until upload is enabled.'
            : 'Ambient capture started. Audio is routing to WAL and transcription.',
        duration: const Duration(seconds: 4),
      );
    } else {
      final reason = ambient.health.reason == null
          ? ambient.health.state.wireName
          : '${ambient.health.state.wireName}: ${ambient.health.reason}';
      AppSnackbar.showSnackbarError('Ambient capture did not start: $reason', duration: const Duration(seconds: 5));
    }
  }

  Future<void> _showAmbientSetupInstructions({
    required String title,
    required IconData icon,
    required List<String> instructions,
    String? note,
  }) async {
    if (!mounted) return;
    await showDialog(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          title: Row(
            children: [
              Icon(icon, color: const Color(0xFF93C5FD), size: 22),
              const SizedBox(width: 10),
              Expanded(child: Text(title, style: const TextStyle(color: Colors.white, fontSize: 18))),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (var i = 0; i < instructions.length; i++)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 24,
                        height: 24,
                        decoration: const BoxDecoration(color: Color(0xFF2563EB), shape: BoxShape.circle),
                        child: Center(
                          child: Text(
                            '${i + 1}',
                            style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700),
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(instructions[i], style: TextStyle(color: Colors.grey.shade200, fontSize: 14)),
                      ),
                    ],
                  ),
                ),
              if (note != null) ...[
                const SizedBox(height: 4),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(color: const Color(0xFF172554), borderRadius: BorderRadius.circular(8)),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.info_outline, color: Color(0xFF93C5FD), size: 16),
                      const SizedBox(width: 8),
                      Expanded(child: Text(note, style: const TextStyle(color: Color(0xFFDBEAFE), fontSize: 12))),
                    ],
                  ),
                ),
              ],
            ],
          ),
          actions: [
            TextButton(
              style: _ambientTextButtonStyle,
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Got it'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _openAmbientAccessibilitySettings(AmbientCaptureProvider ambient) async {
    await ambient.service.openAccessibilitySettings();
    _scheduleAmbientPermissionRefresh(delaysMs: const [500, 1200, 2200, 4000]);
    await _showAmbientSetupInstructions(
      title: 'Enable Accessibility Service',
      icon: Icons.accessibility_new,
      instructions: const [
        'Find Omi in Android Accessibility settings.',
        'Open it and turn on the Omi service.',
        'Confirm the Android permission dialog, then return to Omi.',
      ],
      note:
          'Accessibility is optional and only used for foreground-app awareness or caption fallback when you enable it.',
    );
  }

  Future<void> _requestAmbientBatteryOptimization() async {
    await FlutterForegroundTask.requestIgnoreBatteryOptimization();
    _scheduleAmbientPermissionRefresh(delaysMs: const [500, 1500, 3000]);
    await _showAmbientSetupInstructions(
      title: 'Battery Reliability',
      icon: Icons.battery_charging_full,
      instructions: const [
        'If Android shows a battery prompt, tap Allow.',
        'On Pixel, use Battery -> Unrestricted if you land in App Info.',
        'On Samsung and other phones, look for Allow background activity or Do not optimize.',
      ],
      note: 'This does not bypass Android restrictions; it just makes long-running foreground capture less fragile.',
    );
  }

  Widget _buildSectionContainer({required List<Widget> children}) {
    return Container(
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(12)),
      child: Column(children: children),
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
                style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
              ),
              if (trailing != null) trailing,
            ],
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 6),
            Text(subtitle, style: TextStyle(color: Colors.grey.shade400, fontSize: 14)),
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
      decoration: BoxDecoration(color: Colors.grey.shade800, borderRadius: BorderRadius.circular(8)),
      child: Text(
        label,
        style: const TextStyle(color: Colors.grey, fontSize: 11, fontWeight: FontWeight.w500),
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
          decoration: BoxDecoration(color: const Color(0xFF2A2A2E), borderRadius: BorderRadius.circular(10)),
          child: Center(child: FaIcon(icon, color: Colors.grey.shade400, size: 16)),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
              ),
              const SizedBox(height: 2),
              Text(description, style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
            ],
          ),
        ),
        Switch(value: value, onChanged: onChanged, activeColor: const Color(0xFF22C55E)),
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
              decoration: BoxDecoration(color: const Color(0xFF2A2A2E), borderRadius: BorderRadius.circular(10)),
              child: Center(child: FaIcon(icon, color: Colors.grey.shade400, size: 16)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                  ),
                  const SizedBox(height: 2),
                  Text(description, style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                ],
              ),
            ),
            Switch(value: isEnabled, onChanged: onToggle, activeColor: const Color(0xFF22C55E)),
          ],
        ),
        if (isEnabled) ...[
          const SizedBox(height: 12),
          _buildTextField(controller: controller, label: context.l10n.endpointUrl),
          if (extraField != null) ...[const SizedBox(height: 8), extraField],
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
      decoration: BoxDecoration(color: const Color(0xFF2C2C2E), borderRadius: BorderRadius.circular(10)),
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
        AppSnackbar.showSnackbar(context.l10n.labelCopied(label));
      },
      child: Row(
        children: [
          Expanded(
            flex: 2,
            child: Text(label, style: TextStyle(color: Colors.grey.shade500, fontSize: 13)),
          ),
          Expanded(
            flex: 3,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              decoration: BoxDecoration(color: const Color(0xFF0D0D0D), borderRadius: BorderRadius.circular(6)),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      value,
                      style: const TextStyle(color: Colors.white, fontFamily: 'Ubuntu Mono', fontSize: 13),
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

  Widget _buildAmbientDropdown({
    required String label,
    required String value,
    required List<String> values,
    required ValueChanged<String?> onChanged,
  }) {
    return Row(
      children: [
        Expanded(child: Text(label, style: const TextStyle(color: Colors.white, fontSize: 14))),
        DropdownButton<String>(
          value: value,
          dropdownColor: const Color(0xFF2C2C2E),
          style: const TextStyle(color: Colors.white, fontSize: 14),
          underline: const SizedBox.shrink(),
          items: values.map((v) => DropdownMenuItem(value: v, child: Text(v.replaceAll('_', ' ')))).toList(),
          onChanged: onChanged,
        ),
      ],
    );
  }

  Widget _buildAmbientNumberField({
    required String label,
    required int value,
    required ValueChanged<int> onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: TextFormField(
        key: ValueKey('ambient_$label$value'),
        initialValue: value.toString(),
        keyboardType: TextInputType.number,
        inputFormatters: [FilteringTextInputFormatter.digitsOnly],
        style: const TextStyle(color: Colors.white, fontSize: 14),
        decoration: InputDecoration(
          labelText: label,
          labelStyle: TextStyle(color: Colors.grey.shade400),
          filled: true,
          fillColor: const Color(0xFF2C2C2E),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
        ),
        onChanged: (text) {
          final parsed = int.tryParse(text);
          if (parsed != null && parsed > 0) onChanged(parsed);
        },
      ),
    );
  }

  Widget _buildAmbientSetupRow({
    required String title,
    required String subtitle,
    required bool complete,
    required VoidCallback? onPressed,
    String action = 'Enable',
  }) {
    final statusColor = complete ? const Color(0xFF22C55E) : const Color(0xFFF59E0B);
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: complete ? const Color(0xFF14532D) : const Color(0xFF3A2A12)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 30,
                height: 30,
                decoration: BoxDecoration(color: statusColor.withValues(alpha: 0.16), shape: BoxShape.circle),
                child: Icon(complete ? Icons.check : Icons.priority_high, color: statusColor, size: 16),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 2),
                    Text(subtitle, style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  complete ? 'Ready' : 'Needs setup',
                  style: TextStyle(color: statusColor, fontSize: 11, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          if (!complete && onPressed != null) ...[
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton(
                style: _ambientOutlineButtonStyle,
                onPressed: onPressed,
                child: Text(action),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildAmbientInstructionButton({
    required String label,
    required VoidCallback? onPressed,
    bool primary = false,
  }) {
    if (primary) {
      return ElevatedButton(style: _ambientPrimaryButtonStyle, onPressed: onPressed, child: Text(label));
    }
    return OutlinedButton(style: _ambientOutlineButtonStyle, onPressed: onPressed, child: Text(label));
  }

  Widget _buildAmbientControlButton({
    required String label,
    required VoidCallback? onPressed,
    ButtonStyle? style,
  }) {
    return ElevatedButton(style: style ?? _ambientPrimaryButtonStyle, onPressed: onPressed, child: Text(label));
  }

  Widget _buildAmbientDeleteButton({
    required String label,
    required VoidCallback? onPressed,
  }) {
    return OutlinedButton(
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(0xFFFCA5A5),
        disabledForegroundColor: Colors.grey.shade600,
        side: const BorderSide(color: Color(0xFF7F1D1D)),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
      onPressed: onPressed,
      child: Text(label),
    );
  }

  Widget _buildAmbientSyncButton({
    required String label,
    required VoidCallback? onPressed,
  }) {
    return OutlinedButton(
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(0xFF93C5FD),
        disabledForegroundColor: Colors.grey.shade600,
        side: const BorderSide(color: Color(0xFF1D4ED8)),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
      onPressed: onPressed,
      child: Text(label),
    );
  }

  Widget _buildAmbientSetupChecklist(AmbientCaptureProvider ambient) {
    final prefs = SharedPreferencesUtil();
    final wantsAccessibility =
        prefs.ambientCaptureAccessibilityModeEnabled || prefs.ambientCaptureCaptionFallbackEnabled;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: const Color(0xFF121214), borderRadius: BorderRadius.circular(10)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'Setup checklist',
                  style: TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                ),
              ),
              TextButton(
                style: _ambientTextButtonStyle,
                onPressed: _ambientSetupLoading ? null : _refreshAmbientSetupState,
                child: const Text('Refresh'),
              ),
            ],
          ),
          const SizedBox(height: 4),
          _buildAmbientSetupRow(
            title: 'Microphone',
            subtitle: 'Required for native Android phone-mic capture.',
            complete: _ambientMicGranted,
            onPressed: () async {
              await Permission.microphone.request();
              await _refreshAmbientSetupState();
            },
          ),
          _buildAmbientSetupRow(
            title: 'Notifications',
            subtitle: 'Required so the foreground microphone notification can stay visible.',
            complete: _ambientNotificationsGranted,
            onPressed: () async {
              await Permission.notification.request();
              await _refreshAmbientSetupState();
            },
          ),
          _buildAmbientSetupRow(
            title: 'Battery optimization',
            subtitle: 'Recommended so Android is less likely to kill long-running capture.',
            complete: _ambientBatteryExempt,
            onPressed: _requestAmbientBatteryOptimization,
          ),
          if (wantsAccessibility)
            _buildAmbientSetupRow(
              title: 'Accessibility service',
              subtitle: 'Optional. Only needed for foreground-app awareness and caption fallback.',
              complete: _ambientAccessibilityEnabled,
              action: 'Open',
              onPressed: () => _openAmbientAccessibilitySettings(ambient),
            ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _buildAmbientInstructionButton(
                label: _ambientSetupLoading ? 'Preparing...' : 'Prepare permissions and defaults',
                onPressed: _ambientSetupLoading ? null : () => _runAmbientSetup(),
                primary: true,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            prefs.ambientCaptureRawAudioUploadEnabled
                ? 'Full recording defaults are enabled: local WAL/spool, audio upload, text fallback, local STT, and caption fallback where Android permits.'
                : 'Upload for transcription is off. Capture can run, but conversations will stay local-only until upload/sync is enabled.',
            style: TextStyle(
              color: prefs.ambientCaptureRawAudioUploadEnabled ? Colors.greenAccent.shade100 : Colors.amber.shade200,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAmbientCaptureSection() {
    final prefs = SharedPreferencesUtil();
    return Consumer<AmbientCaptureProvider>(
      builder: (context, ambient, _) {
        final enabled = prefs.advancedAmbientCaptureEnabled;
        final capture = context.watch<CaptureProvider>();
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 32),
            _buildSectionHeader(
              'Advanced Ambient Capture',
              subtitle: 'Android-only experimental phone microphone capture. Disabled by default.',
            ),
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(14)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildExperimentalItem(
                    title: 'Master toggle',
                    description: 'Requires explicit local consent before native capture can start.',
                    icon: FontAwesomeIcons.microphone,
                    value: enabled,
                    onChanged: (v) async {
                      if (v) {
                        AmbientCaptureProvider.applyFullCoverageDefaults();
                      } else {
                        prefs.advancedAmbientCaptureEnabled = false;
                      }
                      if (!v && ambient.running) await ambient.stop();
                      await _refreshAmbientSetupState();
                      setState(() {});
                    },
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Current state: ${ambient.health.state.wireName}'
                    '${ambient.health.reason == null ? '' : ' (${ambient.health.reason})'}',
                    style: TextStyle(color: Colors.grey.shade300),
                  ),
                  if (prefs.ambientCapturePluginControlEnabled && prefs.ambientCapturePolicyUrl.isEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      'Plugin controller is enabled, but no controller is paired. Turn it off for local testing, or pair '
                      'a controller before relying on policy-driven capture.',
                      style: TextStyle(color: Colors.amber.shade200, fontSize: 12),
                    ),
                  ],
                  const SizedBox(height: 12),
                  _buildAmbientSetupChecklist(ambient),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _buildAmbientControlButton(
                        label: 'Start recording',
                        onPressed: enabled ? () => _startAmbientCapture(ambient) : null,
                        style: _ambientSuccessButtonStyle,
                      ),
                      _buildAmbientControlButton(label: 'Pause', onPressed: ambient.running ? ambient.pause : null),
                      _buildAmbientControlButton(
                        label: 'Stop',
                        onPressed: ambient.running ? ambient.stop : null,
                        style: _ambientDangerButtonStyle,
                      ),
                      _buildAmbientControlButton(
                        label: 'Private Mode',
                        onPressed: ambient.running ? ambient.enablePrivateMode : null,
                        style: _ambientDangerButtonStyle,
                      ),
                    ],
                  ),
                  const SizedBox(height: 18),
                  _buildAmbientDropdown(
                    label: 'Capture mode',
                    value: prefs.ambientCaptureMode,
                    values: const ['off', 'normal', 'aggressive', 'work_hours', 'meeting'],
                    onChanged: (v) {
                      if (v != null) prefs.ambientCaptureMode = v;
                      setState(() {});
                    },
                  ),
                  _buildAmbientDropdown(
                    label: 'Sensitivity',
                    value: prefs.ambientCaptureSensitivity,
                    values: const ['low', 'medium', 'high', 'custom'],
                    onChanged: (v) {
                      if (v != null) prefs.ambientCaptureSensitivity = v;
                      setState(() {});
                    },
                  ),
                  _buildAmbientDropdown(
                    label: 'Call / communication mode',
                    value: prefs.ambientCaptureCommunicationMode,
                    values: const ['off', 'detect_only', 'detect_and_attempt_mic', 'detect_and_caption_fallback'],
                    onChanged: (v) {
                      if (v != null) prefs.ambientCaptureCommunicationMode = v;
                      setState(() {});
                    },
                  ),
                  Text(
                    'Android may prevent call audio capture. This mode detects communication state and labels degraded '
                    'or fallback segments.',
                    style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                  ),
                  const SizedBox(height: 16),
                  SwitchListTile(
                    value: prefs.ambientCapturePluginControlEnabled,
                    onChanged: (v) => setState(() => prefs.ambientCapturePluginControlEnabled = v),
                    title: const Text('Plugin controller', style: TextStyle(color: Colors.white)),
                    subtitle: Text(ambient.policyStatus, style: TextStyle(color: Colors.grey.shade500)),
                    activeColor: const Color(0xFF22C55E),
                    contentPadding: EdgeInsets.zero,
                  ),
                  SwitchListTile(
                    value: prefs.ambientCaptureAccessibilityModeEnabled,
                    onChanged: (v) async {
                      prefs.ambientCaptureAccessibilityModeEnabled = v;
                      if (v && !_ambientAccessibilityEnabled) {
                        AppSnackbar.showSnackbar(
                          'Accessibility must be enabled in Android settings before it can be used.',
                          duration: const Duration(seconds: 4),
                        );
                        await _openAmbientAccessibilitySettings(ambient);
                      }
                      await _refreshAmbientSetupState();
                    },
                    title: const Text('Accessibility-enhanced mode', style: TextStyle(color: Colors.white)),
                    subtitle: Text(
                      'Optional foreground-app awareness. Caption text is only used when caption fallback is enabled.',
                      style: TextStyle(color: Colors.grey.shade500),
                    ),
                    activeColor: const Color(0xFF22C55E),
                    contentPadding: EdgeInsets.zero,
                  ),
                  SwitchListTile(
                    value: prefs.ambientCaptureTextFallbackEnabled,
                    onChanged: (v) => setState(() => prefs.ambientCaptureTextFallbackEnabled = v),
                    title: const Text('Text fallback queue', style: TextStyle(color: Colors.white)),
                    activeColor: const Color(0xFF22C55E),
                    contentPadding: EdgeInsets.zero,
                  ),
                  SwitchListTile(
                    value: prefs.ambientCaptureLocalSttFallbackEnabled,
                    onChanged: (v) => setState(() => prefs.ambientCaptureLocalSttFallbackEnabled = v),
                    title: const Text('Local STT fallback', style: TextStyle(color: Colors.white)),
                    activeColor: const Color(0xFF22C55E),
                    contentPadding: EdgeInsets.zero,
                  ),
                  SwitchListTile(
                    value: prefs.ambientCaptureCaptionFallbackEnabled,
                    onChanged: (v) async {
                      prefs.ambientCaptureCaptionFallbackEnabled = v;
                      if (v && !_ambientAccessibilityEnabled) {
                        AppSnackbar.showSnackbar(
                          'Caption fallback also requires enabling Omi in Android Accessibility settings.',
                          duration: const Duration(seconds: 4),
                        );
                        await _openAmbientAccessibilitySettings(ambient);
                      }
                      await _refreshAmbientSetupState();
                    },
                    title: const Text('Caption/accessibility fallback', style: TextStyle(color: Colors.white)),
                    activeColor: const Color(0xFF22C55E),
                    contentPadding: EdgeInsets.zero,
                  ),
                  SwitchListTile(
                    value: prefs.ambientCaptureRawAudioUploadEnabled,
                    onChanged: (v) => setState(() => prefs.ambientCaptureRawAudioUploadEnabled = v),
                    title: const Text('Upload audio for transcription', style: TextStyle(color: Colors.white)),
                    subtitle: Text(
                      'When off, audio remains queued locally and will not appear as normal conversations yet.',
                      style: TextStyle(color: Colors.grey.shade500),
                    ),
                    activeColor: const Color(0xFF22C55E),
                    contentPadding: EdgeInsets.zero,
                  ),
                  SwitchListTile(
                    value: prefs.ambientCaptureDeleteSyncedAudio,
                    onChanged: (v) => setState(() => prefs.ambientCaptureDeleteSyncedAudio = v),
                    title: const Text('Delete synced ambient audio', style: TextStyle(color: Colors.white)),
                    activeColor: const Color(0xFF22C55E),
                    contentPadding: EdgeInsets.zero,
                  ),
                  _buildAmbientDropdown(
                    label: 'Raw audio retention',
                    value: prefs.ambientCaptureRawAudioRetention,
                    values: const ['none', 'until_synced', '24h', '7d'],
                    onChanged: (v) {
                      if (v != null) prefs.ambientCaptureRawAudioRetention = v;
                      setState(() {});
                    },
                  ),
                  _buildAmbientNumberField(
                    label: 'Max ambient storage MB',
                    value: prefs.ambientCaptureMaxStorageMb,
                    onChanged: (v) => prefs.ambientCaptureMaxStorageMb = v,
                  ),
                  _buildAmbientNumberField(
                    label: 'Minimum free storage MB',
                    value: prefs.ambientCaptureMinFreeStorageMb,
                    onChanged: (v) => prefs.ambientCaptureMinFreeStorageMb = v,
                  ),
                  SwitchListTile(
                    value: prefs.ambientCaptureVerboseAuditEnabled,
                    onChanged: (v) => setState(() => prefs.ambientCaptureVerboseAuditEnabled = v),
                    title: const Text('Verbose audit log', style: TextStyle(color: Colors.white)),
                    activeColor: const Color(0xFF22C55E),
                    contentPadding: EdgeInsets.zero,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Storage: WAL queue ${capture.unsyncedSessionWals.length}, '
                    'in-flight ${capture.inFlightAudioSeconds}s, '
                    'native spool ${ambient.pendingSpoolCount} files '
                    '(${(ambient.spoolBytes / (1024 * 1024)).toStringAsFixed(1)} MB), '
                    'fallback text ${ambient.pendingFallbackCount}',
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 13),
                  ),
                  const SizedBox(height: 8),
                  LinearProgressIndicator(
                    value: (ambient.spoolBytes / (prefs.ambientCaptureMaxStorageMb * 1024 * 1024)).clamp(0.0, 1.0),
                    backgroundColor: const Color(0xFF2A2A2E),
                    valueColor: AlwaysStoppedAnimation<Color>(
                      ambient.health.state == AmbientCaptureHealthState.storageLimitReached
                          ? Colors.redAccent
                          : const Color(0xFF22C55E),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Quota ${prefs.ambientCaptureMaxStorageMb} MB, '
                    'minimum free ${prefs.ambientCaptureMinFreeStorageMb} MB',
                    style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    children: [
                      _buildAmbientDeleteButton(
                        label: 'Delete synced audio',
                        onPressed: () async {
                          ServiceManager.instance().wal.getSyncs().phone.deleteAllSyncedWals();
                          await ambient.deleteNativeSpool(status: 'synced');
                        },
                      ),
                      _buildAmbientDeleteButton(
                        label: 'Delete pending audio',
                        onPressed: () async {
                          ServiceManager.instance().wal.getSyncs().phone.deleteAllPendingWals();
                          await ambient.deleteNativeSpool(status: 'pending');
                        },
                      ),
                      _buildAmbientDeleteButton(
                        label: 'Delete all ambient audio',
                        onPressed: () {
                          ambient.deleteNativeSpool();
                        },
                      ),
                      _buildAmbientSyncButton(
                        label: 'Sync native spool',
                        onPressed: ambient.drainNativeSpool,
                      ),
                      _buildAmbientSyncButton(
                        label: 'Sync fallback text',
                        onPressed: ambient.drainFallbackQueue,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildApiKeysList(BuildContext context) {
    return Consumer<McpProvider>(
      builder: (context, provider, child) {
        if (provider.isLoading && provider.keys.isEmpty) {
          return Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(12)),
            child: const Center(child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)),
          );
        }
        if (provider.error != null) {
          return Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(12)),
            child: Center(
              child: Text('Error: ${provider.error}', style: TextStyle(color: Colors.red.shade300)),
            ),
          );
        }
        if (provider.keys.isEmpty) {
          return Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(12)),
            child: Column(
              children: [
                FaIcon(FontAwesomeIcons.key, color: Colors.grey.shade600, size: 28),
                const SizedBox(height: 12),
                Text(context.l10n.noApiKeysYet, style: TextStyle(color: Colors.grey.shade400, fontSize: 15)),
                const SizedBox(height: 4),
                Text(context.l10n.createKeyToGetStarted, style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
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
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text(
            context.l10n.docs,
            style: const TextStyle(color: Colors.black, fontWeight: FontWeight.w600, fontSize: 12),
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
        decoration: BoxDecoration(color: Colors.white.withOpacity(0.1), borderRadius: BorderRadius.circular(20)),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const FaIcon(FontAwesomeIcons.plus, color: Colors.white, size: 10),
            const SizedBox(width: 6),
            Text(
              context.l10n.createKey,
              style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w500),
            ),
          ],
        ),
      ),
    );
  }

  void _showApiSwitchDialog(BuildContext context, String targetEnvironment) {
    final targetName = targetEnvironment == 'production' ? context.l10n.production : context.l10n.staging;
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1C1C1E),
        title: Text(context.l10n.switchApiConfirmTitle, style: const TextStyle(color: Colors.white)),
        content: Text(context.l10n.switchApiConfirmBody(targetName), style: const TextStyle(color: Colors.white70)),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: Text(context.l10n.cancel, style: const TextStyle(color: Colors.grey)),
          ),
          TextButton(
            onPressed: () async {
              Navigator.of(ctx).pop();
              await SharedPreferencesUtil().saveString('testFlightApiEnvironment', targetEnvironment);
              AppSnackbar.showSnackbar(context.l10n.apiEnvSavedRestartRequired, duration: const Duration(seconds: 5));
            },
            child: Text(context.l10n.switchAndRestart, style: const TextStyle(color: Colors.orange)),
          ),
        ],
      ),
    );
  }

  Widget _buildManualFirmwareFlash(DeviceProvider provider) {
    return _buildSectionContainer(
      children: [
        GestureDetector(
          onTap: () async {
            final result = await FilePicker.platform.pickFiles(
              type: FileType.custom,
              allowedExtensions: ['zip'],
              dialogTitle: 'Select firmware ZIP file',
            );
            if (result == null || result.files.isEmpty) return;
            final file = result.files.first;
            if (file.path == null) return;

            if (!mounted) return;
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (context) => _ManualFirmwareFlashPage(
                  zipFilePath: file.path!,
                  fileName: file.name,
                  device: provider.pairedDevice!,
                ),
              ),
            );
          },
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
            child: Row(
              children: [
                const SizedBox(
                  width: 24,
                  height: 24,
                  child: Center(child: FaIcon(FontAwesomeIcons.microchip, color: Colors.white, size: 16)),
                ),
                const SizedBox(width: 14),
                const Expanded(
                  child: Text('Flash Custom Firmware', style: TextStyle(color: Colors.white, fontSize: 16)),
                ),
                Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 20),
              ],
            ),
          ),
        ),
      ],
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
              title: Text(
                context.l10n.developerSettings,
                style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
              ),
              centerTitle: true,
              actions: [
                TextButton(
                  onPressed: provider.savingSettingsLoading ? null : provider.saveSettings,
                  child: Text(
                    provider.savingSettingsLoading ? context.l10n.saving : context.l10n.save,
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
                  // Transcription Section
                  GestureDetector(
                    onTap: () async {
                      await Navigator.of(
                        context,
                      ).push(MaterialPageRoute(builder: (context) => const TranscriptionSettingsPage()));
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
                              child: FaIcon(FontAwesomeIcons.microphone, color: Colors.grey.shade400, size: 16),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  context.l10n.transcription,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  context.l10n.configureSttProvider,
                                  style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                                ),
                              ],
                            ),
                          ),
                          _buildSttChip(),
                          const SizedBox(width: 8),
                          FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 14),
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
                            child: Center(child: FaIcon(FontAwesomeIcons.clock, color: Colors.grey.shade400, size: 16)),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  context.l10n.conversationTimeout,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  context.l10n.setWhenConversationsAutoEnd,
                                  style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                                ),
                              ],
                            ),
                          ),
                          FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 14),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),

                  // Import Data Section
                  GestureDetector(
                    onTap: () {
                      Navigator.of(context).push(MaterialPageRoute(builder: (context) => const ImportHistoryPage()));
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
                              child: FaIcon(FontAwesomeIcons.fileImport, color: Colors.grey.shade400, size: 16),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  context.l10n.importData,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  context.l10n.importDataFromOtherSources,
                                  style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                                ),
                              ],
                            ),
                          ),
                          FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 14),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 32),

                  // Debug Logs Section
                  _buildSectionHeader(context.l10n.debugAndDiagnostics),
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(14)),
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
                              child: Center(child: FaIcon(FontAwesomeIcons.bug, color: Colors.grey.shade400, size: 16)),
                            ),
                            const SizedBox(width: 14),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    context.l10n.debugLogs,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    SharedPreferencesUtil().devLogsToFileEnabled
                                        ? context.l10n.autoDeletesAfterThreeDays
                                        : context.l10n.helpsDiagnoseIssues,
                                    style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
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
                                      AppSnackbar.showSnackbarError(context.l10n.noLogFilesFound);
                                      return;
                                    }
                                    if (files.length == 1) {
                                      final result = await Share.shareXFiles([
                                        XFile(files.first.path),
                                      ], text: 'Omi debug log');
                                      if (result.status == ShareResultStatus.success) {
                                        Logger.debug('Log shared');
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
                                              Padding(
                                                padding: const EdgeInsets.all(16),
                                                child: Text(
                                                  context.l10n.selectLogFile,
                                                  style: const TextStyle(
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
                                                      trailing: const FaIcon(
                                                        FontAwesomeIcons.chevronRight,
                                                        color: Color(0xFF3C3C43),
                                                        size: 14,
                                                      ),
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
                                      final result = await Share.shareXFiles([
                                        XFile(selected.path),
                                      ], text: 'Omi debug log');
                                      if (result.status == ShareResultStatus.success) {
                                        Logger.debug('Log shared');
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
                                          context.l10n.shareLogs,
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
                                  AppSnackbar.showSnackbar(context.l10n.debugLogCleared);
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
                                      Text(
                                        context.l10n.clear,
                                        style: const TextStyle(
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
                              SnackBar(
                                content: Text(context.l10n.exportStartedMayTakeFewSeconds),
                                duration: const Duration(seconds: 3),
                              ),
                            );
                            final directory = await getApplicationDocumentsDirectory();
                            final filePath = '${directory.path}/omi-export.json';
                            final exportedPath = await exportUserDataToFile(filePath);
                            if (exportedPath == null) {
                              if (context.mounted) {
                                ScaffoldMessenger.of(
                                  context,
                                ).showSnackBar(const SnackBar(content: Text('Export failed. Please try again.')));
                              }
                              setState(() => provider.loadingExportMemories = false);
                              return;
                            }

                            final result = await Share.shareXFiles([
                              XFile(exportedPath),
                            ], text: 'Exported Data from Omi');
                            if (result.status == ShareResultStatus.success) {
                              Logger.debug('Export shared');
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
                              child: FaIcon(FontAwesomeIcons.fileExport, color: Colors.grey.shade400, size: 16),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  context.l10n.exportAllData,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  context.l10n.exportConversationsToJson,
                                  style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                                ),
                              ],
                            ),
                          ),
                          if (provider.loadingExportMemories)
                            const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          else
                            FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade400, size: 16),
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
                          title: Text(
                            context.l10n.deleteKnowledgeGraphQuestion,
                            style: const TextStyle(color: Colors.white),
                          ),
                          content: Text(
                            context.l10n.knowledgeGraphDeleteDescription,
                            style: const TextStyle(color: Colors.white70),
                          ),
                          actions: [
                            TextButton(
                              onPressed: () => Navigator.of(ctx).pop(),
                              child: Text(context.l10n.cancel, style: const TextStyle(color: Colors.grey)),
                            ),
                            TextButton(
                              onPressed: () async {
                                Navigator.of(ctx).pop();
                                try {
                                  // Call delete endpoint
                                  await KnowledgeGraphApi.deleteKnowledgeGraph();
                                  AppSnackbar.showSnackbar(context.l10n.knowledgeGraphDeletedSuccessfully);
                                } catch (e) {
                                  AppSnackbar.showSnackbarError(context.l10n.failedToDeleteGraph(e.toString()));
                                }
                              },
                              child: Text(context.l10n.delete, style: const TextStyle(color: Colors.redAccent)),
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
                              child: FaIcon(FontAwesomeIcons.trash, color: Colors.redAccent.shade100, size: 16),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  context.l10n.deleteKnowledgeGraph,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  context.l10n.clearAllNodesAndConnections,
                                  style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                                ),
                              ],
                            ),
                          ),
                          FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 14),
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
                        Text(
                          context.l10n.mcp,
                          style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
                        ),
                        const Spacer(),
                        _buildDocsButton('https://docs.omi.me/doc/developer/MCP', 'MCP'),
                        const SizedBox(width: 8),
                        _buildCreateKeyButton(
                          () => showDialog(context: context, builder: (context) => const CreateMcpApiKeyDialog()),
                        ),
                      ],
                    ),
                  ),
                  _buildApiKeysList(context),

                  const SizedBox(height: 24),

                  // Claude Desktop Integration
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(14)),
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
                                  Text(
                                    context.l10n.claudeDesktop,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    context.l10n.addToClaudeDesktopConfig,
                                    style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
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
                              style: const TextStyle(fontFamily: 'Ubuntu Mono', fontSize: 11, height: 1.6),
                              children: [
                                const TextSpan(
                                  text: '{\n',
                                  style: TextStyle(color: Colors.white),
                                ),
                                const TextSpan(
                                  text: '  ',
                                  style: TextStyle(color: Colors.white),
                                ),
                                TextSpan(
                                  text: '"mcpServers"',
                                  style: TextStyle(color: Colors.cyan.shade300),
                                ),
                                const TextSpan(
                                  text: ': {\n',
                                  style: TextStyle(color: Colors.white),
                                ),
                                const TextSpan(
                                  text: '    ',
                                  style: TextStyle(color: Colors.white),
                                ),
                                TextSpan(
                                  text: '"omi"',
                                  style: TextStyle(color: Colors.cyan.shade300),
                                ),
                                const TextSpan(
                                  text: ': {\n',
                                  style: TextStyle(color: Colors.white),
                                ),
                                const TextSpan(
                                  text: '      ',
                                  style: TextStyle(color: Colors.white),
                                ),
                                TextSpan(
                                  text: '"command"',
                                  style: TextStyle(color: Colors.cyan.shade300),
                                ),
                                const TextSpan(
                                  text: ': ',
                                  style: TextStyle(color: Colors.white),
                                ),
                                TextSpan(
                                  text: '"docker"',
                                  style: TextStyle(color: Colors.orange.shade300),
                                ),
                                const TextSpan(
                                  text: ',\n',
                                  style: TextStyle(color: Colors.white),
                                ),
                                const TextSpan(
                                  text: '      ',
                                  style: TextStyle(color: Colors.white),
                                ),
                                TextSpan(
                                  text: '"args"',
                                  style: TextStyle(color: Colors.cyan.shade300),
                                ),
                                const TextSpan(
                                  text: ': [\n',
                                  style: TextStyle(color: Colors.white),
                                ),
                                const TextSpan(
                                  text: '        ',
                                  style: TextStyle(color: Colors.white),
                                ),
                                TextSpan(
                                  text: '"run"',
                                  style: TextStyle(color: Colors.orange.shade300),
                                ),
                                const TextSpan(
                                  text: ', ',
                                  style: TextStyle(color: Colors.white),
                                ),
                                TextSpan(
                                  text: '"--rm"',
                                  style: TextStyle(color: Colors.orange.shade300),
                                ),
                                const TextSpan(
                                  text: ', ',
                                  style: TextStyle(color: Colors.white),
                                ),
                                TextSpan(
                                  text: '"-i"',
                                  style: TextStyle(color: Colors.orange.shade300),
                                ),
                                const TextSpan(
                                  text: ', ',
                                  style: TextStyle(color: Colors.white),
                                ),
                                TextSpan(
                                  text: '"-e"',
                                  style: TextStyle(color: Colors.orange.shade300),
                                ),
                                const TextSpan(
                                  text: ',\n',
                                  style: TextStyle(color: Colors.white),
                                ),
                                const TextSpan(
                                  text: '        ',
                                  style: TextStyle(color: Colors.white),
                                ),
                                TextSpan(
                                  text: '"OMI_API_KEY=<your_key>"',
                                  style: TextStyle(color: Colors.orange.shade300),
                                ),
                                const TextSpan(
                                  text: ',\n',
                                  style: TextStyle(color: Colors.white),
                                ),
                                const TextSpan(
                                  text: '        ',
                                  style: TextStyle(color: Colors.white),
                                ),
                                TextSpan(
                                  text: '"omiai/mcp-server:latest"',
                                  style: TextStyle(color: Colors.orange.shade300),
                                ),
                                const TextSpan(
                                  text: '\n      ]\n    }\n  }\n}',
                                  style: TextStyle(color: Colors.white),
                                ),
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
                            AppSnackbar.showSnackbar(context.l10n.configCopiedToClipboard);
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
                                  context.l10n.copyConfig,
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
                    decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(14)),
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
                                  Text(
                                    context.l10n.mcpServer,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    context.l10n.connectAiAssistantsToYourData,
                                    style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 20),

                        // Server URL
                        Text(
                          context.l10n.serverUrl,
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 12, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 8),
                        Builder(
                          builder: (context) {
                            final mcpUrl = '${Env.apiBaseUrl}v1/mcp/sse';
                            return GestureDetector(
                              onTap: () {
                                Clipboard.setData(ClipboardData(text: mcpUrl));
                                AppSnackbar.showSnackbar(context.l10n.urlCopied);
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
                          context.l10n.apiKeyAuth,
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 12, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              flex: 2,
                              child: Text(
                                context.l10n.header,
                                style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                              ),
                            ),
                            Expanded(
                              flex: 3,
                              child: Text(
                                'Authorization: Bearer <key>',
                                style: TextStyle(color: Colors.grey.shade600, fontSize: 12, fontFamily: 'Ubuntu Mono'),
                              ),
                            ),
                          ],
                        ),

                        const SizedBox(height: 20),
                        Divider(color: Colors.grey.shade800, height: 1),
                        const SizedBox(height: 20),

                        // OAuth Section
                        Text(
                          context.l10n.oAuth,
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 12, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 12),

                        // Client ID
                        _buildMcpConfigRow(context.l10n.clientId, 'omi'),
                        const SizedBox(height: 8),

                        // Client Secret hint
                        Row(
                          children: [
                            Expanded(
                              flex: 2,
                              child: Text(
                                context.l10n.clientSecret,
                                style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                              ),
                            ),
                            Expanded(
                              flex: 3,
                              child: Text(
                                context.l10n.useYourMcpApiKey,
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
                        Text(
                          context.l10n.webhooks,
                          style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
                        ),
                        _buildDocsButton('https://docs.omi.me/doc/developer/apps/Introduction', 'Webhooks'),
                      ],
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(14)),
                    child: Column(
                      children: [
                        // Conversation Events
                        _buildWebhookItem(
                          title: context.l10n.conversationEvents,
                          description: context.l10n.newConversationCreated,
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
                          title: context.l10n.realTimeTranscript,
                          description: context.l10n.transcriptReceived,
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
                          title: context.l10n.audioBytes,
                          description: context.l10n.audioDataReceived,
                          icon: FontAwesomeIcons.waveSquare,
                          isEnabled: provider.audioBytesToggled,
                          onToggle: provider.onAudioBytesToggled,
                          controller: provider.webhookAudioBytes,
                          extraField: _buildTextField(
                            controller: provider.webhookAudioBytesDelay,
                            label: context.l10n.intervalSeconds,
                            keyboardType: TextInputType.number,
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        // Day Summary
                        _buildWebhookItem(
                          title: context.l10n.daySummary,
                          description: context.l10n.summaryGenerated,
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
                    child: Text(
                      context.l10n.experimental,
                      style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(14)),
                    child: Column(
                      children: [
                        // Transcription Diagnostics
                        _buildExperimentalItem(
                          title: context.l10n.transcriptionDiagnostics,
                          description: context.l10n.detailedDiagnosticMessages,
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
                          title: context.l10n.autoCreateSpeakers,
                          description: context.l10n.autoCreateWhenNameDetected,
                          icon: FontAwesomeIcons.userPlus,
                          value: provider.autoCreateSpeakersEnabled,
                          onChanged: provider.onAutoCreateSpeakersChanged,
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        // VAD Gate
                        _buildExperimentalItem(
                          title: 'VAD Gate',
                          description: 'Server-side voice gating to reduce STT costs',
                          icon: FontAwesomeIcons.microphoneSlash,
                          value: provider.vadGateEnabled,
                          onChanged: provider.onVadGateChanged,
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        // Claude Agent
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
                                child: FaIcon(FontAwesomeIcons.robot, color: Colors.grey.shade400, size: 16),
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
                                        'Omi Agent',
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
                                          color: Colors.purple.withOpacity(0.2),
                                          borderRadius: BorderRadius.circular(10),
                                        ),
                                        child: const Text(
                                          'BETA',
                                          style: TextStyle(
                                            color: Colors.purple,
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
                                    'Route chat through desktop agent VM',
                                    style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                                  ),
                                ],
                              ),
                            ),
                            if (provider.claudeAgentLoading)
                              const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                              )
                            else
                              Switch(
                                value: provider.claudeAgentEnabled,
                                onChanged: (v) => provider.onClaudeAgentChanged(v),
                                activeColor: const Color(0xFF22C55E),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),

                  _buildAmbientCaptureSection(),

                  // Home Screen Section
                  const SizedBox(height: 32),
                  const Padding(
                    padding: EdgeInsets.only(left: 4, right: 4, bottom: 12),
                    child: Text(
                      'Home Screen',
                      style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(14)),
                    child: Column(
                      children: [
                        _buildExperimentalItem(
                          title: context.l10n.goalTracker,
                          description: context.l10n.trackYourGoalsOnHomepage,
                          icon: FontAwesomeIcons.bullseye,
                          value: provider.showGoalTrackerEnabled,
                          onChanged: provider.onShowGoalTrackerChanged,
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        _buildExperimentalItem(
                          title: context.l10n.dailyScore,
                          description: context.l10n.showDailyScoreOnHomepage,
                          icon: FontAwesomeIcons.chartLine,
                          value: provider.showDailyScoreEnabled,
                          onChanged: provider.onShowDailyScoreChanged,
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        _buildExperimentalItem(
                          title: context.l10n.tasks,
                          description: context.l10n.showTasksOnHomepage,
                          icon: FontAwesomeIcons.listCheck,
                          value: provider.showTasksEnabled,
                          onChanged: provider.onShowTasksChanged,
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Divider(color: Colors.grey.shade800, height: 1),
                        ),
                        _buildExperimentalItem(
                          title: context.l10n.showPhoneCallButtonTitle,
                          description: context.l10n.showPhoneCallButtonDesc,
                          icon: FontAwesomeIcons.phone,
                          value: provider.showPhoneCallButton,
                          onChanged: provider.onShowPhoneCallButtonChanged,
                        ),
                      ],
                    ),
                  ),

                  // API Environment Section (TestFlight only, requires STAGING_API_URL env var)
                  if (Env.isTestFlight && Env.isStagingConfigured) ...[
                    const SizedBox(height: 32),
                    _buildSectionHeader(context.l10n.apiEnvironment, subtitle: context.l10n.apiEnvironmentDescription),
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1C1E),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            decoration: BoxDecoration(
                              color: const Color(0xFF2A2A2E),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Row(
                              children: [
                                Expanded(
                                  child: GestureDetector(
                                    onTap: () {
                                      if (!SharedPreferencesUtil().testFlightUseStagingApi) return;
                                      _showApiSwitchDialog(context, 'production');
                                    },
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(vertical: 12),
                                      decoration: BoxDecoration(
                                        color: !SharedPreferencesUtil().testFlightUseStagingApi
                                            ? const Color(0xFF22C55E)
                                            : Colors.transparent,
                                        borderRadius: BorderRadius.circular(10),
                                      ),
                                      child: Column(
                                        children: [
                                          Text(
                                            context.l10n.production,
                                            style: TextStyle(
                                              color: !SharedPreferencesUtil().testFlightUseStagingApi
                                                  ? Colors.white
                                                  : Colors.grey.shade400,
                                              fontSize: 14,
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                          const SizedBox(height: 2),
                                          Text(
                                            'api.omi.me',
                                            style: TextStyle(
                                              color: !SharedPreferencesUtil().testFlightUseStagingApi
                                                  ? Colors.white70
                                                  : Colors.grey.shade600,
                                              fontSize: 11,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                                Expanded(
                                  child: GestureDetector(
                                    onTap: () {
                                      if (SharedPreferencesUtil().testFlightUseStagingApi) return;
                                      _showApiSwitchDialog(context, 'staging');
                                    },
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(vertical: 12),
                                      decoration: BoxDecoration(
                                        color: SharedPreferencesUtil().testFlightUseStagingApi
                                            ? Colors.orange.shade800
                                            : Colors.transparent,
                                        borderRadius: BorderRadius.circular(10),
                                      ),
                                      child: Column(
                                        children: [
                                          Text(
                                            context.l10n.staging,
                                            style: TextStyle(
                                              color: SharedPreferencesUtil().testFlightUseStagingApi
                                                  ? Colors.white
                                                  : Colors.grey.shade400,
                                              fontSize: 14,
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                          const SizedBox(height: 2),
                                          Text(
                                            Uri.parse(Env.stagingApiUrl!).host,
                                            style: TextStyle(
                                              color: SharedPreferencesUtil().testFlightUseStagingApi
                                                  ? Colors.white70
                                                  : Colors.grey.shade600,
                                              fontSize: 11,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 8),
                          Row(
                            children: [
                              FaIcon(FontAwesomeIcons.circleInfo, color: Colors.grey.shade600, size: 12),
                              const SizedBox(width: 6),
                              Text(
                                context.l10n.switchRequiresRestart,
                                style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    if (SharedPreferencesUtil().testFlightUseStagingApi) ...[
                      const SizedBox(height: 8),
                      Container(
                        margin: const EdgeInsets.symmetric(horizontal: 4),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.orange.shade900.withValues(alpha: 0.3),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: Colors.orange.shade700.withValues(alpha: 0.5)),
                        ),
                        child: Row(
                          children: [
                            Icon(Icons.warning_amber_rounded, color: Colors.orange.shade300, size: 20),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                context.l10n.stagingDisclaimer,
                                style: TextStyle(color: Colors.orange.shade300, fontSize: 12),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],

                  // Manual Firmware Flash (only when device connected)
                  Builder(
                    builder: (context) {
                      final deviceProvider = context.watch<DeviceProvider>();
                      if (deviceProvider.isConnected && deviceProvider.pairedDevice != null) {
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const SizedBox(height: 24),
                            _buildSectionHeader('Firmware', subtitle: 'Flash custom firmware builds'),
                            const SizedBox(height: 8),
                            _buildManualFirmwareFlash(deviceProvider),
                          ],
                        );
                      }
                      return const SizedBox.shrink();
                    },
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

// ============================================================
// Manual Firmware Flash Page
// ============================================================

class _ManualFirmwareFlashPage extends StatefulWidget {
  final String zipFilePath;
  final String fileName;
  final BtDevice device;

  const _ManualFirmwareFlashPage({required this.zipFilePath, required this.fileName, required this.device});

  @override
  State<_ManualFirmwareFlashPage> createState() => _ManualFirmwareFlashPageState();
}

class _ManualFirmwareFlashPageState extends State<_ManualFirmwareFlashPage> with FirmwareMixin {
  bool _confirmed = false;
  String? _error;

  @override
  void initState() {
    super.initState();
  }

  @override
  void dispose() {
    killMcuUpdateManager();
    super.dispose();
  }

  Future<void> _startFlash() async {
    setState(() {
      _confirmed = true;
      _error = null;
    });
    try {
      // Manual flash always uses MCU DFU — modern firmware ZIPs contain
      // manifest.json which NordicDfu (legacy) cannot parse.
      await startMCUDfu(widget.device, zipFilePath: widget.zipFilePath);
    } catch (e) {
      if (mounted) {
        setState(() => _error = e.toString());
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        title: const Text('Flash Firmware', style: TextStyle(color: Colors.white)),
        iconTheme: const IconThemeData(color: Colors.white),
        elevation: 0,
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // File info
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(12)),
              child: Row(
                children: [
                  const FaIcon(FontAwesomeIcons.file, color: Colors.deepPurple, size: 20),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          widget.fileName,
                          style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Target: ${widget.device.name}',
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // Warning
            if (!_confirmed) ...[
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.orange.shade900.withValues(alpha: 0.3),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.orange.shade700.withValues(alpha: 0.5)),
                ),
                child: Row(
                  children: [
                    Icon(Icons.warning_amber_rounded, color: Colors.orange.shade300, size: 24),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Flashing custom firmware can brick your device. Make sure this is a valid Omi firmware build. Do not disconnect during the update.',
                        style: TextStyle(color: Colors.orange.shade300, fontSize: 13),
                      ),
                    ),
                  ],
                ),
              ),
              const Spacer(),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: ElevatedButton(
                  onPressed: _startFlash,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.deepPurple,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  child: const Text(
                    'Flash Firmware',
                    style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            ],

            // Progress
            if (_confirmed && !isInstalled) ...[
              const SizedBox(height: 16),
              Text(
                isInstalling ? 'Installing...' : 'Preparing...',
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 16),
              LinearProgressIndicator(
                value: installProgress / 100,
                backgroundColor: const Color(0xFF2A2A2E),
                valueColor: const AlwaysStoppedAnimation<Color>(Colors.deepPurple),
                minHeight: 8,
                borderRadius: BorderRadius.circular(4),
              ),
              const SizedBox(height: 8),
              Text('${installProgress}%', style: TextStyle(color: Colors.grey.shade400, fontSize: 14)),
            ],

            // Success
            if (isInstalled) ...[
              const SizedBox(height: 32),
              const Center(
                child: Column(
                  children: [
                    Icon(Icons.check_circle, color: Colors.green, size: 64),
                    SizedBox(height: 16),
                    Text(
                      'Firmware flashed successfully!',
                      style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                    ),
                    SizedBox(height: 8),
                    Text('Your device will restart.', style: TextStyle(color: Colors.grey, fontSize: 14)),
                  ],
                ),
              ),
            ],

            // Error
            if (_error != null) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.red.shade900.withValues(alpha: 0.3),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(_error!, style: TextStyle(color: Colors.red.shade300, fontSize: 13)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

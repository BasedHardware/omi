import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/pages/settings/widgets/live_activity_settings.dart';

class NotificationsSettingsPage extends StatefulWidget {
  const NotificationsSettingsPage({super.key});

  @override
  State<NotificationsSettingsPage> createState() => _NotificationsSettingsPageState();
}

class NotificationsSettingsLoadingShimmer extends StatelessWidget {
  const NotificationsSettingsLoadingShimmer({super.key});

  @override
  Widget build(BuildContext context) {
    final placeholderColor = OmiColors.surface2;

    Widget placeholder({required double height, double? width, BorderRadius radius = OmiRadius.smAll}) {
      return Container(
        width: width,
        height: height,
        decoration: BoxDecoration(color: placeholderColor, borderRadius: radius),
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: ShimmerWithTimeout(
        baseColor: placeholderColor,
        highlightColor: OmiColors.surface3,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            placeholder(width: 190, height: 24),
            const SizedBox(height: 12),
            placeholder(height: 14),
            const SizedBox(height: 8),
            placeholder(width: 250, height: 14),
            const SizedBox(height: 16),
            placeholder(height: 172, radius: OmiRadius.lgAll),
            const SizedBox(height: 32),
            placeholder(width: 150, height: 24),
            const SizedBox(height: 12),
            placeholder(height: 14),
            const SizedBox(height: 8),
            placeholder(width: 220, height: 14),
            const SizedBox(height: 16),
            placeholder(height: 145, radius: OmiRadius.lgAll),
          ],
        ),
      ),
    );
  }
}

class _NotificationsSettingsPageState extends State<NotificationsSettingsPage> with WidgetsBindingObserver {
  bool _isLoading = true;

  /// Whether the phone lets Omi notify at all (v2 Notifications: "iPhone notifications").
  OmiPermissionStatus? _permission;

  // Notification frequency (0-5), default 0 (disabled)
  int _notificationFrequency = 0;
  int _savedNotificationFrequency = 0;

  // Daily Summary settings
  bool _dailySummaryEnabled = true;
  int _dailySummaryHour = 22; // Default to 10 PM

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadSettings();
    _loadPermission();
    PlatformManager.instance.analytics.dailySummarySettingsOpened();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  /// Back from the Settings app: the reader may have changed the permission there.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _loadPermission();
  }

  Future<void> _loadPermission() async {
    OmiPermissionStatus? status;
    try {
      status = OmiPermissionStatus.fromStatus(await Permission.notification.status);
    } catch (_) {
      // No permission plugin (tests, unsupported platforms): the row stays hidden.
    }
    if (mounted) setState(() => _permission = status);
  }

  Future<void> _requestPermission() async {
    try {
      final status = await Permission.notification.request();
      if (mounted) setState(() => _permission = OmiPermissionStatus.fromStatus(status));
    } catch (_) {}
  }

  Future<void> _loadSettings() async {
    // Load Daily Summary settings from API
    final settings = await getDailySummarySettings();

    // Load Mentor Notification settings from API
    final mentorSettings = await getMentorNotificationSettings();

    // Load settings from local prefs
    final localFrequency = SharedPreferencesUtil().notificationFrequency;

    if (mounted) {
      setState(() {
        if (settings != null) {
          _dailySummaryEnabled = settings.enabled;
          _dailySummaryHour = settings.hour;
        }
        // Use backend value if available, otherwise use local
        _notificationFrequency = mentorSettings?.frequency ?? localFrequency;
        _savedNotificationFrequency = _notificationFrequency;
        // Sync local with backend
        if (mentorSettings != null) {
          SharedPreferencesUtil().notificationFrequency = mentorSettings.frequency;
        }
        _isLoading = false;
      });
    }
  }

  Future<void> _updateNotificationFrequency(int value) async {
    PlatformManager.instance.analytics.notificationFrequencyChanged(
      oldFrequency: _notificationFrequency,
      newFrequency: value,
    );
    setState(() => _notificationFrequency = value);
    SharedPreferencesUtil().notificationFrequency = value;
    final saved = await setMentorNotificationSettings(value);
    if (saved) {
      _savedNotificationFrequency = value;
    } else if (mounted && _notificationFrequency == value) {
      setState(() => _notificationFrequency = _savedNotificationFrequency);
      SharedPreferencesUtil().notificationFrequency = _savedNotificationFrequency;
    }
  }

  String _getFrequencyLabel(BuildContext context, int value) {
    switch (value) {
      case 0:
        return context.l10n.frequencyOff;
      case 1:
        return context.l10n.frequencyMinimal;
      case 2:
        return context.l10n.frequencyLow;
      case 3:
        return context.l10n.frequencyBalanced;
      case 4:
        return context.l10n.frequencyHigh;
      case 5:
        return context.l10n.frequencyMaximum;
      default:
        return context.l10n.frequencyBalanced;
    }
  }

  String _getFrequencyDescription(BuildContext context, int value) {
    switch (value) {
      case 0:
        return context.l10n.frequencyDescOff;
      case 1:
        return context.l10n.frequencyDescMinimal;
      case 2:
        return context.l10n.frequencyDescLow;
      case 3:
        return context.l10n.frequencyDescBalanced;
      case 4:
        return context.l10n.frequencyDescHigh;
      case 5:
        return context.l10n.frequencyDescMaximum;
      default:
        return context.l10n.frequencyDescBalanced;
    }
  }

  /// The hour in the reader's locale and clock ("10:00 PM", "22:00").
  String _formatHourDisplay(BuildContext context, int hour) =>
      OmiDateFormat.of(context).time(DateTime(2000, 1, 1, hour));

  Future<void> _updateDailySummaryEnabled(bool value) async {
    final previous = _dailySummaryEnabled;
    setState(() => _dailySummaryEnabled = value);
    if (!await setDailySummarySettings(enabled: value)) {
      if (mounted) setState(() => _dailySummaryEnabled = previous);
      return;
    }
    PlatformManager.instance.analytics.dailySummaryToggled(enabled: value);
  }

  Future<void> _updateDailySummaryHour(int hour) async {
    final previous = _dailySummaryHour;
    setState(() => _dailySummaryHour = hour);
    if (!await setDailySummarySettings(hour: hour)) {
      if (mounted) setState(() => _dailySummaryHour = previous);
      return;
    }
    PlatformManager.instance.analytics.dailySummaryTimeChanged(hour: hour);
  }

  Future<void> _showHourPicker() async {
    if (!_dailySummaryEnabled) return;

    int tempHour = _dailySummaryHour;
    final picked = await showOmiSheet<int>(
      context: context,
      title: context.l10n.selectTime,
      builder: (sheetContext) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: 216,
            child: CupertinoTheme(
              data: const CupertinoThemeData(brightness: Brightness.dark),
              child: CupertinoPicker(
                scrollController: FixedExtentScrollController(initialItem: tempHour),
                itemExtent: 44,
                onSelectedItemChanged: (index) => tempHour = index,
                children: List.generate(
                  24,
                  (index) => Center(child: Text(_formatHourDisplay(sheetContext, index), style: OmiType.title3)),
                ),
              ),
            ),
          ),
          const SizedBox(height: OmiSpacing.md),
          OmiButton(label: context.l10n.done, expand: true, onPressed: () => Navigator.of(sheetContext).pop(tempHour)),
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
    if (picked != null && picked != _dailySummaryHour) await _updateDailySummaryHour(picked);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: OmiAppBar(leading: const OmiBackButton(), title: Text(context.l10n.notifications)),
      body: Column(children: [
        const LiveActivitySettings(),
        Expanded(
            child: _isLoading
                ? const NotificationsSettingsLoadingShimmer()
                : ListView(
                    padding: const EdgeInsets.all(OmiSpacing.md),
                    children: [
                      if (_permission != null) ...[
                        OmiSettingsGroup(
                          children: [
                            OmiPermissionRow(
                              key: const Key('notifications_permission_row'),
                              inGroup: true,
                              icon: Icons.notifications_none,
                              title: context.l10n.notifications,
                              reason: context.l10n.notificationsDesc,
                              status: _permission!,
                              onAllow: _requestPermission,
                            ),
                          ],
                        ),
                        const SizedBox(height: OmiSpacing.xxl),
                      ],
                      _buildFrequencyGroup(),
                      const SizedBox(height: OmiSpacing.xxl),
                      _buildDailySummaryGroup(),
                    ],
                  )),
      ]),
    );
  }

  /// v2 Notifications "How often": the six levels as a list, the current one ticked.
  Widget _buildFrequencyGroup() {
    return OmiSettingsGroup(
      header: context.l10n.notificationFrequency,
      headerSubtitle: context.l10n.notificationFrequencyDescription,
      children: [
        for (var level = 0; level <= 5; level++)
          Semantics(
            key: ValueKey('notification_frequency_$level'),
            selected: level == _notificationFrequency,
            inMutuallyExclusiveGroup: true,
            child: OmiSettingsRow(
              title: _getFrequencyLabel(context, level),
              subtitle: _getFrequencyDescription(context, level),
              showChevron: false,
              trailing: level == _notificationFrequency
                  ? Icon(Icons.check_rounded, size: 20, color: OmiColors.textPrimary)
                  : const SizedBox(width: 20),
              onTap: level == _notificationFrequency
                  ? null
                  : () {
                      OmiHaptics.selection();
                      _updateNotificationFrequency(level);
                    },
            ),
          ),
      ],
    );
  }

  Widget _buildDailySummaryGroup() {
    return OmiSettingsGroup(
      header: context.l10n.dailySummary,
      headerSubtitle: context.l10n.dailySummaryDescription,
      children: [
        OmiSettingsRow.toggle(
          leading: const FaIcon(FontAwesomeIcons.bell),
          title: context.l10n.enable,
          value: _dailySummaryEnabled,
          onChanged: _updateDailySummaryEnabled,
        ),
        AnimatedOpacity(
          opacity: _dailySummaryEnabled ? 1.0 : 0.4,
          duration: OmiMotion.of(context).standard,
          child: OmiSettingsRow(
            leading: const FaIcon(FontAwesomeIcons.clock),
            title: context.l10n.deliveryTime,
            value: _formatHourDisplay(context, _dailySummaryHour),
            showChevron: true,
            onTap: _dailySummaryEnabled ? _showHourPicker : null,
          ),
        ),
      ],
    );
  }
}

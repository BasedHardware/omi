import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/pages/settings/widgets/plans/contextual_plans.dart';
import 'package:omi/pages/settings/widgets/live_activity_settings.dart';
import 'package:omi/pages/conversations/widgets/daily_recap_recovery_action.dart';

/// The server reads and writes behind the page; tests replace them.
class NotificationSettingsApi {
  const NotificationSettingsApi();

  Future<DailySummarySettings?> dailySummary() => getDailySummarySettings();
  Future<MentorNotificationSettings?> mentor() => getMentorNotificationSettings();
  Future<bool> setDailySummary({bool? enabled, int? hour}) => setDailySummarySettings(enabled: enabled, hour: hour);
  Future<bool> setMentorFrequency(int frequency) => setMentorNotificationSettings(frequency);
}

class NotificationsSettingsPage extends StatefulWidget {
  const NotificationsSettingsPage(
      {super.key, this.api = const NotificationSettingsApi(), this.showLiveActivity = true});

  final NotificationSettingsApi api;

  /// The Live Activity row is a platform surface; tests leave it out.
  final bool showLiveActivity;

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

class _NotificationsSettingsPageState extends State<NotificationsSettingsPage> {
  bool _isLoading = true;

  // Notification frequency (0-5), default 0 (disabled)
  int _notificationFrequency = 0;
  int _savedNotificationFrequency = 0;

  // Daily Summary settings
  bool _dailySummaryEnabled = true;
  int _dailySummaryHour = 22; // Default to 10 PM

  @override
  void initState() {
    super.initState();
    _loadSettings();
    PlatformManager.instance.analytics.dailySummarySettingsOpened();
  }

  /// The server's settings could not be read: the page says so with Try Again instead of showing
  /// defaults as if they were the reader's choices (P4), and no change can overwrite them blind.
  bool _loadFailed = false;

  Future<void> _loadSettings() async {
    if (mounted && _loadFailed) {
      setState(() {
        _loadFailed = false;
        _isLoading = true;
      });
    }
    Future<T?> read<T>(Future<T?> Function() load) async {
      try {
        return await load();
      } catch (_) {
        return null;
      }
    }

    final settings = await read(widget.api.dailySummary);
    final mentorSettings = await read(widget.api.mentor);

    // Load settings from local prefs
    final localFrequency = SharedPreferencesUtil().notificationFrequency;

    if (mounted) {
      setState(() {
        _loadFailed = settings == null || mentorSettings == null;
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
    if (value > 0 &&
        _notificationFrequency == 0 &&
        await showProGateUpsell(
          context,
          feature: 'proactive_agent',
          source: 'proactive_agent_gate',
        )) {
      return;
    }
    if (!mounted) return;
    PlatformManager.instance.analytics.notificationFrequencyChanged(
      oldFrequency: _notificationFrequency,
      newFrequency: value,
    );
    final saved = await applyOmiSetting<int>(
      context,
      setting: 'mentor_frequency',
      previous: _savedNotificationFrequency,
      next: value,
      show: (frequency) {
        if (mounted) setState(() => _notificationFrequency = frequency);
        SharedPreferencesUtil().notificationFrequency = frequency;
      },
      save: widget.api.setMentorFrequency,
    );
    if (saved) _savedNotificationFrequency = value;
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
    final saved = await applyOmiSetting<bool>(
      context,
      setting: 'daily_summary_enabled',
      previous: _dailySummaryEnabled,
      next: value,
      show: (enabled) {
        if (mounted) setState(() => _dailySummaryEnabled = enabled);
      },
      save: (enabled) => widget.api.setDailySummary(enabled: enabled),
    );
    if (saved) PlatformManager.instance.analytics.dailySummaryToggled(enabled: value);
  }

  Future<void> _updateDailySummaryHour(int hour) async {
    final saved = await applyOmiSetting<int>(
      context,
      setting: 'daily_summary_hour',
      previous: _dailySummaryHour,
      next: hour,
      show: (value) {
        if (mounted) setState(() => _dailySummaryHour = value);
      },
      save: (value) => widget.api.setDailySummary(hour: value),
    );
    if (saved) PlatformManager.instance.analytics.dailySummaryTimeChanged(hour: hour);
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
              data: CupertinoThemeData(brightness: Theme.of(sheetContext).brightness),
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
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.notifications)),
      body: Column(
        children: [
          if (widget.showLiveActivity) const LiveActivitySettings(),
          Expanded(
            child: _isLoading
                ? const NotificationsSettingsLoadingShimmer()
                : _loadFailed
                    ? OmiErrorState(
                        key: const Key('notification_settings_load_failed'),
                        message: context.l10n.couldNotLoadNotificationSettings,
                        onRetry: _loadSettings,
                      )
                    : ListView(
                        padding: const EdgeInsets.all(OmiSpacing.md),
                        children: [
                          OmiSectionHeader(
                            context.l10n.notificationFrequency,
                            subtitle: context.l10n.notificationFrequencyDescription,
                          ),
                          _buildFrequencyCard(),
                          const SizedBox(height: OmiSpacing.xxl),
                          _buildDailySummaryGroup(),
                        ],
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildFrequencyCard() {
    final isOff = _notificationFrequency == 0;
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.lg),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // One value label: the level's name, plus what it means once it is on.
          Text(_getFrequencyLabel(context, _notificationFrequency), style: OmiType.headline),
          if (!isOff) ...[
            const SizedBox(height: OmiSpacing.xxs),
            Text(
              _getFrequencyDescription(context, _notificationFrequency),
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            ),
          ],
          const SizedBox(height: OmiSpacing.sm),
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: OmiColors.accent,
              inactiveTrackColor: OmiColors.surface3,
              thumbColor: OmiColors.accent,
              overlayColor: OmiColors.accent.withValues(alpha: 0.12),
              trackHeight: 6,
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 10),
            ),
            child: Slider(
              value: _notificationFrequency.toDouble(),
              min: 0,
              max: 5,
              divisions: 5,
              label: _getFrequencyLabel(context, _notificationFrequency),
              semanticFormatterCallback: (value) => _getFrequencyLabel(context, value.round()),
              onChanged: (value) => _updateNotificationFrequency(value.round()),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDailySummaryGroup() {
    // The toggle row names the feature, so the group needs no header or explainer of its own.
    return OmiSettingsGroup(
      children: [
        OmiSettingsRow.toggle(
          key: const Key('daily_summary_toggle'),
          leading: const FaIcon(FontAwesomeIcons.bell),
          title: context.l10n.dailySummary,
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
        const DailyRecapRecoveryAction(settingsRow: true),
      ],
    );
  }
}

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/calendar_provider.dart';
import 'package:omi/services/calendar_service.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class CalendarSettingsPage extends StatefulWidget {
  const CalendarSettingsPage({super.key});

  @override
  State<CalendarSettingsPage> createState() => _CalendarSettingsPageState();
}

class _CalendarSettingsPageState extends State<CalendarSettingsPage> {
  bool _showMenuBarMeetings = true;
  bool _showEventsWithNoParticipants = false;
  Set<String> _enabledCalendarIds = {};

  @override
  void initState() {
    super.initState();

    // Load saved settings
    _showMenuBarMeetings = SharedPreferencesUtil().showMeetingsInMenuBar;
    _showEventsWithNoParticipants = SharedPreferencesUtil().showEventsWithNoParticipants;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = Provider.of<CalendarProvider>(context, listen: false);
      if (provider.isAuthorized) {
        provider.fetchSystemCalendars();
        // Enable all calendars by default if none are saved
        final savedIds = SharedPreferencesUtil().enabledCalendarIds;
        setState(() {
          if (savedIds.isEmpty && provider.systemCalendars.isNotEmpty) {
            _enabledCalendarIds = provider.systemCalendars.map((c) => c.id).toSet();
            SharedPreferencesUtil().enabledCalendarIds = _enabledCalendarIds.toList();
          } else {
            _enabledCalendarIds = savedIds.toSet();
          }
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ResponsiveHelper.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: ResponsiveHelper.backgroundPrimary,
        elevation: 0,
        title: Text(
          context.l10n.calendarSettings,
          style: const TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: ResponsiveHelper.textPrimary),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Consumer<CalendarProvider>(
        builder: (context, provider, child) {
          return ListView(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
            children: [
              // Calendar Providers Section
              _buildSectionHeader(context.l10n.calendarProviders),
              const SizedBox(height: 12),
              _buildCalendarProviderCard(
                context,
                icon: FontAwesomeIcons.calendar,
                iconColor: const Color(0xFF5AC8FA),
                title: context.l10n.macOsCalendar,
                description: context.l10n.connectMacOsCalendar,
                isEnabled: provider.isAuthorized && provider.isMonitoring,
                onToggle: (value) async {
                  if (value) {
                    // If already authorized, just start monitoring
                    if (provider.isAuthorized) {
                      SharedPreferencesUtil().calendarIntegrationEnabled = true;
                      await provider.startMonitoring();
                    } else {
                      // Otherwise request permission first
                      await provider.requestPermission();
                    }
                  } else {
                    await provider.stopMonitoring();
                  }
                },
              ),
              const SizedBox(height: 8),
              _buildCalendarProviderCard(
                context,
                icon: FontAwesomeIcons.google,
                iconColor: const Color(0xFF4285F4),
                title: context.l10n.googleCalendar,
                description: context.l10n.syncGoogleAccount,
                isEnabled: false,
                onToggle: (value) {
                  _showComingSoonToast(context);
                },
              ),

              const SizedBox(height: 24),

              // Settings Section
              _buildSettingsCard(context, [
                _buildSettingItem(
                  icon: FontAwesomeIcons.clock,
                  iconColor: ResponsiveHelper.textSecondary,
                  title: context.l10n.showMeetingsMenuBar,
                  description: context.l10n.showMeetingsMenuBarDesc,
                  value: _showMenuBarMeetings,
                  onChanged: (value) {
                    setState(() => _showMenuBarMeetings = value);
                    provider.updateShowMeetingsInMenuBar(value);
                  },
                ),
                const Divider(
                  height: 1,
                  thickness: 1,
                  color: ResponsiveHelper.backgroundTertiary,
                ),
                _buildSettingItem(
                  icon: FontAwesomeIcons.calendarDay,
                  iconColor: ResponsiveHelper.textSecondary,
                  title: context.l10n.showEventsNoParticipants,
                  description: context.l10n.showEventsNoParticipantsDesc,
                  value: _showEventsWithNoParticipants,
                  onChanged: (value) {
                    setState(() => _showEventsWithNoParticipants = value);
                    provider.updateShowEventsWithNoParticipants(value);
                  },
                ),
              ]),

              const SizedBox(height: 24),

              // Your Meetings Section
              if (provider.isAuthorized) ...[
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    _buildSectionHeader(context.l10n.yourMeetings),
                    if (provider.upcomingMeetings.isNotEmpty)
                      TextButton(
                        onPressed: () => provider.refreshMeetings(),
                        style: TextButton.styleFrom(
                          padding: EdgeInsets.zero,
                          minimumSize: Size.zero,
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        ),
                        child: Text(
                          context.l10n.refresh,
                          style: const TextStyle(
                            color: ResponsiveHelper.purplePrimary,
                            fontSize: 13,
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 12),
                _buildMeetingsList(provider),
              ],
            ],
          );
        },
      ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Text(
      title,
      style: const TextStyle(
        color: ResponsiveHelper.textPrimary,
        fontSize: 16,
        fontWeight: FontWeight.w600,
      ),
    );
  }

  Widget _buildCalendarProviderCard(
    BuildContext context, {
    required IconData icon,
    required Color iconColor,
    required String title,
    required String description,
    required bool isEnabled,
    required ValueChanged<bool> onToggle,
  }) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: iconColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              icon,
              color: iconColor,
              size: 16,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  description,
                  style: const TextStyle(
                    color: ResponsiveHelper.textSecondary,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Transform.scale(
            scale: 0.8,
            child: CupertinoSwitch(
              value: isEnabled,
              onChanged: onToggle,
              activeColor: ResponsiveHelper.purplePrimary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSettingsCard(BuildContext context, List<Widget> children) {
    return Container(
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: Column(
        children: children,
      ),
    );
  }

  Widget _buildSettingItem({
    required IconData icon,
    required Color iconColor,
    required String title,
    required String description,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: iconColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              icon,
              color: iconColor,
              size: 16,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  description,
                  style: const TextStyle(
                    color: ResponsiveHelper.textSecondary,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Transform.scale(
            scale: 0.8,
            child: CupertinoSwitch(
              value: value,
              onChanged: onChanged,
              activeColor: ResponsiveHelper.purplePrimary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCalendarsCard(CalendarProvider provider) {
    return Container(
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: ListView.separated(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        itemCount: provider.systemCalendars.length,
        separatorBuilder: (context, index) => const Divider(
          height: 1,
          thickness: 1,
          color: ResponsiveHelper.backgroundTertiary,
          indent: 50,
        ),
        itemBuilder: (context, index) {
          final calendar = provider.systemCalendars[index];
          final isEnabled = _enabledCalendarIds.contains(calendar.id);

          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(
              children: [
                // Color indicator
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: calendar.color ?? ResponsiveHelper.purplePrimary,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 12),
                // Calendar title
                Expanded(
                  child: Text(
                    calendar.title,
                    style: const TextStyle(
                      color: ResponsiveHelper.textPrimary,
                      fontSize: 14,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                // Toggle
                Transform.scale(
                  scale: 0.8,
                  child: CupertinoSwitch(
                    value: isEnabled,
                    onChanged: (value) {
                      setState(() {
                        if (value) {
                          _enabledCalendarIds.add(calendar.id);
                        } else {
                          _enabledCalendarIds.remove(calendar.id);
                        }
                        SharedPreferencesUtil().enabledCalendarIds = _enabledCalendarIds.toList();
                      });
                    },
                    activeColor: ResponsiveHelper.purplePrimary,
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildMeetingsList(CalendarProvider provider) {
    if (provider.upcomingMeetings.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(32),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.4),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
            width: 1,
          ),
        ),
        child: Column(
          children: [
            const Icon(
              Icons.event_busy,
              color: ResponsiveHelper.textTertiary,
              size: 40,
            ),
            const SizedBox(height: 12),
            Text(
              context.l10n.noUpcomingMeetings,
              style: const TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              context.l10n.checkingNextDays,
              style: const TextStyle(
                color: ResponsiveHelper.textTertiary,
                fontSize: 12,
              ),
            ),
          ],
        ),
      );
    }

    // Sort meetings by start time
    final sortedMeetings = List<CalendarMeeting>.from(provider.upcomingMeetings)
      ..sort((a, b) => a.startTime.compareTo(b.startTime));

    // Group meetings by date
    final groupedMeetings = <DateTime, List<CalendarMeeting>>{};
    for (final meeting in sortedMeetings) {
      final dateKey = DateTime(meeting.startTime.year, meeting.startTime.month, meeting.startTime.day);
      groupedMeetings.putIfAbsent(dateKey, () => []).add(meeting);
    }

    // Build list with date headers
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: groupedMeetings.entries.map((entry) {
        final date = entry.key;
        final meetings = entry.value;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Date header
            Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 8, top: 12),
              child: Text(
                _formatDateHeader(date),
                style: const TextStyle(
                  color: ResponsiveHelper.textSecondary,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            // Meetings for this date
            Container(
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.4),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                  width: 1,
                ),
              ),
              child: ListView.separated(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: meetings.length,
                separatorBuilder: (context, index) => const Divider(
                  height: 1,
                  thickness: 1,
                  color: ResponsiveHelper.backgroundTertiary,
                  indent: 14,
                  endIndent: 14,
                ),
                itemBuilder: (context, index) {
                  return _buildMeetingCard(meetings[index]);
                },
              ),
            ),
          ],
        );
      }).toList(),
    );
  }

  String _formatDateHeader(DateTime date) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final tomorrow = today.add(const Duration(days: 1));

    if (date == today) {
      return context.l10n.today;
    } else if (date == tomorrow) {
      return context.l10n.tomorrow;
    } else {
      // Show full date for other days
      return DateFormat('EEEE, MMMM d').format(date);
    }
  }

  Widget _buildMeetingCard(CalendarMeeting meeting) {
    final dateFormat = DateFormat('h:mm a');
    final duration = meeting.endTime.difference(meeting.startTime);
    final durationString = '${duration.inMinutes} min';

    return Padding(
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          Container(
            width: 3,
            height: 36,
            decoration: BoxDecoration(
              color: _getPlatformColor(meeting.platform),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  meeting.title,
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Text(
                      '${dateFormat.format(meeting.startTime)} • $durationString',
                      style: const TextStyle(
                        color: ResponsiveHelper.textSecondary,
                        fontSize: 12,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: _getPlatformColor(meeting.platform).withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(3),
                      ),
                      child: Text(
                        meeting.platform,
                        style: TextStyle(
                          color: _getPlatformColor(meeting.platform),
                          fontSize: 10,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Color _getPlatformColor(String platform) {
    switch (platform.toLowerCase()) {
      case 'zoom':
        return const Color(0xFF2D8CFF);
      case 'google meet':
        return const Color(0xFF00AC47);
      case 'teams':
        return const Color(0xFF6264A7);
      case 'slack':
        return const Color(0xFF4A154B);
      default:
        return ResponsiveHelper.purplePrimary;
    }
  }

  void _showComingSoonToast(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          context.l10n.googleCalendarComingSoon,
          style: const TextStyle(color: ResponsiveHelper.textPrimary),
        ),
        backgroundColor: ResponsiveHelper.backgroundTertiary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        duration: const Duration(seconds: 2),
      ),
    );
  }
}

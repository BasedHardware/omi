import 'package:flutter/foundation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/calendar_capture_gap_monitor.dart';
import 'package:omi/services/integrations/base_integration_service.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

class GoogleCalendarService extends BaseIntegrationService {
  static const String _appKey = 'google_calendar';
  static const String _prefKey = 'google_calendar_connected';

  // Populated only by calendar-list reads the user already requested. No
  // network discovery, permissions prompts, titles, or attendee data here.
  static final knownMeetings = ValueNotifier<CalendarMeetingSnapshot>(
    const CalendarMeetingSnapshot(owner: '', windows: []),
  );

  static String get meetingCacheOwner =>
      SharedPreferencesUtil().uid.isEmpty ? '' : '${SharedPreferencesUtil().uid}:${AnalyticsManager.identityEpoch}';

  static void rememberMeetings(String owner, Iterable<CalendarCaptureWindow> windows, {required DateTime now}) {
    if (owner.isEmpty) return;
    final byId = <String, CalendarCaptureWindow>{
      if (knownMeetings.value.owner == owner)
        for (final window in knownMeetings.value.windows) window.id: window,
      for (final window in windows) window.id: window,
    };
    final retained = byId.values.where((w) => w.id.isNotEmpty && w.end.isAfter(now) && w.end.isAfter(w.start)).toList()
      ..sort((a, b) => a.start.compareTo(b.start));
    knownMeetings.value = CalendarMeetingSnapshot(owner: owner, windows: List.unmodifiable(retained.take(64)));
  }

  GoogleCalendarService() : super(appKey: _appKey, prefKey: _prefKey);
}

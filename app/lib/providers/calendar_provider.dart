import 'dart:async';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/calendar_meetings.dart' as calendar_api;
import 'package:omi/backend/schema/calendar_meeting_context.dart';
import 'package:omi/services/calendar_service.dart';
import 'package:omi/utils/platform/platform_service.dart';

class CalendarProvider extends ChangeNotifier {
  final CalendarService _service = CalendarService();

  // State
  CalendarPermissionStatus _permissionStatus = CalendarPermissionStatus.notDetermined;
  bool _isMonitoring = false;
  List<CalendarMeeting> _upcomingMeetings = [];
  List<SystemCalendar> _systemCalendars = [];
  bool _isLoading = false;
  bool _isSyncing = false;

  // Getters
  CalendarPermissionStatus get permissionStatus => _permissionStatus;
  bool get isMonitoring => _isMonitoring;

  List<CalendarMeeting> get upcomingMeetings => _upcomingMeetings;
  List<SystemCalendar> get systemCalendars => _systemCalendars;
  bool get isLoading => _isLoading;
  bool get isAuthorized => _permissionStatus == CalendarPermissionStatus.authorized;

  /// Returns meetings in the immediate window (next 60 minutes or currently in progress)
  List<CalendarMeeting> get immediateMeetings {
    return _upcomingMeetings.where((meeting) {
      final minutesUntilStart = meeting.minutesUntilStart;
      final hasEnded = meeting.hasEnded;
      // Include if starting in next 60 minutes or currently in progress
      return (minutesUntilStart >= -5 && minutesUntilStart <= 60) || (meeting.hasStarted && !hasEnded);
    }).toList();
  }

  /// Returns the currently active meeting (started within last 5 min or starting in next 5 min)
  CalendarMeeting? get activeMeeting {
    return _upcomingMeetings.firstWhereOrNull((meeting) {
      final minutesUntilStart = meeting.minutesUntilStart;
      final hasStarted = meeting.hasStarted;
      final hasEnded = meeting.hasEnded;

      // Meeting is active if:
      // - Starting in the next 5 minutes, OR
      // - Started but not ended yet (currently in progress)
      return (minutesUntilStart >= -5 && minutesUntilStart <= 5) || (hasStarted && !hasEnded);
    });
  }

  CalendarProvider() {
    _init();
  }

  Future<void> _init() async {
    // Calendar integration is only supported on macOS
    if (!PlatformService.isMacOS) {
      return;
    }

    await checkPermissionStatus();

    // Only auto-start if user has explicitly enabled calendar integration
    final calendarEnabled = SharedPreferencesUtil().calendarIntegrationEnabled;

    if (isAuthorized && calendarEnabled) {
      // Apply saved settings FIRST, before starting monitoring
      await _applySavedSettings();

      // Now start monitoring with correct settings applied
      await startMonitoring();

      // Fetch calendars and meetings
      await fetchSystemCalendars();
      await refreshMeetings();
    }
  }

  Future<void> _applySavedSettings() async {
    // Apply saved settings to calendar monitor
    await _service.updateSettings(
      showEventsWithNoParticipants: SharedPreferencesUtil().showEventsWithNoParticipants,
      showMeetingsInMenuBar: SharedPreferencesUtil().showMeetingsInMenuBar,
    );
  }

  Future<void> updateShowEventsWithNoParticipants(bool value) async {
    SharedPreferencesUtil().showEventsWithNoParticipants = value;
    await _service.updateSettings(showEventsWithNoParticipants: value);
    await refreshMeetings();
  }

  Future<void> updateShowMeetingsInMenuBar(bool value) async {
    SharedPreferencesUtil().showMeetingsInMenuBar = value;
    await _service.updateSettings(showMeetingsInMenuBar: value);
  }

  Future<void> checkPermissionStatus() async {
    _permissionStatus = await _service.checkPermissionStatus();
    notifyListeners();
  }

  Future<void> requestPermission() async {
    _isLoading = true;
    notifyListeners();

    try {
      _permissionStatus = await _service.requestPermission();
      if (isAuthorized) {
        // Mark calendar as enabled when user grants permission
        SharedPreferencesUtil().calendarIntegrationEnabled = true;
        await _applySavedSettings();
        await startMonitoring();
        await fetchSystemCalendars();
        await refreshMeetings();
      }
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> startMonitoring() async {
    if (!isAuthorized) return;

    await _service.startMonitoring();
    _isMonitoring = true;

    // Listen to events
    _service.initialize(onMeetingEvent: _handleMeetingEvent);

    // Initial fetch
    await refreshMeetings();

    notifyListeners();
  }

  Future<void> stopMonitoring() async {
    await _service.stopMonitoring();
    _service.dispose();
    _isMonitoring = false;
    // Clear enabled flag when user disables calendar
    SharedPreferencesUtil().calendarIntegrationEnabled = false;
    notifyListeners();
  }

  Future<void> refreshMeetings() async {
    if (!isAuthorized) return;

    // Get fresh meetings from calendar
    final freshMeetings = await _service.getUpcomingMeetings();

    // Preserve meetingId from previous syncs
    final meetingIdMap = {
      for (var m in _upcomingMeetings)
        if (m.meetingId != null) m.id: m.meetingId
    };

    // Update meetings list, preserving meetingIds
    _upcomingMeetings = freshMeetings.map((meeting) {
      final existingMeetingId = meetingIdMap[meeting.id];
      if (existingMeetingId != null) {
        return meeting.copyWith(meetingId: existingMeetingId);
      }
      return meeting;
    }).toList();

    // Sync meetings to backend (in background, don't block UI)
    _syncMeetingsToBackend();

    notifyListeners();
  }

  Future<void> _syncMeetingsToBackend() async {
    // Prevent concurrent syncs - if already syncing, skip this call
    if (_isSyncing) {
      debugPrint('CalendarProvider: Sync already in progress, skipping');
      return;
    }

    _isSyncing = true;
    try {
      // Build a map of already synced event IDs to avoid re-syncing on every refresh
      final alreadySyncedIds = _upcomingMeetings.where((m) => m.meetingId != null).map((m) => m.id).toSet();

      debugPrint(
          'CalendarProvider: Syncing ${_upcomingMeetings.length} meetings (${alreadySyncedIds.length} already synced)');

      for (final meeting in _upcomingMeetings) {
        // Skip if we've already synced this calendar event in this session
        if (alreadySyncedIds.contains(meeting.id)) {
          continue;
        }

        try {
          // Convert participants
          final participants = meeting.participants.map((p) {
            return MeetingParticipant(
              name: p.name,
              email: p.email,
            );
          }).toList();

          // Store meeting in backend (backend handles create vs update based on calendar_event_id)
          final response = await calendar_api.storeMeeting(
            calendarEventId: meeting.id,
            calendarSource: 'macos_calendar', // TODO: Detect source dynamically
            title: meeting.title,
            startTime: meeting.startTime,
            endTime: meeting.endTime,
            platform: meeting.platform,
            meetingLink: meeting.meetingUrl,
            participants: participants,
            notes: meeting.notes,
          );

          if (response != null) {
            // Update local meeting with backend meeting_id to mark as synced
            final index = _upcomingMeetings.indexWhere((m) => m.id == meeting.id);
            if (index != -1) {
              _upcomingMeetings[index] = meeting.copyWith(meetingId: response.meetingId);
            }
          }
        } catch (e) {
          debugPrint('CalendarProvider: Error syncing meeting ${meeting.id}: $e');
          // Continue with other meetings even if one fails
        }
      }
      notifyListeners();
    } finally {
      _isSyncing = false;
    }
  }

  Future<void> fetchSystemCalendars() async {
    if (!isAuthorized) return;

    _systemCalendars = await _service.getAvailableCalendars();
    notifyListeners();
  }

  void _handleMeetingEvent(CalendarMeetingEvent event) {
    // Refresh list when events happen
    refreshMeetings();
  }

  @override
  void dispose() {
    _service.dispose();
    super.dispose();
  }
}

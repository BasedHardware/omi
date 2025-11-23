import 'dart:async';
import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/calendar_service.dart';

class CalendarProvider extends ChangeNotifier {
  final CalendarService _service = CalendarService();

  // State
  CalendarPermissionStatus _permissionStatus = CalendarPermissionStatus.notDetermined;
  bool _isMonitoring = false;
  List<CalendarMeeting> _upcomingMeetings = [];
  List<SystemCalendar> _systemCalendars = [];
  bool _isLoading = false;

  // Getters
  CalendarPermissionStatus get permissionStatus => _permissionStatus;
  bool get isMonitoring => _isMonitoring;
  List<CalendarMeeting> get upcomingMeetings => _upcomingMeetings;
  List<SystemCalendar> get systemCalendars => _systemCalendars;
  bool get isLoading => _isLoading;
  bool get isAuthorized => _permissionStatus == CalendarPermissionStatus.authorized;

  CalendarProvider() {
    _init();
  }

  Future<void> _init() async {
    await checkPermissionStatus();

    // Only auto-start if user has explicitly enabled calendar integration
    if (isAuthorized && SharedPreferencesUtil().calendarIntegrationEnabled) {
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
    );
  }

  Future<void> updateShowEventsWithNoParticipants(bool value) async {
    SharedPreferencesUtil().showEventsWithNoParticipants = value;
    await _service.updateSettings(showEventsWithNoParticipants: value);
    await refreshMeetings();
  }

  Future<void> updateShowMeetingsInMenuBar(bool value) async {
    SharedPreferencesUtil().showMeetingsInMenuBar = value;
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

    _upcomingMeetings = await _service.getUpcomingMeetings();
    notifyListeners();
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

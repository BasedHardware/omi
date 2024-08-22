import 'package:device_calendar/device_calendar.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/features/calendar.dart';

class CalenderProvider extends ChangeNotifier {
  List<Calendar> calendars = [];
  bool calendarEnabled = false;
  final CalendarUtil _calendarUtil = CalendarUtil();
  final MixpanelManager _mixpanelManager = MixpanelManager();
  final SharedPreferencesUtil _sharedPreferencesUtil = SharedPreferencesUtil();
  void initialize() {
    calendarEnabled = _sharedPreferencesUtil.calendarEnabled;
    if (calendarEnabled) _getCalendars();
  }

  _getCalendars() async {
    await CalendarUtil().getCalendars().then((value) {
      calendars = value;
      notifyListeners();
    });
  }

  void onCalendarSwitchChanged(bool s) async {
    // TODO: what if user didn't enable permissions?
    if (s) {
      await _getCalendars();
      bool hasAccess = await _calendarUtil.hasCalendarAccess();
      if (calendars.isEmpty && !hasAccess && _sharedPreferencesUtil.calendarPermissionAlreadyRequested) {
        AppSnackbar.showSnackbar(
          'Calendar access was not granted previously. Please enable it in your settings.',
          duration: const Duration(seconds: 5),
        );

        return;
      }

      calendarEnabled = hasAccess;
      notifyListeners();

      _mixpanelManager.calendarEnabled();
    } else {
      _sharedPreferencesUtil.calendarId = '';
      _sharedPreferencesUtil.calendarType = 'auto';
      _mixpanelManager.calendarDisabled();

      calendarEnabled = s;
      notifyListeners();
    }
    _sharedPreferencesUtil.calendarPermissionAlreadyRequested = await _calendarUtil.calendarPermissionAsked();
    _sharedPreferencesUtil.calendarEnabled = await _calendarUtil.hasCalendarAccess() && s;
  }

  void onCalendarTypeChanged(String? v) {
    _sharedPreferencesUtil.calendarType = v!;
    _mixpanelManager.calendarTypeChanged(v);
    notifyListeners();
  }

  void selectCalendar(String? value, Calendar calendar) {
    _sharedPreferencesUtil.calendarId = value!;
    notifyListeners();
    _mixpanelManager.calendarSelected();
    AppSnackbar.showSnackbar(
      'Calendar ${calendar.name} selected.',
      duration: const Duration(seconds: 1),
    );
  }
}

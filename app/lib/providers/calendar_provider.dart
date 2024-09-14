import 'package:device_calendar/device_calendar.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:permission_handler/permission_handler.dart';

class CalenderProvider extends ChangeNotifier {
  List<Calendar> calendars = [];
  bool calendarEnabled = false;
  final CalendarUtil _calendarUtil = CalendarUtil();
  final MixpanelManager _mixpanelManager = MixpanelManager();
  final SharedPreferencesUtil _sharedPreferencesUtil = SharedPreferencesUtil();

  Future<void> initialize() async {
    calendarEnabled = await hasCalendarAccess();
    if (await hasCalendarAccess()) await _getCalendars();
  }

  Future<void> _getCalendars() async {
    calendars = await _calendarUtil.fetchCalendars();
    notifyListeners();
  }

  Future<bool> hasCalendarAccess() async {
    return await _calendarUtil.checkCalendarPermission();
  }

  Future<void> onCalendarSwitchChanged(bool s) async {
    if (s) {
      var res = await Permission.calendarFullAccess.request();
      print('res: $res');
      _sharedPreferencesUtil.calendarPermissionAlreadyRequested = true;
      bool hasAccess = await hasCalendarAccess();
      print('hasAccess: $hasAccess');
      if (res.isGranted || hasAccess) {
        await _getCalendars();
        if (calendars.isEmpty) {
          AppSnackbar.showSnackbar(
            'No calendars found. Please check your device settings.',
            duration: const Duration(seconds: 5),
          );
          calendarEnabled = false;
        } else {
          calendarEnabled = true;
          _mixpanelManager.calendarEnabled();
        }
      } else if ((await Permission.calendarFullAccess.isDenied ||
              await Permission.calendarFullAccess.isPermanentlyDenied) &&
          _sharedPreferencesUtil.calendarPermissionAlreadyRequested) {
        AppSnackbar.showSnackbar(
          'Calendar access was denied. Please enable it in your app settings.',
          duration: const Duration(seconds: 5),
          // action: SnackBarAction(
          //   label: 'Open Settings',
          //   onPressed: () => _calendarUtil.openAppSettings(),
          // ),
        );
        calendarEnabled = false;
      } else {
        AppSnackbar.showSnackbar(
          'Failed to request calendar access. Please try again.',
          duration: const Duration(seconds: 5),
        );
        calendarEnabled = false;
      }
    } else {
      _sharedPreferencesUtil.calendarId = '';
      _sharedPreferencesUtil.calendarType = 'auto';
      _mixpanelManager.calendarDisabled();
      calendarEnabled = false;
    }
    _sharedPreferencesUtil.calendarEnabled = calendarEnabled;
    notifyListeners();
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

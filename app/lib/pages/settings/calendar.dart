import 'package:device_calendar/device_calendar.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

class CalendarPage extends StatefulWidget {
  const CalendarPage({super.key});

  @override
  State<CalendarPage> createState() => _CalendarPageState();
}

class _CalendarPageState extends State<CalendarPage> {
  List<Calendar> calendars = [];
  bool calendarEnabled = false;

  _getCalendars() async {
    await CalendarUtil().getCalendars().then((value) {
      setState(() => calendars = value);
    });
  }

  @override
  void initState() {
    calendarEnabled = SharedPreferencesUtil().calendarEnabled;
    if (calendarEnabled) _getCalendars();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Calendar'),
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: ListView(
        children: [
          Container(
            margin: const EdgeInsets.all(8),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Row(
                  children: [
                    Icon(Icons.edit_calendar),
                    SizedBox(width: 16),
                    Text(
                      'Enable integration',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                      ),
                    ),
                  ],
                ),
                Switch(
                  value: calendarEnabled,
                  onChanged: _onSwitchChanged,
                ),
              ],
            ),
          ),
          const Text(
            'Friend can automatically schedule events from your conversations, or ask for your confirmation first.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.grey,
            ),
          ),
          const SizedBox(height: 24),
          if (calendarEnabled) ..._calendarType(),
          const SizedBox(height: 24),
          if (calendarEnabled) ..._displayCalendars(),
        ],
      ),
    );
  }

  _calendarType() {
    return [
      RadioListTile(
        title: const Text('Automatic'),
        subtitle: const Text('AI Will automatically scheduled your events.'),
        value: 'auto',
        groupValue: SharedPreferencesUtil().calendarType,
        onChanged: (v) {
          SharedPreferencesUtil().calendarType = v!;
          MixpanelManager().calendarTypeChanged(v);
          setState(() {});
        },
      ),
      RadioListTile(
        title: const Text('Manual'),
        subtitle: const Text('Your events will be drafted, but you will have to confirm their creation.'),
        value: 'manual',
        groupValue: SharedPreferencesUtil().calendarType,
        onChanged: (v) {
          SharedPreferencesUtil().calendarType = v!;
          MixpanelManager().calendarTypeChanged(v);
          setState(() {});
        },
      ),
    ];
  }

  _displayCalendars() {
    return [
      const SizedBox(height: 16),
      Container(
        margin: const EdgeInsets.all(16),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: const BoxDecoration(
          borderRadius: BorderRadius.all(Radius.circular(8)),
          border: GradientBoxBorder(
            gradient: LinearGradient(colors: [
              Color.fromARGB(127, 208, 208, 208),
              Color.fromARGB(127, 188, 99, 121),
              Color.fromARGB(127, 86, 101, 182),
              Color.fromARGB(127, 126, 190, 236)
            ]),
            width: 2,
          ),
          shape: BoxShape.rectangle,
        ),
        child: const Center(
            child: Padding(
          padding: EdgeInsets.symmetric(vertical: 4),
          child: Text('Calendars'),
        )),
      ),
      const Padding(
        padding: EdgeInsets.symmetric(horizontal: 8.0),
        child: Text(
          'Select to which calendar you want your Friend to connect to.',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: Colors.grey,
          ),
        ),
      ),
      const SizedBox(height: 16),
      for (var calendar in calendars)
        RadioListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 24),
          title: Text(calendar.name!),
          subtitle: Text(calendar.accountName!),
          value: calendar.id!,
          groupValue: SharedPreferencesUtil().calendarId,
          onChanged: (String? value) {
            SharedPreferencesUtil().calendarId = value!;
            setState(() {});
            MixpanelManager().calendarSelected();
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('Calendar ${calendar.name} selected.'),
                duration: const Duration(seconds: 1),
              ),
            );
          },
        )
    ];
  }

  _onSwitchChanged(s) async {
    // TODO: what if user didn't enable permissions?
    if (s) {
      await _getCalendars();
      bool hasAccess = await CalendarUtil().hasCalendarAccess();
      if (calendars.isEmpty && !hasAccess && SharedPreferencesUtil().calendarPermissionAlreadyRequested) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Calendar access was not granted previously. Please enable it in your settings.'),
              duration: Duration(seconds: 5),
            ),
          );
        }
        return;
      }
      setState(() {
        calendarEnabled = hasAccess;
      });

      MixpanelManager().calendarEnabled();
    } else {
      SharedPreferencesUtil().calendarId = '';
      SharedPreferencesUtil().calendarType = 'auto';
      MixpanelManager().calendarDisabled();
      setState(() {
        calendarEnabled = s;
      });
    }
    SharedPreferencesUtil().calendarPermissionAlreadyRequested = await CalendarUtil().calendarPermissionAsked();
    SharedPreferencesUtil().calendarEnabled = await CalendarUtil().hasCalendarAccess() && s;
  }
}

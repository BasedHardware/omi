import 'package:device_calendar/device_calendar.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/calendar.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

class CalendarPage extends StatefulWidget {
  const CalendarPage({super.key});

  @override
  State<CalendarPage> createState() => _CalendarPageState();
}

class _CalendarPageState extends State<CalendarPage> {
  List<Calendar> calendars = [];
  bool calendarEnabled = false;

  @override
  void initState() {
    calendarEnabled = SharedPreferencesUtil().calendarEnabled;
    if (calendarEnabled) {
      CalendarUtil().getCalendars().then((value) {
        setState(() => calendars = value);
      });
    }
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
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Row(
                  children: [
                    Icon(Icons.calendar_month),
                    SizedBox(width: 10),
                    Text('Calendar Access'),
                  ],
                ),
                Switch(
                  value: calendarEnabled,
                  onChanged: _onSwitchChanged,
                ),
              ],
            ),
          ),
          if (calendarEnabled)
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
              child: Column(
                children: [
                  const Text('Calendars'),
                  const SizedBox(height: 10),
                  for (var calendar in calendars)
                    ListTile(
                      title: Text(calendar.name!),
                      subtitle: Text(calendar.accountName!),
                      onTap: () {
                        SharedPreferencesUtil().calendarId = calendar.id!;
                        setState(() {});
                      },
                      trailing: calendar.id == SharedPreferencesUtil().calendarId ? const Icon(Icons.check) : null,
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  _onSwitchChanged(s) async {
    if (calendarEnabled) {
      calendars = await CalendarUtil().getCalendars();
      debugPrint('Calendars: ${calendars.length}');
      SharedPreferencesUtil().calendarEnabled = s;
    } else {
      SharedPreferencesUtil().calendarEnabled = s;
      SharedPreferencesUtil().calendarId = '';
    }
    setState(() {
      calendarEnabled = s;
    });
  }
}

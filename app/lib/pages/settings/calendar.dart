import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/providers/calendar_provider.dart';
import 'package:friend_private/widgets/extensions/functions.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

class CalendarPage extends StatelessWidget {
  const CalendarPage({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (context) => CalenderProvider(),
      child: const _CalendarPage(),
    );
  }
}

class _CalendarPage extends StatefulWidget {
  const _CalendarPage();

  @override
  State<_CalendarPage> createState() => __CalendarPageState();
}

class __CalendarPageState extends State<_CalendarPage> {
  @override
  void initState() {
    () {
      Provider.of<CalenderProvider>(context, listen: false).initialize();
    }.withPostFrameCallback();
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
      body: Consumer<CalenderProvider>(
        builder: (context, provider, child) {
          return ListView(
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
                      value: provider.calendarEnabled,
                      onChanged: provider.onCalendarSwitchChanged,
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
              if (provider.calendarEnabled) ...[
                RadioListTile(
                  title: const Text('Automatic'),
                  subtitle: const Text('AI Will automatically scheduled your events.'),
                  value: 'auto',
                  groupValue: SharedPreferencesUtil().calendarType,
                  onChanged: provider.onCalendarTypeChanged,
                ),
                RadioListTile(
                  title: const Text('Manual'),
                  subtitle: const Text('Your events will be drafted, but you will have to confirm their creation.'),
                  value: 'manual',
                  groupValue: SharedPreferencesUtil().calendarType,
                  onChanged: provider.onCalendarTypeChanged,
                ),
              ],
              const SizedBox(height: 24),
              if (provider.calendarEnabled) ..._displayCalendars(provider),
            ],
          );
        },
      ),
    );
  }

  _displayCalendars(CalenderProvider provider) {
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
      for (var calendar in provider.calendars)
        RadioListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 24),
          title: Text(calendar.name!),
          subtitle: Text(calendar.accountName!),
          value: calendar.id!,
          groupValue: SharedPreferencesUtil().calendarId,
          onChanged: (v) => provider.selectCalendar(v, calendar),
        ),
    ];
  }
}

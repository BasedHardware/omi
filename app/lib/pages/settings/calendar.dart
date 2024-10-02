import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/providers/calendar_provider.dart';
import 'package:friend_private/widgets/extensions/functions.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/services/translation_service.dart';

class CalendarPage extends StatefulWidget {
  const CalendarPage({super.key});

  @override
  State<CalendarPage> createState() => _CalendarPageState();
}

class _CalendarPageState extends State<CalendarPage> {
  @override
  void initState() {
    () async {
      await Provider.of<CalenderProvider>(context, listen: false).initialize();
    }.withPostFrameCallback();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title:  Text(TranslationService.translate('Calendar')),
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: Consumer<CalenderProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading) {
            return const Center(
              child: CircularProgressIndicator(
                color: Colors.white,
              ),
            );
          }
          return ListView(
            children: [
              Container(
                margin: const EdgeInsets.all(8),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                     Row(
                      children: [
                        Icon(Icons.edit_calendar),
                        SizedBox(width: 16),
                        Text(
          TranslationService.translate('Enable integration'),
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                          ),
                        ),
                      ],
                    ),
                    Switch(
                      value: provider.calendarEnabled,
                      onChanged: (v) async {
                        await provider.onCalendarSwitchChanged(v);
                      },
                    ),
                  ],
                ),
              ),
               Padding(
                padding: EdgeInsets.symmetric(horizontal: 12, vertical: 2),
                child: Text(
                  TranslationService.translate('Omi can automatically schedule events from your conversations, or ask for your confirmation first.'),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.grey,
                  ),
                ),
              ),
              const SizedBox(height: 32),
              provider.calendarEnabled
                  ? Container(
                      margin: const EdgeInsets.all(16),
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: const Text('Mode', style: TextStyle(fontSize: 18)),
                    )
                  : const SizedBox(),
              if (provider.calendarEnabled) ...[
                RadioListTile(
                  title:  Text(TranslationService.translate('Automatic')),
                  subtitle:  Text(TranslationService.translate('Omi Will automatically scheduled your events.')),
                  value: 'auto',
                  groupValue: SharedPreferencesUtil().calendarType,
                  onChanged: provider.onCalendarTypeChanged,
                ),
                RadioListTile(
                  title:  Text(TranslationService.translate('Manual')),
                  subtitle:  Text(TranslationService.translate('Your events will be drafted, but you will have to confirm their creation.')),
                  value: 'manual',
                  groupValue: SharedPreferencesUtil().calendarType,
                  onChanged: provider.onCalendarTypeChanged,
                ),
              ],
              provider.calendarEnabled ? const SizedBox(height: 48) : const SizedBox(),
              provider.calendarEnabled
                  ? Divider(
                      color: Colors.grey.shade400,
                      height: 1,
                    )
                  : const SizedBox(),
              const SizedBox(height: 12),
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
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Text(TranslationService.translate('Select a calendar'), style: TextStyle(fontSize: 18)),
      ),
       Padding(
        padding: EdgeInsets.symmetric(horizontal: 32),
        child: Text(
          TranslationService.translate('Which calendar Omi will schedule to?'),
          style: TextStyle(color: Colors.grey),
        ),
      ),
      const SizedBox(height: 16),
      for (var calendar in provider.calendars)
        RadioListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 24),
          title: Text(calendar.name!),
          subtitle: (calendar.accountName?.isNotEmpty ?? false) ? Text(calendar.accountName!) : null,
          value: calendar.id!,
          groupValue: SharedPreferencesUtil().calendarId,
          onChanged: (v) => provider.selectCalendar(v, calendar),
        ),
    ];
  }
}

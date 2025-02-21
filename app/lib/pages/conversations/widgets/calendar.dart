import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/providers/conversation_provider.dart';

class CalendarIconButton extends StatelessWidget {
  const CalendarIconButton({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(
      builder: (context, convoProvider, child) {
        return Container(
          decoration: BoxDecoration(
            color: Colors.grey.shade900,
            borderRadius: const BorderRadius.all(Radius.circular(16)),
          ),
          child: IconButton(
            onPressed: () async {
              if (Platform.isAndroid) {
                // Android: Show Material Design DatePicker
                DateTime? picked = await showDatePicker(
                  context: context,
                  initialDate: convoProvider.selectedDate ?? DateTime.now(),
                  firstDate: DateTime(2000),
                  lastDate: DateTime.now(),
                  builder: (context, child) {
                    return Dialog(
                      backgroundColor: Colors.transparent,
                      child: SizedBox(
                        height: MediaQuery.of(context).size.height * 0.75,
                        child: Theme(
                          data: Theme.of(context).copyWith(
                            colorScheme: ColorScheme.light(
                              primary: Colors.white,
                              onPrimary: Colors.grey.shade900,
                              surface: Colors.grey.shade900,
                              onSurface: Colors.white,
                            ),
                            textButtonTheme: TextButtonThemeData(
                              style: TextButton.styleFrom(
                                foregroundColor: Colors.white,
                              ),
                            ),
                          ),
                          child: child!,
                        ),
                      ),
                    );
                  },
                );

                if (picked != null && picked != convoProvider.selectedDate) {
                  convoProvider.selectDate(picked);
                }
              } else if (Platform.isIOS) {
                // iOS: Show Cupertino-style DatePicker
                showCupertinoModalPopup(
                  context: context,
                  builder: (context) {
                    DateTime selectedDate =
                        convoProvider.selectedDate ?? DateTime.now();
                    return Container(
                      height: 250,
                      color: Colors.white,
                      child: Column(
                        children: [
                          SizedBox(
                            height: 200,
                            child: CupertinoDatePicker(
                              mode: CupertinoDatePickerMode.date,
                              initialDateTime: selectedDate,
                              minimumDate: DateTime(2000),
                              maximumDate: DateTime.now(),
                              onDateTimeChanged: (DateTime newDate) {
                                convoProvider.selectDate(newDate);
                              },
                            ),
                          ),
                          CupertinoButton(
                            child: const Text('Done'),
                            onPressed: () {
                              Navigator.of(context).pop();
                            },
                          ),
                        ],
                      ),
                    );
                  },
                );
              }
            },
            icon: const Icon(
              Icons.calendar_today,
              color: Colors.white,
              size: 20,
            ),
          ),
        );
      },
    );
  }
}

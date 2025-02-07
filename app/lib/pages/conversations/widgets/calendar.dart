import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/providers/conversation_provider.dart';

class CalendarIconButton extends StatelessWidget { // StatelessWidget now
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
              DateTime? picked = await showDatePicker(
                context: context,
                initialDate: convoProvider.selectedDate ?? DateTime.now(),
                firstDate: DateTime(2000),
                lastDate: DateTime.now(),
              );

              if (picked != null && picked != convoProvider.selectedDate) {
                convoProvider.selectDate(picked);
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
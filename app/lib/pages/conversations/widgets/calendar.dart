import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/providers/conversation_provider.dart';

class CalendarIconButton extends StatefulWidget {
  const CalendarIconButton({super.key});

  @override
  State<CalendarIconButton> createState() => _CalendarIconButtonState();
}

class _CalendarIconButtonState extends State<CalendarIconButton> {
  DateTime? _selectedDate; // Store the selected date

  Future<void> _showDatePicker(BuildContext context) async {
    final DateTime now = DateTime.now(); // Get the current date
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _selectedDate ?? DateTime.now(), // Start with current or selected date
      firstDate: DateTime(2000), // Set a reasonable first date
      lastDate: now, // Set a reasonable last date
    );

    if (picked != null && picked != _selectedDate) {
      setState(() {
        _selectedDate = picked;
        // filter conversations based on the date.
        //_filterConversationsByDate(_selectedDate);
      });
    }
  }
/* 
  void _filterConversationsByDate(DateTime? date) {
    // filter conversations based on the selected date.
    // ConversationProvider or similar state management.

    if (date != null) {
      print("Filtering conversations by: ${DateFormat('yyyy-MM-dd').format(date)}");
      // Example: Call a function in your provider
      // Provider.of<ConversationProvider>(context, listen: false).filterByDate(date);
    } else {
       print("Clearing date filter");
      //Provider.of<ConversationProvider>(context, listen: false).clearDateFilter();
    }

  } */

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(
      builder: (BuildContext context, ConversationProvider convoProvider, Widget? child) {
        return Container(
          decoration: BoxDecoration(
            color: Colors.grey.shade900,
            borderRadius: const BorderRadius.all(Radius.circular(16)),
          ),
          child: IconButton(
            onPressed: () => _showDatePicker(context),
            icon: const Icon(
              Icons.calendar_today,
              color: Colors.white,
              size: 20, // Match the filter button size
            ),
          ),
        );
      }
    );
  }
}
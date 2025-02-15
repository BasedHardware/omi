import 'package:flutter/material.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

class SearchResultHeaderWidget extends StatelessWidget {
  const SearchResultHeaderWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(builder: (context, convoProvider, child) {
      if (convoProvider.selectedDate != null) {
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Conversations from ${DateFormat('MMM d, yyyy').format(convoProvider.selectedDate!)}',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
              TextButton(
                onPressed: convoProvider.clearDateFilter,
                child: const Text(
                  'Clear Filter',
                  style: TextStyle(
                    color: Colors.blue,
                    fontSize: 14,
                  ),
                ),
              ),
            ],
          ),
        );
      }
      if (convoProvider.previousQuery.isNotEmpty) {
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Text(
            'Search results for "${convoProvider.previousQuery}"',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
        );
      }
      return const SizedBox.shrink();
    });
  }
}

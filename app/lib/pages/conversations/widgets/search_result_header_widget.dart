import 'package:flutter/material.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:provider/provider.dart';

class SearchResultHeaderWidget extends StatefulWidget {
  const SearchResultHeaderWidget({super.key});

  @override
  State<SearchResultHeaderWidget> createState() => _SearchResultHeaderWidgetState();
}

class _SearchResultHeaderWidgetState extends State<SearchResultHeaderWidget> {
  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(builder: (context, provider, child) {
      var onSearches = provider.previousQuery.isNotEmpty;
      var isSearching = provider.isFetchingConversations;

      return Container(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        child: onSearches
            ? (isSearching
                ? const Text(
                    "Search your converstations",
                    style: TextStyle(color: Colors.white, fontSize: 14),
                  )
                : provider.totalSearchPages > 0
                    ? Text(
                        "Search result ${provider.currentSearchPage}/${provider.totalSearchPages}",
                        style: const TextStyle(color: Colors.white, fontSize: 14),
                      )
                    : const SizedBox.shrink())
            : const SizedBox.shrink(),
      );
    });
  }
}

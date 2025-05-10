import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

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
                ? Shimmer.fromColors(
                    baseColor: Colors.white,
                    highlightColor: Colors.grey,
                    child: const Text(
                      "Searching your conversations",
                      style: TextStyle(color: Colors.white, fontSize: 14),
                    ))
                : provider.totalSearchPages > 0
                    ? const Text(
                        "Search results",
                        style: const TextStyle(color: Colors.white, fontSize: 14),
                      )
                    : const SizedBox.shrink())
            : const SizedBox.shrink(),
      );
    });
  }
}

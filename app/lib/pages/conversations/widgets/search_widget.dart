import 'package:flutter/material.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/utils/other/debouncer.dart';
import 'package:provider/provider.dart';

class SearchWidget extends StatefulWidget {
  const SearchWidget({super.key});

  @override
  State<SearchWidget> createState() => _SearchWidgetState();
}

class _SearchWidgetState extends State<SearchWidget> {
  final TextEditingController searchController = TextEditingController();
  final _debouncer = Debouncer(delay: const Duration(milliseconds: 500));
  bool showClearButton = false;

  void setShowClearButton() {
    if (showClearButton != searchController.text.isNotEmpty) {
      setState(() {
        showClearButton = searchController.text.isNotEmpty;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 0),
      child: TextFormField(
        controller: searchController,
        focusNode: context.read<HomeProvider>().convoSearchFieldFocusNode,
        onChanged: (value) {
          var provider = Provider.of<ConversationProvider>(context, listen: false);
          _debouncer.run(() async {
            await provider.searchConversations(value);
          });
          setShowClearButton();
        },
        decoration: InputDecoration(
          hintText: 'Search Conversations',
          hintStyle: TextStyle(color: Colors.grey.shade500),
          filled: false,
    
          // fillColor: Colors.grey[900],
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(color: Colors.grey.shade800, width: 0.5),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(color: Colors.grey.shade500, width: 0.5),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(color: Colors.grey.shade500, width: 0.5),
          ),
          prefixIcon: Icon(
            Icons.search,
            color: Colors.grey.shade500,
          ),
          suffixIcon: showClearButton
              ? GestureDetector(
                  onTap: () {
                    var provider = Provider.of<ConversationProvider>(context, listen: false);
                    provider.resetGroupedConvos();
                    searchController.clear();
                    setShowClearButton();
                  },
                  child: const Icon(
                    Icons.close,
                    color: Colors.white,
                  ),
                )
              : null,
          contentPadding: const EdgeInsets.symmetric(horizontal: 12),
        ),
        style: const TextStyle(color: Colors.white),
      ),
    );
  }
}

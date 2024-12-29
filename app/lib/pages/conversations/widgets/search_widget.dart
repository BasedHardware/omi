import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
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
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Container(
          padding: const EdgeInsets.fromLTRB(16, 16, 2, 0),
          width: MediaQuery.sizeOf(context).width * 0.85,
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
                borderSide: BorderSide(color: Colors.grey.shade900, width: 0.5),
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
        ),
        Consumer2<ConversationProvider, HomeProvider>(builder: (context, convoProvider, home, child) {
          if (home.selectedIndex != 0 ||
              !convoProvider.hasNonDiscardedConversations ||
              convoProvider.isLoadingConversations) {
            return const SizedBox.shrink();
          }
          return Padding(
            padding: const EdgeInsets.only(left: 2.0, top: 12),
            child: IconButton(
              onPressed: convoProvider.toggleDiscardConversations,
              icon: Icon(
                SharedPreferencesUtil().showDiscardedMemories ? Icons.filter_list_off_sharp : Icons.filter_list,
                color: Colors.white,
                size: 24,
              ),
            ),
          );
        }),
      ],
    );
  }
}

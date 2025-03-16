import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/other/debouncer.dart';
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
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
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
                hintStyle: const TextStyle(color: Colors.white60, fontSize: 14),
                filled: true,
                fillColor: Colors.grey.shade900,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(16),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(16),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(16),
                ),
                prefixIcon: const Icon(
                  Icons.search,
                  color: Colors.white60,
                ),
                suffixIcon: showClearButton
                    ? GestureDetector(
                        onTap: () async {
                          var provider = Provider.of<ConversationProvider>(context, listen: false);
                          await provider.searchConversations(""); // clear
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
          const SizedBox(
            width: 12,
          ),
          Consumer<ConversationProvider>(
              builder: (BuildContext context, ConversationProvider convoProvider, Widget? child) {
            return Container(
              decoration: BoxDecoration(
                color: Colors.grey.shade900,
                borderRadius: const BorderRadius.all(Radius.circular(16)),
              ),
              child: IconButton(
                onPressed: convoProvider.toggleDiscardConversations,
                icon: Icon(
                  convoProvider.showDiscardedConversations ? Icons.filter_alt_off_sharp : Icons.filter_alt_sharp,
                  color: Colors.white,
                  size: 20,
                ),
              ),
            );
          }),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:friend_private/pages/conversations/widgets/conversation_list_item.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/utils/other/debouncer.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

class SearchPage extends StatefulWidget {
  const SearchPage({super.key});

  @override
  State<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends State<SearchPage> {
  final TextEditingController searchController = TextEditingController();
  final _debouncer = Debouncer(delay: const Duration(milliseconds: 600));

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: PreferredSize(
          preferredSize: const Size.fromHeight(80.0),
          child: Padding(
            padding: const EdgeInsets.only(top: 10.0),
            child: AppBar(
              backgroundColor: Theme.of(context).colorScheme.primary,
              elevation: 0,
              title: SizedBox(
                width: MediaQuery.sizeOf(context).width * 0.9,
                height: 40,
                child: TextFormField(
                  controller: searchController,
                  focusNode: context.read<HomeProvider>().convoSearchFieldFocusNode,
                  onChanged: (value) {
                    _debouncer.run(() async {
                      await provider.searchConversations(value);
                    });
                  },
                  decoration: InputDecoration(
                    hintText: 'Search Conversations',
                    hintStyle: const TextStyle(color: Colors.white),
                    filled: true,
                    fillColor: Colors.grey[800],
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: BorderSide.none,
                    ),
                    suffixIcon: searchController.text.isNotEmpty
                        ? GestureDetector(
                            onTap: () {
                              searchController.clear();
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
            ),
          ),
        ),
        body: provider.isFetchingConversations
            ? const Center(
                child: CircularProgressIndicator(
                  color: Colors.white,
                ),
              )
            : ListView.separated(
                shrinkWrap: true,
                scrollDirection: Axis.vertical,
                itemBuilder: (ctx, idx) {
                  if (idx == provider.groupedConversations.values.expand((element) => element).toList().length) {
                    if (provider.isLoadingConversations) {
                      return const Center(
                        child: Padding(
                          padding: EdgeInsets.only(top: 32.0),
                          child: CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                        ),
                      );
                    }
                    return VisibilityDetector(
                      key: const Key('search-key'),
                      onVisibilityChanged: (visibilityInfo) async {
                        if (visibilityInfo.visibleFraction > 0 &&
                            !provider.isLoadingConversations &&
                            (provider.totalSearchPages > provider.currentSearchPage)) {
                          await provider.searchMoreConversations();
                        }
                      },
                      child: const SizedBox(height: 20, width: double.maxFinite),
                    );
                  } else {
                    var convo = provider.groupedConversations.values.expand((element) => element).toList()[idx];
                    var date = DateTime(convo.createdAt.year, convo.createdAt.month, convo.createdAt.day);
                    var convoIdx = provider.groupedSearchConvoIndex(convo);
                    return ConversationListItem(conversation: convo, conversationIdx: convoIdx, date: date);
                  }
                },
                separatorBuilder: (ctx, idx) {
                  return const SizedBox(
                    height: 8,
                  );
                },
                itemCount: provider.groupedConversations.values.expand((element) => element).toList().length + 1,
              ),
      );
    });
  }
}

import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
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
  HomeProvider? _homeProvider;
  ConversationProvider? _convoProvider;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Store provider references safely
    _homeProvider = Provider.of<HomeProvider>(context, listen: false);
    _convoProvider = Provider.of<ConversationProvider>(context, listen: false);

    // Add listener if not already added
    _homeProvider?.convoSearchFieldFocusNode.removeListener(_onFocusChange);
    _homeProvider?.convoSearchFieldFocusNode.addListener(_onFocusChange);
  }

  @override
  void dispose() {
    // Remove listener safely
    _homeProvider?.convoSearchFieldFocusNode.removeListener(_onFocusChange);
    // Dispose the text controller to prevent memory leak
    searchController.dispose();
    // Cancel any pending debounced operations
    _debouncer.cancel();
    super.dispose();
  }

  void _onFocusChange() {
    // Check if widget is still mounted before accessing providers
    if (!mounted || _homeProvider == null || _convoProvider == null) {
      return;
    }

    // Hide search bar if focus is lost and there's no search query
    if (!_homeProvider!.isConvoSearchFieldFocused &&
        _convoProvider!.previousQuery.isEmpty &&
        _homeProvider!.showConvoSearchBar) {
      _homeProvider!.hideConvoSearchBar();
    }
  }

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
              onTap: () {
                MixpanelManager().searchBarFocused();
              },
              onChanged: (value) {
                var provider = Provider.of<ConversationProvider>(context, listen: false);
                _debouncer.run(() async {
                  await provider.searchConversations(value);
                  if (value.isNotEmpty) {
                    // Track search query with results count
                    MixpanelManager().searchQueryEntered(value, provider.searchedConversations.length);
                  }
                });
                setShowClearButton();
              },
              decoration: InputDecoration(
                hintText: 'Search Conversations',
                hintStyle: const TextStyle(color: Colors.white60, fontSize: 14),
                filled: true,
                fillColor: const Color(0xFF1F1F25),
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
                          var homeProvider = Provider.of<HomeProvider>(context, listen: false);
                          await provider.searchConversations(""); // clear
                          searchController.clear();
                          setShowClearButton();
                          // Hide search bar when search is cleared
                          homeProvider.hideConvoSearchBar();
                          MixpanelManager().searchQueryCleared();
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
            width: 8,
          ),
          // Calendar button
          Consumer<ConversationProvider>(
            builder: (BuildContext context, ConversationProvider convoProvider, Widget? child) {
              return Container(
                decoration: BoxDecoration(
                  color:
                      convoProvider.selectedDate != null ? Colors.deepPurple.withOpacity(0.5) : const Color(0xFF1F1F25),
                  borderRadius: const BorderRadius.all(Radius.circular(16)),
                ),
                child: IconButton(
                  onPressed: () async {
                    HapticFeedback.mediumImpact();
                    if (convoProvider.selectedDate != null) {
                      // Clear date filter
                      await convoProvider.clearDateFilter();
                      MixpanelManager().calendarFilterCleared();
                    } else {
                      // Open date picker
                      await _selectDate(context);
                    }
                  },
                  icon: Icon(
                    convoProvider.selectedDate != null ? FontAwesomeIcons.calendarDay : FontAwesomeIcons.calendarDays,
                    color: Colors.white,
                    size: 18,
                  ),
                  tooltip: convoProvider.selectedDate != null
                      ? 'Filtered by ${DateFormat('MMM d, yyyy').format(convoProvider.selectedDate!)} - Tap to clear'
                      : 'Filter by date',
                ),
              );
            },
          ),
          const SizedBox(width: 8),
          // Starred filter button
          Consumer<ConversationProvider>(
            builder: (BuildContext context, ConversationProvider convoProvider, Widget? child) {
              return Container(
                decoration: BoxDecoration(
                  color: convoProvider.showStarredOnly ? Colors.amber.withValues(alpha: 0.5) : const Color(0xFF1F1F25),
                  borderRadius: const BorderRadius.all(Radius.circular(16)),
                ),
                child: IconButton(
                  onPressed: () {
                    HapticFeedback.mediumImpact();
                    convoProvider.toggleStarredFilter();
                  },
                  icon: Icon(
                    convoProvider.showStarredOnly ? FontAwesomeIcons.solidStar : FontAwesomeIcons.star,
                    color: convoProvider.showStarredOnly ? Colors.amber : Colors.white,
                    size: 18,
                  ),
                  tooltip:
                      convoProvider.showStarredOnly ? 'Showing starred only - Tap to show all' : 'Filter by starred',
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}

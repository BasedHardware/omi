import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';

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

  Future<void> _selectDate(BuildContext context) async {
    DateTime selectedDate = DateTime.now();

    await showCupertinoModalPopup<void>(
      context: context,
      builder: (BuildContext context) {
        return Container(
          height: 300,
          padding: const EdgeInsets.only(top: 6.0),
          margin: EdgeInsets.only(
            bottom: MediaQuery.of(context).viewInsets.bottom,
          ),
          color: CupertinoColors.systemBackground.resolveFrom(context),
          child: SafeArea(
            top: false,
            child: Column(
              children: [
                // Header with Cancel and Done buttons
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1F1F25),
                    border: Border(
                      bottom: BorderSide(
                        color: Color(0xFF35343B),
                        width: 0.5,
                      ),
                    ),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () => Navigator.of(context).pop(),
                        child: const Text(
                          'Cancel',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                          ),
                        ),
                      ),
                      const Spacer(),
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () async {
                          Navigator.of(context).pop();
                          if (context.mounted) {
                            final provider = Provider.of<ConversationProvider>(context, listen: false);
                            await provider.filterConversationsByDate(selectedDate);
                            MixpanelManager().calendarFilterApplied(selectedDate);
                          }
                        },
                        child: const Text(
                          'Done',
                          style: TextStyle(
                            color: Colors.deepPurple,
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                // Date picker
                Expanded(
                  child: Container(
                    color: const Color(0xFF1F1F25),
                    child: CupertinoDatePicker(
                      mode: CupertinoDatePickerMode.date,
                      initialDateTime: DateTime.now(),
                      minimumDate: DateTime(2020),
                      maximumDate: DateTime.now(),
                      onDateTimeChanged: (DateTime newDate) {
                        selectedDate = newDate;
                      },
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
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
                          await provider.searchConversations(""); // clear
                          searchController.clear();
                          setShowClearButton();
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
                  color: convoProvider.showStarredOnly ? Colors.amber.withOpacity(0.5) : const Color(0xFF1F1F25),
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

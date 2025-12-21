import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/ui_guidelines.dart';
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
                            color: Color(0xFF3B82F6),
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
      color: const Color(0xFF0F0F0F), // Match scaffold background
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: SizedBox(
              height: 44,
              child: SearchBar(
                hintText: 'Search Conversations',
                leading: const Padding(
                  padding: EdgeInsets.only(left: 6.0),
                  child: Icon(FontAwesomeIcons.magnifyingGlass, color: Colors.white70, size: 14),
                ),
                backgroundColor: WidgetStateProperty.all(AppStyles.backgroundSecondary),
                elevation: WidgetStateProperty.all(0),
                padding: WidgetStateProperty.all(
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                ),
                focusNode: context.read<HomeProvider>().convoSearchFieldFocusNode,
                controller: searchController,
                trailing: showClearButton
                    ? [
                        IconButton(
                          icon: const Icon(Icons.close, color: Colors.white70, size: 16),
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(
                            minHeight: 36,
                            minWidth: 36,
                          ),
                          onPressed: () async {
                            var provider = Provider.of<ConversationProvider>(context, listen: false);
                            await provider.searchConversations(""); // clear
                            searchController.clear();
                            setShowClearButton();
                            MixpanelManager().searchQueryCleared();
                          },
                        )
                      ]
                    : null,
                hintStyle: WidgetStateProperty.all(
                  TextStyle(color: AppStyles.textTertiary, fontSize: 14),
                ),
                textStyle: WidgetStateProperty.all(
                  const TextStyle(color: AppStyles.textPrimary, fontSize: 14),
                ),
                shape: WidgetStateProperty.all(
                  RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                  ),
                ),
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
                onTap: () {
                  MixpanelManager().searchBarFocused();
                },
                onSubmitted: (value) {
                  if (value.isNotEmpty) {
                    var provider = Provider.of<ConversationProvider>(context, listen: false);
                    MixpanelManager().searchQueryEntered(value, provider.searchedConversations.length);
                  }
                },
              ),
            ),
          ),
          const SizedBox(width: 8),
          // Calendar button
          Consumer<ConversationProvider>(
            builder: (BuildContext context, ConversationProvider convoProvider, Widget? child) {
              return SizedBox(
                width: 44,
                height: 44,
                child: Container(
                  decoration: BoxDecoration(
                    color: convoProvider.selectedDate != null
                        ? const Color(0xFF3B82F6).withOpacity(0.3)
                        : AppStyles.backgroundSecondary,
                    borderRadius: BorderRadius.circular(12),
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
                      convoProvider.selectedDate != null
                          ? FontAwesomeIcons.calendarDay
                          : FontAwesomeIcons.calendarDays,
                      color: Colors.white,
                      size: 16,
                    ),
                    tooltip: convoProvider.selectedDate != null
                        ? 'Filtered by ${DateFormat('MMM d, yyyy').format(convoProvider.selectedDate!)} - Tap to clear'
                        : 'Filter by date',
                    padding: EdgeInsets.zero,
                  ),
                ),
              );
            },
          ),
          const SizedBox(width: 8),
          // Filter button
          Consumer<ConversationProvider>(
            builder: (BuildContext context, ConversationProvider convoProvider, Widget? child) {
              return SizedBox(
                width: 44,
                height: 44,
                child: Container(
                  decoration: BoxDecoration(
                    color: convoProvider.showDiscardedConversations
                        ? Colors.red.withOpacity(0.5)
                        : AppStyles.backgroundSecondary,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: IconButton(
                    onPressed: () {
                      HapticFeedback.mediumImpact();
                      convoProvider.toggleDiscardConversations();
                      MixpanelManager().deletedConversationsFilterToggled(!convoProvider.showDiscardedConversations);
                    },
                    icon: Icon(
                      convoProvider.showDiscardedConversations
                          ? FontAwesomeIcons.eyeSlash
                          : FontAwesomeIcons.eye,
                      color: Colors.white,
                      size: 16,
                    ),
                    padding: EdgeInsets.zero,
                  ),
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}

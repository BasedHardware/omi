import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:calendar_date_picker2/calendar_date_picker2.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';

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

  Future<void> _showDatePicker(BuildContext context, {bool hasExistingFilter = false}) async {
    final convoProvider = Provider.of<ConversationProvider>(context, listen: false);
    DateTime selectedDate = convoProvider.selectedDate ?? DateTime.now();
    await showCupertinoModalPopup<void>(
      context: context,
      builder: (BuildContext context) {
        return Container(
          height: 420,
          padding: const EdgeInsets.only(top: 6.0),
          margin: EdgeInsets.only(
            bottom: MediaQuery.of(context).viewInsets.bottom,
          ),
          color: const Color(0xFF1F1F25),
          child: SafeArea(
            top: false,
            child: Column(
              children: [
                // Header with Cancel and Done buttons
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                  decoration: const BoxDecoration(
                    color: Color(0xFF1F1F25),
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
                        onPressed: () async {
                          if (hasExistingFilter) {
                            final provider = Provider.of<ConversationProvider>(context, listen: false);
                            Navigator.of(context).pop();
                            await provider.clearDateFilter();
                            MixpanelManager().calendarFilterCleared();
                          } else {
                            Navigator.of(context).pop();
                          }
                        },
                        child: Text(
                          hasExistingFilter ? context.l10n.removeFilter : context.l10n.cancel,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                          ),
                        ),
                      ),
                      const Spacer(),
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () async {
                          final provider = Provider.of<ConversationProvider>(context, listen: false);
                          Navigator.of(context).pop();
                          await provider.filterConversationsByDate(selectedDate);
                          MixpanelManager().calendarFilterApplied(selectedDate);
                        },
                        child: Text(
                          context.l10n.done,
                          style: const TextStyle(
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
                  child: Material(
                    color: ResponsiveHelper.backgroundSecondary,
                    child: CalendarDatePicker2(
                      config: getDefaultCalendarConfig(
                        firstDate: DateTime(2020),
                        lastDate: DateTime.now(),
                        currentDate: DateTime.now(),
                      ),
                      value: [selectedDate],
                      onValueChanged: (dates) {
                        if (dates.isNotEmpty) {
                          selectedDate = dates[0];
                        }
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
                hintText: context.l10n.searchConversations,
                hintStyle: const TextStyle(color: Colors.white60, fontSize: 14),
                filled: true,
                fillColor: const Color(0xFF1F1F25),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: BorderSide.none,
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: BorderSide.none,
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: BorderSide.none,
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
          const SizedBox(width: 8),
          // Calendar button - same height as search bar (48px)
          Consumer<ConversationProvider>(
            builder: (context, convoProvider, _) {
              return Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: convoProvider.selectedDate != null
                      ? Colors.deepPurple.withValues(alpha: 0.5)
                      : const Color(0xFF1F1F25),
                  borderRadius: BorderRadius.circular(24),
                ),
                child: IconButton(
                  padding: EdgeInsets.zero,
                  icon: Icon(
                    convoProvider.selectedDate != null ? FontAwesomeIcons.calendarDay : FontAwesomeIcons.calendarDays,
                    size: 18,
                    color: convoProvider.selectedDate != null ? Colors.white : Colors.white70,
                  ),
                  onPressed: () async {
                    HapticFeedback.mediumImpact();
                    await _showDatePicker(context, hasExistingFilter: convoProvider.selectedDate != null);
                  },
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}

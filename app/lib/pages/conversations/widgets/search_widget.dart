import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/pages/conversations/widgets/speaker_filter_sheet.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/debouncer.dart';
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
        !_convoProvider!.hasActiveSearch &&
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
                PlatformManager.instance.analytics.searchBarFocused();
              },
              onChanged: (value) {
                var provider = Provider.of<ConversationProvider>(context, listen: false);
                _debouncer.run(() async {
                  await provider.searchConversations(value);
                  if (value.isNotEmpty) {
                    // Track search query with results count
                    PlatformManager.instance.analytics.searchQueryEntered(value, provider.searchedConversations.length);
                  }
                });
                setShowClearButton();
              },
              decoration: InputDecoration(
                hintText: context.l10n.searchConversations,
                hintStyle: const TextStyle(color: Colors.white60, fontSize: 14),
                filled: true,
                fillColor: const Color(0xFF1F1F25),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: BorderSide.none),
                focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: BorderSide.none),
                enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: BorderSide.none),
                prefixIcon: const Icon(Icons.search, color: Colors.white60),
                suffixIcon: showClearButton
                    ? GestureDetector(
                        onTap: () async {
                          var provider = Provider.of<ConversationProvider>(context, listen: false);
                          var homeProvider = Provider.of<HomeProvider>(context, listen: false);
                          await provider.searchConversations(""); // clear
                          searchController.clear();
                          setShowClearButton();
                          if (!provider.hasActiveSearch) {
                            homeProvider.hideConvoSearchBar();
                          }
                          PlatformManager.instance.analytics.searchQueryCleared();
                        },
                        child: const Icon(Icons.close, color: Colors.white),
                      )
                    : null,
                contentPadding: const EdgeInsets.symmetric(horizontal: 12),
              ),
              style: const TextStyle(color: Colors.white),
            ),
          ),
          const SizedBox(width: 8),
          Consumer<ConversationProvider>(
            builder: (context, convoProvider, _) {
              final isActive = convoProvider.selectedSpeakerId != null;
              return Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: isActive ? Colors.deepPurple.withValues(alpha: 0.5) : const Color(0xFF1F1F25),
                  borderRadius: BorderRadius.circular(24),
                ),
                child: IconButton(
                  key: const Key('conversation_speaker_filter'),
                  padding: EdgeInsets.zero,
                  tooltip: context.l10n.phoneSpeaker,
                  icon: Icon(Icons.person_search, size: 20, color: isActive ? Colors.white : Colors.white70),
                  onPressed: () async {
                    HapticFeedback.mediumImpact();
                    await showSpeakerFilterSheet(context);
                  },
                ),
              );
            },
          ),
          const SizedBox(width: 8),
          // Calendar button - same height as search bar (48px)
          Consumer<ConversationProvider>(
            builder: (context, convoProvider, _) {
              final hasSearchQuery = searchController.text.isNotEmpty;
              final hasActiveFilter =
                  hasSearchQuery ? convoProvider.searchStartDate != null : convoProvider.selectedStartDate != null;
              return Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: hasActiveFilter ? Colors.deepPurple.withValues(alpha: 0.5) : const Color(0xFF1F1F25),
                  borderRadius: BorderRadius.circular(24),
                ),
                child: IconButton(
                  padding: EdgeInsets.zero,
                  icon: FaIcon(
                    hasActiveFilter ? FontAwesomeIcons.calendarDay : FontAwesomeIcons.calendarDays,
                    size: 18,
                    color: hasActiveFilter ? Colors.white : Colors.white70,
                  ),
                  onPressed: () async {
                    HapticFeedback.mediumImpact();
                    if (hasSearchQuery) {
                      await showConversationSearchDateRangePicker(context);
                    } else {
                      await showConversationDateRangePicker(context);
                    }
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

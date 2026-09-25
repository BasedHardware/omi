import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/pages/conversations/widgets/speaker_filter_sheet.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';

class SearchWidget extends StatefulWidget {
  const SearchWidget({super.key});

  @override
  State<SearchWidget> createState() => _SearchWidgetState();
}

class _SearchWidgetState extends State<SearchWidget> {
  final TextEditingController searchController = TextEditingController();
  final _debouncer = Debouncer(delay: const Duration(milliseconds: 500));
  HomeProvider? _homeProvider;
  ConversationProvider? _convoProvider;

  @override
  void initState() {
    super.initState();
    // Seed from the provider so a rebuilt field never hides an active query (hub audit #23).
    searchController.text = context.read<ConversationProvider>().previousQuery;
  }

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

  ProductFailure _searchFailure(ConversationSearchResult result) {
    final statusCode = result.statusCode;
    if (statusCode == null) return ProductFailure.network;
    if (statusCode >= 500) return ProductFailure.server;
    return ProductFailure.invalidResponse;
  }

  bool _isCurrentSearchSurface(String value) {
    if (!mounted || searchController.text != value) return false;
    final route = ModalRoute.of(context);
    if (route != null && !route.isCurrent) return false;
    final homeProvider = _homeProvider;
    final conversationProvider = _convoProvider;
    if (homeProvider == null || conversationProvider == null || homeProvider.selectedIndex != 1) return false;
    return homeProvider.showConvoSearchBar || conversationProvider.previousQuery == value;
  }

  void _onChanged(String value) {
    var provider = Provider.of<ConversationProvider>(context, listen: false);
    _debouncer.run(() async {
      if (value.isEmpty) {
        await provider.searchConversations(value);
        return;
      }

      final attempt = ProductTelemetry.instance.start(ProductJourney.search, surface: ProductSurface.conversations);
      final result = await provider.searchConversations(value);
      if (!mounted || searchController.text != value) {
        attempt.complete(ProductOutcome.superseded);
        return;
      }

      if (!result.isSuccess) {
        attempt.complete(ProductOutcome.failure, failure: _searchFailure(result));
        return;
      }

      final resultCount = result.items.length;
      if (resultCount == 0) {
        attempt.complete(ProductOutcome.empty, resultCount: 0);
      } else {
        // The provider has updated the visible list. Keep the
        // first-result signal separate from transport completion.
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_isCurrentSearchSurface(value)) {
            attempt.firstResult();
            attempt.complete(ProductOutcome.success, resultCount: resultCount);
          } else {
            attempt.complete(ProductOutcome.superseded);
          }
        });
      }
      PlatformManager.instance.analytics.searchQueryEntered(value, resultCount);
    });
  }

  /// The clear X empties the query and, with no other search filter left, hides the bar.
  Future<void> _onCleared() async {
    _debouncer.cancel();
    final provider = Provider.of<ConversationProvider>(context, listen: false);
    final homeProvider = Provider.of<HomeProvider>(context, listen: false);
    await provider.searchConversations('');
    if (!provider.hasActiveSearch) homeProvider.hideConvoSearchBar();
    PlatformManager.instance.analytics.searchQueryCleared();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: OmiSearchField(
              controller: searchController,
              focusNode: context.read<HomeProvider>().convoSearchFieldFocusNode,
              placeholder: context.l10n.searchConversations,
              onTap: () => PlatformManager.instance.analytics.searchBarFocused(),
              onChanged: (value) {
                if (value.isEmpty) return; // the clear X handles an emptied field in _onCleared
                _onChanged(value);
              },
              onCleared: _onCleared,
            ),
          ),
          const SizedBox(width: OmiSpacing.xs),
          Selector<ConversationProvider, bool>(
            selector: (_, p) => p.selectedSpeakerId != null,
            builder: (context, isActive, _) => OmiIconButton.filled(
              key: const Key('conversation_speaker_filter'),
              diameter: kOmiMinTapTarget,
              fillColor: isActive ? OmiColors.accent : OmiColors.surface1,
              color: isActive ? OmiColors.onAccent : OmiColors.textSecondary,
              label: context.l10n.filterBySpeaker,
              icon: const Icon(Icons.person_search, size: 20),
              onPressed: () async {
                HapticFeedback.mediumImpact();
                await showSpeakerFilterSheet(context);
              },
            ),
          ),
          const SizedBox(width: OmiSpacing.xs),
          // One date filter for the list and the search (hub audit #23).
          Selector<ConversationProvider, bool>(
            selector: (_, p) => p.selectedStartDate != null,
            builder: (context, hasActiveFilter, _) => OmiIconButton.filled(
              key: const Key('conversation_date_filter'),
              diameter: kOmiMinTapTarget,
              fillColor: hasActiveFilter ? OmiColors.accent : OmiColors.surface1,
              color: hasActiveFilter ? OmiColors.onAccent : OmiColors.textSecondary,
              label: context.l10n.filterByDate,
              icon: FaIcon(hasActiveFilter ? FontAwesomeIcons.calendarDay : FontAwesomeIcons.calendarDays, size: 18),
              onPressed: () async {
                HapticFeedback.mediumImpact();
                await showConversationDateRangePicker(context);
              },
            ),
          ),
        ],
      ),
    );
  }
}

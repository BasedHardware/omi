import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

class DesktopSearchWidget extends StatefulWidget {
  const DesktopSearchWidget({super.key});

  @override
  State<DesktopSearchWidget> createState() => _DesktopSearchWidgetState();
}

class _DesktopSearchWidgetState extends State<DesktopSearchWidget> {
  final TextEditingController searchController = TextEditingController();
  final _debouncer = Debouncer(delay: const Duration(milliseconds: 500));
  final FocusNode _focusNode = FocusNode();
  bool _isExpanded = false;

  @override
  void initState() {
    super.initState();

    _focusNode.addListener(_onFocusChange);

    // Initialize search controller with current search query from provider
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = Provider.of<ConversationProvider>(context, listen: false);
      if (provider.previousQuery.isNotEmpty) {
        searchController.text = provider.previousQuery;
        setState(() => _isExpanded = true);
      }
    });
  }

  void _onFocusChange() {
    if (!_focusNode.hasFocus && searchController.text.isEmpty) {
      setState(() => _isExpanded = false);
    }
    setState(() {});
  }

  void _expandSearch() {
    setState(() => _isExpanded = true);
    Future.delayed(const Duration(milliseconds: 50), () {
      _focusNode.requestFocus();
    });
  }

  void _collapseSearch() {
    if (searchController.text.isEmpty) {
      setState(() => _isExpanded = false);
    }
  }

  @override
  void dispose() {
    searchController.dispose();
    _focusNode.removeListener(_onFocusChange);
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(
      builder: (context, provider, child) {
        final hasActiveSearch = provider.previousQuery.isNotEmpty;

        // If there's an active search, always show expanded
        if (hasActiveSearch && !_isExpanded) {
          _isExpanded = true;
        }

        return AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOutCubic,
          width: _isExpanded ? 240 : null,
          child: _isExpanded
              ? _buildSearchInput(provider)
              : _buildSearchButton(),
        );
      },
    );
  }

  Widget _buildSearchButton() {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: _expandSearch,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary,
              width: 1,
            ),
          ),
          child: const Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.search_rounded,
                size: 14,
                color: ResponsiveHelper.textTertiary,
              ),
              SizedBox(width: 8),
              Text(
                'Search',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  color: ResponsiveHelper.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSearchInput(ConversationProvider provider) {
    return Container(
      height: 38,
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: _focusNode.hasFocus
              ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.5)
              : ResponsiveHelper.backgroundTertiary,
          width: 1,
        ),
      ),
      child: Row(
        children: [
          const SizedBox(width: 12),
          Icon(
            Icons.search_rounded,
            size: 14,
            color: _focusNode.hasFocus ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: TextField(
              controller: searchController,
              focusNode: _focusNode,
              style: const TextStyle(
                fontSize: 13,
                color: ResponsiveHelper.textPrimary,
              ),
              decoration: const InputDecoration(
                hintText: 'Search...',
                hintStyle: TextStyle(
                  fontSize: 13,
                  color: ResponsiveHelper.textTertiary,
                ),
                border: InputBorder.none,
                isDense: true,
                contentPadding: EdgeInsets.symmetric(vertical: 10),
              ),
              onChanged: (value) {
                setState(() {});
                _debouncer.run(() async {
                  await provider.searchConversations(value);
                });
              },
            ),
          ),
          if (searchController.text.isNotEmpty)
            GestureDetector(
              onTap: () async {
                searchController.clear();
                await provider.searchConversations("");
                _collapseSearch();
                setState(() {});
              },
              child: Container(
                padding: const EdgeInsets.all(4),
                child: const Icon(
                  Icons.close_rounded,
                  size: 14,
                  color: ResponsiveHelper.textTertiary,
                ),
              ),
            ),
          const SizedBox(width: 8),
        ],
      ),
    );
  }
}

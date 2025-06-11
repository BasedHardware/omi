import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

/// Premium minimal search widget for desktop conversations
class DesktopSearchWidget extends StatefulWidget {
  const DesktopSearchWidget({super.key});

  @override
  State<DesktopSearchWidget> createState() => _DesktopSearchWidgetState();
}

class _DesktopSearchWidgetState extends State<DesktopSearchWidget> {
  final TextEditingController searchController = TextEditingController();
  final _debouncer = Debouncer(delay: const Duration(milliseconds: 500));
  final FocusNode _focusNode = FocusNode();
  bool showClearButton = false;
  bool _isFocused = false;

  @override
  void initState() {
    super.initState();
    _focusNode.addListener(() {
      setState(() {
        _isFocused = _focusNode.hasFocus;
      });
    });
  }

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
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
      constraints: const BoxConstraints(maxWidth: 600),
      child: Row(
        children: [
          // Premium search input with better contrast
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: _isFocused
                      ? ResponsiveHelper.purplePrimary.withOpacity(0.6)
                      : ResponsiveHelper.backgroundQuaternary,
                  width: 1,
                ),
                boxShadow: _isFocused
                    ? [
                        BoxShadow(
                          color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ]
                    : [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.1),
                          blurRadius: 4,
                          offset: const Offset(0, 1),
                        ),
                      ],
              ),
              child: TextFormField(
                controller: searchController,
                focusNode: _focusNode,
                onChanged: (value) {
                  var provider = Provider.of<ConversationProvider>(context, listen: false);
                  _debouncer.run(() async {
                    await provider.searchConversations(value);
                  });
                  setShowClearButton();
                },
                style: const TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 15,
                  fontWeight: FontWeight.w400,
                ),
                decoration: InputDecoration(
                  hintText: 'Search conversations...',
                  hintStyle: const TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 15,
                    fontWeight: FontWeight.w400,
                  ),
                  filled: false,
                  border: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  prefixIcon: Container(
                    width: 24,
                    height: 24,
                    margin: const EdgeInsets.only(left: 16, right: 12),
                    child: Center(
                      child: Icon(
                        Icons.search_rounded,
                        color: _isFocused ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                        size: 18,
                      ),
                    ),
                  ),
                  suffixIcon: showClearButton
                      ? Container(
                          width: 24,
                          height: 24,
                          margin: const EdgeInsets.only(right: 16),
                          child: Center(
                            child: Material(
                              color: Colors.transparent,
                              child: InkWell(
                                onTap: () async {
                                  var provider = Provider.of<ConversationProvider>(context, listen: false);
                                  await provider.searchConversations("");
                                  searchController.clear();
                                  setShowClearButton();
                                },
                                borderRadius: BorderRadius.circular(12),
                                child: Container(
                                  width: 20,
                                  height: 20,
                                  decoration: BoxDecoration(
                                    color: ResponsiveHelper.backgroundQuaternary,
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: const Icon(
                                    Icons.close_rounded,
                                    color: ResponsiveHelper.textSecondary,
                                    size: 12,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        )
                      : null,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 20,
                    vertical: 16,
                  ),
                ),
              ),
            ),
          ),

          const SizedBox(width: 12),

          // Filter button with improved contrast
          Consumer<ConversationProvider>(
            builder: (BuildContext context, ConversationProvider convoProvider, Widget? child) {
              bool isFiltered = convoProvider.showDiscardedConversations;

              return Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: convoProvider.toggleDiscardConversations,
                  borderRadius: BorderRadius.circular(12),
                  child: Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: isFiltered
                          ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
                          : ResponsiveHelper.backgroundTertiary,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: isFiltered
                            ? ResponsiveHelper.purplePrimary.withOpacity(0.4)
                            : ResponsiveHelper.backgroundQuaternary,
                        width: 1,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.1),
                          blurRadius: 4,
                          offset: const Offset(0, 1),
                        ),
                      ],
                    ),
                    child: Icon(
                      isFiltered ? Icons.filter_alt_off_rounded : Icons.filter_alt_rounded,
                      color: isFiltered ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                      size: 18,
                    ),
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

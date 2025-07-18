import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/ui/atoms/omi_search_input.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
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

  @override
  void initState() {
    super.initState();

    _focusNode.addListener(() => setState(() {}));

    // Initialize search controller with current search query from provider
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = Provider.of<ConversationProvider>(context, listen: false);
      if (provider.previousQuery.isNotEmpty) {
        searchController.text = provider.previousQuery;
      }
    });
  }

  @override
  void dispose() {
    searchController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(
      builder: (context, provider, child) {
        return Container(
          constraints: const BoxConstraints(maxWidth: 600),
          child: Row(
            children: [
              Expanded(
                child: OmiSearchInput(
                  controller: searchController,
                  focusNode: _focusNode,
                  hint: 'Search conversations...',
                  onChanged: (value) {
                    var provider = Provider.of<ConversationProvider>(context, listen: false);
                    _debouncer.run(() async {
                      await provider.searchConversations(value);
                    });
                  },
                  onClear: () async {
                    var provider = Provider.of<ConversationProvider>(context, listen: false);
                    searchController.clear();
                    await provider.searchConversations("");
                  },
                ),
              ),
              const SizedBox(width: 12),
              Consumer<ConversationProvider>(
                builder: (context, convoProvider, _) {
                  bool isFiltered = convoProvider.showDiscardedConversations;
                  return OmiIconButton(
                    icon: isFiltered ? Icons.filter_alt_off_rounded : Icons.filter_alt_rounded,
                    style: OmiIconButtonStyle.outline,
                    color: isFiltered ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                    onPressed: convoProvider.toggleDiscardConversations,
                  );
                },
              ),
            ],
          ),
        );
      },
    );
  }
}

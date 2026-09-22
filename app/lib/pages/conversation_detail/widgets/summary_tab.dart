import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/app_review_prompt.dart';

class SummaryTab extends StatefulWidget {
  final bool reviewEnabled;
  final String searchQuery;
  final int currentResultIndex;
  final VoidCallback? onTapWhenSearchEmpty;

  const SummaryTab(
      {super.key,
      this.reviewEnabled = false,
      this.searchQuery = '',
      this.currentResultIndex = -1,
      this.onTapWhenSearchEmpty});

  @override
  State<SummaryTab> createState() => _SummaryTabState();
}

class _SummaryTabState extends State<SummaryTab> with AutomaticKeepAliveClientMixin {
  bool _isEditing = false;
  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return GestureDetector(
      excludeFromSemantics: true,
      behavior: HitTestBehavior.translucent,
      onTap: () {
        FocusScope.of(context).unfocus();
        // If search is empty, call the callback to close search
        if (widget.searchQuery.isEmpty && widget.onTapWhenSearchEmpty != null) {
          widget.onTapWhenSearchEmpty!();
        }
      },
      child: Consumer<ConversationDetailProvider>(
        builder: (context, provider, child) {
          final conversation = provider.conversationOrNull;
          final discarded = conversation?.discarded ?? true;
          return AppReviewPrompt(
            contentId: conversation?.id ?? '',
            moment: AppReviewMoment.conversationRead,
            enabled: widget.reviewEnabled &&
                !_isEditing &&
                !provider.isLoading &&
                !provider.loadingReprocessConversation &&
                conversation?.status == ConversationStatus.completed &&
                !discarded &&
                provider.getSummarySelection().content.trim().isNotEmpty,
            child: Stack(
              children: [
                CustomScrollView(
                  keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.manual,
                  slivers: [
                    const SliverToBoxAdapter(child: GetSummaryWidgets()),
                    discarded
                        ? const SliverToBoxAdapter(child: ReprocessDiscardedWidget())
                        : GetAppsWidgets(
                            searchQuery: widget.searchQuery,
                            currentResultIndex: widget.currentResultIndex,
                            canStartEditing: () {
                              final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                              if (!connectivityProvider.isConnected) {
                                ConnectivityProvider.showNoInternetDialog(context);
                                return false;
                              }
                              return true;
                            },
                            onEditStarted: (_) {
                              setState(() => _isEditing = true);
                              PlatformManager.instance.analytics.editSummaryStarted();
                            },
                            onEditCancelled: (_) {
                              setState(() => _isEditing = false);
                              PlatformManager.instance.analytics.editSummaryCancelled();
                            },
                            onSaveSummarySelection: (selection, newContent) {
                              PlatformManager.instance.analytics.editSummarySaved();
                              context.read<ConversationDetailProvider>().saveEditingSummarySelection(
                                    selection,
                                    newContent,
                                  );
                            },
                          ),
                    const SliverToBoxAdapter(child: GetGeolocationWidgets()),
                    const SliverToBoxAdapter(child: SizedBox(height: 150)),
                  ],
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

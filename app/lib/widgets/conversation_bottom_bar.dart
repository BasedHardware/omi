import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/widgets/conversation_bottom_bar/tab_button.dart';
import 'package:provider/provider.dart';

enum ConversationBottomBarMode {
  recording, // During active recording (no summary icon)
  detail // For viewing completed conversations
}

enum ConversationTab { transcript, summary, action_items }

class ConversationBottomBar extends StatelessWidget {
  final ConversationBottomBarMode mode;
  final ConversationTab selectedTab;
  final Function(ConversationTab) onTabSelected;
  final VoidCallback onStopPressed;
  final bool hasSegments;

  const ConversationBottomBar({
    super.key,
    required this.mode,
    required this.selectedTab,
    required this.onTabSelected,
    required this.onStopPressed,
    this.hasSegments = true,
  });

  @override
  Widget build(BuildContext context) {
    if (!hasSegments) {
      return const SizedBox();
    }

    return Center(
      child: _buildBottomBar(context),
    );
  }

  Widget _buildBottomBar(BuildContext context) {
    return Material(
      elevation: 8,
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(28),
      child: Container(
        height: 56,
        width: mode == ConversationBottomBarMode.recording ? 180 : 290,
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(28),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.3),
              spreadRadius: 1,
              blurRadius: 5,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            // Transcript tab
            _buildTranscriptTab(),

            // Stop button or Summary tab
            if (mode == ConversationBottomBarMode.recording) _buildStopButton() else _buildSummaryTab(context),

            // Action Items tab (only in detail mode)
            if (mode == ConversationBottomBarMode.detail) _buildActionItemsTab(),
          ],
        ),
      ),
    );
  }

  Widget _buildTranscriptTab() {
    return TabButton(
      icon: Icons.graphic_eq_rounded,
      isSelected: selectedTab == ConversationTab.transcript,
      onTap: () => onTabSelected(ConversationTab.transcript),
    );
  }

  Widget _buildStopButton() {
    return Container(
      height: 40,
      width: 40,
      decoration: BoxDecoration(
        color: Colors.red,
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: Colors.red.withOpacity(0.4),
            spreadRadius: 1,
            blurRadius: 4,
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: onStopPressed,
          child: const Icon(
            Icons.stop_rounded,
            color: Colors.white,
            size: 24,
          ),
        ),
      ),
    );
  }

  Widget _buildSummaryTab(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, _) {
        final summarizedApp = provider.getSummarizedApp();
        final app = summarizedApp != null
            ? provider.appsList.firstWhereOrNull((element) => element.id == summarizedApp.appId)
            : null;

        return _buildSummaryTabContent(context, provider, app);
      },
    );
  }

  Widget _buildSummaryTabContent(BuildContext context, ConversationDetailProvider provider, App? app) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, detailProvider, _) {
        final isReprocessing = detailProvider.loadingReprocessConversation;
        final reprocessingApp = detailProvider.selectedAppForReprocessing;

        return TabButton(
          icon: null,
          customIcon: app == null && reprocessingApp == null
              ? SvgPicture.asset(
                  Assets.images.aiMagic.path,
                  color: Colors.white,
                )
              : null,
          isSelected: selectedTab == ConversationTab.summary,
          onTap: () => onTabSelected(ConversationTab.summary),
          label: isReprocessing ? (reprocessingApp?.name ?? "Auto") : (app?.name ?? "Summary"),
          appImage: isReprocessing
              ? (reprocessingApp != null ? reprocessingApp.getImageUrl() : Assets.images.herologo.path)
              : (app != null ? app.getImageUrl() : null),
          isLocalAsset: isReprocessing && reprocessingApp == null,
          showDropdownArrow: selectedTab == ConversationTab.summary,
          isLoading: isReprocessing,
          onDropdownPressed: () {
            showModalBottomSheet(
              context: context,
              isScrollControlled: true,
              backgroundColor: Colors.transparent,
              builder: (context) => const SummarizedAppsBottomSheet(),
            );
          },
        );
      },
    );
  }

  Widget _buildActionItemsTab() {
    return TabButton(
      icon: Icons.check_circle_outline,
      isSelected: selectedTab == ConversationTab.action_items,
      onTap: () => onTabSelected(ConversationTab.action_items),
    );
  }
}

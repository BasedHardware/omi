import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
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

enum ConversationTab { transcript, summary, actionItems }

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
        width: mode == ConversationBottomBarMode.recording ? 180 : null,
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
        decoration: BoxDecoration(
          color: const Color(0xFF1A0B2E), // Very deep purple
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
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Transcript tab
            _buildTranscriptTab(),

            // Add minimal spacing between tabs
            const SizedBox(width: 4),

            // Stop button or Summary/Action Items tabs
            ...switch (mode) {
              ConversationBottomBarMode.recording => [_buildStopButton()],
              ConversationBottomBarMode.detail => [
                  _buildSummaryTab(context),
                  const SizedBox(width: 4),
                  _buildActionItemsTab(),
                ],
              _ => [_buildSummaryTab(context)],
            },
          ],
        ),
      ),
    );
  }

  Widget _buildTranscriptTab() {
    return TabButton(
      icon: FontAwesomeIcons.solidComments,
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

        void handleTap() {
          if (selectedTab == ConversationTab.summary) {
            showModalBottomSheet(
              context: context,
              isScrollControlled: true,
              backgroundColor: Colors.transparent,
              builder: (context) => const SummarizedAppsBottomSheet(),
            );
          } else {
            onTabSelected(ConversationTab.summary);
          }
        }

        return TabButton(
          icon: null,
          customIcon: app == null && reprocessingApp == null
              ? SvgPicture.asset(
                  Assets.images.aiMagic,
                  color: Colors.white,
                )
              : null,
          isSelected: selectedTab == ConversationTab.summary,
          onTap: handleTap,
          label: null, // Remove the label to show only icon + dropdown
          appImage: isReprocessing
              ? (reprocessingApp != null ? reprocessingApp.getImageUrl() : Assets.images.herologo.path)
              : (app != null ? app.getImageUrl() : null),
          isLocalAsset: isReprocessing && reprocessingApp == null,
          showDropdownArrow: true, // Always show dropdown arrow
          isLoading: isReprocessing,
          onDropdownPressed: handleTap,
        );
      },
    );
  }

  Widget _buildActionItemsTab() {
    return TabButton(
      icon: FontAwesomeIcons.listCheck,
      isSelected: selectedTab == ConversationTab.actionItems,
      onTap: () => onTabSelected(ConversationTab.actionItems),
    );
  }
}

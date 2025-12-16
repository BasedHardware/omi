import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
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
  final bool hasActionItems;

  const ConversationBottomBar({
    super.key,
    required this.mode,
    required this.selectedTab,
    required this.onTabSelected,
    required this.onStopPressed,
    this.hasSegments = true,
    this.hasActionItems = true,
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
    if (mode == ConversationBottomBarMode.recording) {
      return _buildRecordingBar();
    }
    return _buildDetailBar(context);
  }

  Widget _buildRecordingBar() {
    return Material(
      elevation: 8,
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(28),
      child: Container(
        height: 56,
        width: 180,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: const Color(0xFF1A0B2E),
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
            _buildCircularButton(
              icon: FontAwesomeIcons.solidComments,
              isSelected: selectedTab == ConversationTab.transcript,
              onTap: () => onTabSelected(ConversationTab.transcript),
            ),
            const SizedBox(width: 8),
            _buildStopButton(),
          ],
        ),
      ),
    );
  }

  Widget _buildDetailBar(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        // Left: Transcript circular button
        _buildCircularButton(
          icon: FontAwesomeIcons.solidComments,
          isSelected: selectedTab == ConversationTab.transcript,
          onTap: () => onTabSelected(ConversationTab.transcript),
        ),

        const SizedBox(width: 8),

        // Center: Summary pill with app icon + name
        _buildSummaryPill(context),

        // Right: Action items circular button (if available)
        if (hasActionItems) ...[
          const SizedBox(width: 8),
          _buildCircularButton(
            icon: FontAwesomeIcons.listCheck,
            isSelected: selectedTab == ConversationTab.actionItems,
            onTap: () => onTabSelected(ConversationTab.actionItems),
          ),
        ],
      ],
    );
  }

  Widget _buildCircularButton({
    required IconData icon,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Material(
      elevation: 4,
      color: Colors.transparent,
      shape: const CircleBorder(),
      child: Container(
        height: 56,
        width: 56,
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFF6B46C1) : const Color(0xFF2D1B4E),
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.3),
              spreadRadius: 1,
              blurRadius: 5,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Material(
          color: Colors.transparent,
          shape: const CircleBorder(),
          child: InkWell(
            borderRadius: BorderRadius.circular(28),
            onTap: () {
              HapticFeedback.mediumImpact();
              onTap();
            },
            child: Center(
              child: FaIcon(
                icon,
                color: isSelected ? Colors.white : Colors.grey.shade400,
                size: 22,
              ),
            ),
          ),
        ),
      ),
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

  Widget _buildSummaryPill(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, _) {
        final summarizedApp = provider.getSummarizedApp();
        final app = summarizedApp != null
            ? provider.appsList.firstWhereOrNull((element) => element.id == summarizedApp.appId)
            : null;

        return _buildSummaryPillContent(context, provider, app, hasActionItems);
      },
    );
  }

  Widget _buildSummaryPillContent(
      BuildContext context, ConversationDetailProvider provider, App? app, bool showActionItems) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, detailProvider, _) {
        final isReprocessing = detailProvider.loadingReprocessConversation;
        final reprocessingApp = detailProvider.selectedAppForReprocessing;

        void handleTap() {
          HapticFeedback.mediumImpact();
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

        // Get the app name to display
        String displayName = 'Summary';
        if (isReprocessing && reprocessingApp != null) {
          displayName = reprocessingApp.name;
        } else if (app != null) {
          displayName = app.name;
        }

        // Clip name: 8 chars if action items shown, 15 chars otherwise
        final maxChars = showActionItems ? 8 : 15;
        if (displayName.length > maxChars) {
          displayName = '${displayName.substring(0, maxChars)}...';
        }

        // Get app image URL
        String? appImageUrl;
        bool isLocalAsset = false;
        if (isReprocessing) {
          if (reprocessingApp != null) {
            appImageUrl = reprocessingApp.getImageUrl();
          } else {
            appImageUrl = Assets.images.herologo.path;
            isLocalAsset = true;
          }
        } else if (app != null) {
          appImageUrl = app.getImageUrl();
        }

        final isSelected = selectedTab == ConversationTab.summary;

        return Material(
          elevation: 4,
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(28),
          child: Container(
            height: 56,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            decoration: BoxDecoration(
              color: isSelected ? const Color(0xFF6B46C1) : const Color(0xFF2D1B4E),
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
            child: Material(
              color: Colors.transparent,
              borderRadius: BorderRadius.circular(28),
              child: InkWell(
                borderRadius: BorderRadius.circular(28),
                onTap: handleTap,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // App icon or default icon
                    _buildAppIcon(appImageUrl, isLocalAsset, isReprocessing),

                    const SizedBox(width: 10),

                    // App name
                    Text(
                      displayName,
                      style: TextStyle(
                        color: isSelected ? Colors.white : Colors.grey.shade300,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),

                    const SizedBox(width: 4),

                    // Dropdown arrow
                    Icon(
                      Icons.keyboard_arrow_down,
                      color: isSelected ? Colors.white : Colors.grey.shade400,
                      size: 20,
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildAppIcon(String? imageUrl, bool isLocalAsset, bool isLoading) {
    const double size = 28;

    if (isLoading) {
      return SizedBox(
        width: size,
        height: size,
        child: const CircularProgressIndicator(
          strokeWidth: 2,
          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
        ),
      );
    }

    if (imageUrl == null) {
      return SizedBox(
        width: size,
        height: size,
        child: SvgPicture.asset(
          Assets.images.aiMagic,
          colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
        ),
      );
    }

    if (isLocalAsset) {
      return Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(size / 2),
          image: DecorationImage(
            image: AssetImage(imageUrl),
            fit: BoxFit.cover,
          ),
        ),
      );
    }

    return CachedNetworkImage(
      imageUrl: imageUrl,
      imageBuilder: (context, imageProvider) {
        return Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            image: DecorationImage(
              image: imageProvider,
              fit: BoxFit.cover,
            ),
          ),
        );
      },
      errorWidget: (context, url, error) {
        return SizedBox(
          width: size,
          height: size,
          child: SvgPicture.asset(
            Assets.images.aiMagic,
            colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
          ),
        );
      },
      placeholder: (context, url) => SizedBox(
        width: size,
        height: size,
        child: const CircularProgressIndicator(
          strokeWidth: 2,
          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
        ),
      ),
    );
  }
}

import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

enum ConversationBottomBarMode {
  recording, // During active recording (no summary icon)
  detail // For viewing completed conversations
}

enum ConversationTab { transcript, summary }

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

    // Use a Positioned widget inside a Stack in the parent widget
    return Container(
      child: Center(
        child: Material(
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
                // Transcript icon with pill indicator
                _buildTabButton(
                  context: context,
                  icon: Icons.graphic_eq_rounded,
                  isSelected: selectedTab == ConversationTab.transcript,
                  onTap: () => onTabSelected(ConversationTab.transcript),
                ),

                // Stop button - only show in recording mode
                if (mode == ConversationBottomBarMode.recording)
                  Container(
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
                  ),

                // Summary icon or App icon - only show in detail mode
                if (mode == ConversationBottomBarMode.detail)
                  Consumer<ConversationDetailProvider>(
                    builder: (context, provider, child) {
                      final summarizedApp = provider.getSummarizedApp();
                      final app = summarizedApp != null
                          ? provider.appsList.firstWhereOrNull((element) => element.id == summarizedApp.appId)
                          : null;

                      return Row(
                        children: [
                          Consumer<ConversationDetailProvider>(builder: (context, detailProvider, _) {
                            final isReprocessing = detailProvider.loadingReprocessConversation;
                            final reprocessingApp = detailProvider.selectedAppForReprocessing;

                            return _buildTabButton(
                              context: context,
                              icon: app == null && reprocessingApp == null ? Icons.sticky_note_2 : null,
                              isSelected: selectedTab == ConversationTab.summary,
                              onTap: () => onTabSelected(ConversationTab.summary),
                              label: isReprocessing && reprocessingApp != null ? reprocessingApp.name : app?.name,
                              appImage: isReprocessing && reprocessingApp != null
                                  ? reprocessingApp.getImageUrl()
                                  : (app != null ? app.getImageUrl() : null),
                              showDropdownArrow: selectedTab == ConversationTab.summary,
                              isLoading: isReprocessing,
                              onDropdownPressed: () {
                                showModalBottomSheet(
                                  context: context,
                                  isScrollControlled: true,
                                  backgroundColor: Colors.transparent,
                                  builder: (context) => _buildSummarizedAppsSheet(context),
                                );
                              },
                            );
                          }),
                        ],
                      );
                    },
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSummarizedAppsSheet(BuildContext context) {
    return const SummarizedAppsBottomSheet();
  }

  Widget _buildTabButton({
    required BuildContext context,
    IconData? icon,
    required bool isSelected,
    required VoidCallback onTap,
    String? label,
    String? appImage,
    bool showDropdownArrow = false,
    bool isLoading = false,
    VoidCallback? onDropdownPressed,
  }) {
    return Container(
      width: label != null ? 120 : 80,
      height: 40,
      decoration: BoxDecoration(
        color: isSelected ? Colors.deepPurple.withOpacity(0.3) : Colors.transparent,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: showDropdownArrow ? onDropdownPressed : onTap,
          child: Center(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (icon != null)
                  Icon(
                    icon,
                    color: isSelected ? Colors.white : Colors.grey.shade400,
                    size: 24,
                  )
                else if (appImage != null)
                  isLoading
                      ? Container(
                          width: 24,
                          height: 24,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: Colors.transparent,
                          ),
                          child: Stack(
                            alignment: Alignment.center,
                            children: [
                              if (appImage != null)
                                Opacity(
                                  opacity: 0.5,
                                  child: CachedNetworkImage(
                                    imageUrl: appImage,
                                    imageBuilder: (context, imageProvider) => Container(
                                      width: 24,
                                      height: 24,
                                      decoration: BoxDecoration(
                                        shape: BoxShape.circle,
                                        image: DecorationImage(
                                          image: imageProvider,
                                          fit: BoxFit.cover,
                                        ),
                                      ),
                                    ),
                                    errorWidget: (context, url, error) => Container(
                                      width: 24,
                                      height: 24,
                                      decoration: BoxDecoration(
                                        shape: BoxShape.circle,
                                        color: Colors.grey.shade800,
                                      ),
                                      child: const Icon(Icons.error_outline, size: 16, color: Colors.white),
                                    ),
                                  ),
                                ),
                              SizedBox(
                                width: 24,
                                height: 24,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                ),
                              ),
                            ],
                          ),
                        )
                      : CachedNetworkImage(
                          imageUrl: appImage,
                          imageBuilder: (context, imageProvider) => Container(
                            width: 24,
                            height: 24,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              image: DecorationImage(
                                image: imageProvider,
                                fit: BoxFit.cover,
                              ),
                            ),
                          ),
                          placeholder: (context, url) => Container(
                            width: 24,
                            height: 24,
                            decoration: const BoxDecoration(
                              shape: BoxShape.circle,
                              color: Colors.grey,
                            ),
                            child: const Center(
                              child: SizedBox(
                                width: 12,
                                height: 12,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                ),
                              ),
                            ),
                          ),
                          errorWidget: (context, url, error) => Container(
                            width: 24,
                            height: 24,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: Colors.grey.shade800,
                            ),
                            child: const Icon(Icons.error_outline, size: 16, color: Colors.white),
                          ),
                        ),
                if (label != null) ...[
                  const SizedBox(width: 4),
                  Flexible(
                    child: Container(
                      width: 60,
                      child: ShaderMask(
                        shaderCallback: (Rect bounds) {
                          return LinearGradient(
                            begin: Alignment.centerLeft,
                            end: Alignment.centerRight,
                            colors: [Colors.white, Colors.transparent],
                            stops: [0.8, 1.0],
                          ).createShader(bounds);
                        },
                        blendMode: BlendMode.dstIn,
                        child: Text(
                          label,
                          style: TextStyle(
                            color: isSelected ? Colors.white : Colors.grey.shade400,
                            fontSize: 12,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.clip,
                        ),
                      ),
                    ),
                  ),
                ],
                if (showDropdownArrow) ...[
                  const SizedBox(width: 2),
                  Icon(
                    Icons.keyboard_arrow_down,
                    color: Colors.white,
                    size: 16,
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

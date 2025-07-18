import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/chat/widgets/markdown_message_widget.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/ui/atoms/omi_button.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/atoms/omi_avatar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:omi/ui/molecules/omi_empty_state.dart';
import 'package:omi/ui/molecules/omi_panel_header.dart';

class DesktopConversationSummary extends StatelessWidget {
  final ServerConversation conversation;

  const DesktopConversationSummary({
    super.key,
    required this.conversation,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        final summarizedApp = provider.getSummarizedApp();
        final hasOverview = conversation.structured.overview.isNotEmpty;

        if (!hasOverview && conversation.appResults.isEmpty && summarizedApp == null) {
          return _buildEmptyState(context, provider);
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Summary header with app selection
            _buildSummaryHeader(context, provider, summarizedApp),
            const SizedBox(height: 16),

            // App summary result (if available)
            if (summarizedApp != null) ...[
              _buildAppSummaryCard(context, summarizedApp, provider),
              if (hasOverview || conversation.appResults.isNotEmpty) const SizedBox(height: 24),
            ],

            // Overview section
            if (hasOverview) ...[
              _buildSectionHeader('Overview', FontAwesomeIcons.lightbulb),
              const SizedBox(height: 12),
              _buildContentCard(context, conversation.structured.overview.decodeString),
            ],

            // Other app results section (if any beyond the main summarized app)
            if (conversation.appResults.where((result) => result != summarizedApp).isNotEmpty) ...[
              if (hasOverview || summarizedApp != null) const SizedBox(height: 24),
              _buildSectionHeader('Other App Results', FontAwesomeIcons.robot),
              const SizedBox(height: 12),
              ...conversation.appResults.where((result) => result != summarizedApp).map((result) => Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    child: _buildAppResultCard(context, result),
                  )),
            ],
          ],
        );
      },
    );
  }

  Widget _buildSummaryHeader(BuildContext context, ConversationDetailProvider provider, AppResponse? summarizedApp) {
    final app = summarizedApp != null
        ? provider.appsList.firstWhereOrNull((element) => element.id == summarizedApp.appId)
        : null;
    final isReprocessing = provider.loadingReprocessConversation;
    final reprocessingApp = provider.selectedAppForReprocessing;

    return Row(
      children: [
        // Summary title with app info
        Expanded(
          child: Row(
            children: [
              const Icon(
                FontAwesomeIcons.solidStar,
                color: ResponsiveHelper.textSecondary,
                size: 16,
              ),
              const SizedBox(width: 8),
              const Text(
                'Summary',
                style: TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (isReprocessing || app != null) ...[
                const SizedBox(width: 8),
                const Text(
                  '•',
                  style: TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 16,
                  ),
                ),
                const SizedBox(width: 8),
                if (isReprocessing) ...[
                  if (reprocessingApp != null) ...[
                    Container(
                      width: 16,
                      height: 16,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(4),
                        image: DecorationImage(
                          image: CachedNetworkImageProvider(reprocessingApp.getImageUrl()),
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      reprocessingApp.name,
                      style: const TextStyle(
                        color: ResponsiveHelper.textSecondary,
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ] else ...[
                    Container(
                      width: 16,
                      height: 16,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(4),
                        image: DecorationImage(
                          image: AssetImage(Assets.images.herologo.path),
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                    const SizedBox(width: 6),
                    const Text(
                      'Auto',
                      style: TextStyle(
                        color: ResponsiveHelper.textSecondary,
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                  const SizedBox(width: 8),
                  const SizedBox(
                    width: 12,
                    height: 12,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
                    ),
                  ),
                ] else if (app != null) ...[
                  Container(
                    width: 16,
                    height: 16,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(4),
                      image: DecorationImage(
                        image: CachedNetworkImageProvider(app.getImageUrl()),
                        fit: BoxFit.cover,
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    app.name,
                    style: const TextStyle(
                      color: ResponsiveHelper.textSecondary,
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ],
            ],
          ),
        ),

        // App selection dropdown
        OmiButton(
          label: 'Apps',
          type: OmiButtonType.neutral,
          icon: FontAwesomeIcons.chevronDown,
          enabled: !isReprocessing,
          onPressed: () => _showAppSelectionSheet(context, provider),
        ),

        // Copy button (if has content)
        if (summarizedApp != null && summarizedApp.content.trim().isNotEmpty) ...[
          const SizedBox(width: 8),
          OmiIconButton(
            icon: FontAwesomeIcons.copy,
            style: OmiIconButtonStyle.neutral,
            size: 28,
            iconSize: 12,
            borderRadius: 8,
            onPressed: () => _copySummary(context, summarizedApp, provider),
          ),
        ],
      ],
    );
  }

  Widget _buildAppSummaryCard(BuildContext context, AppResponse summarizedApp, ConversationDetailProvider provider) {
    final app = provider.appsList.firstWhereOrNull((element) => element.id == summarizedApp.appId);
    final content = summarizedApp.content.trim().decodeString;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (content.isEmpty) ...[
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'No summary available for this app. Try another app for better results.',
                    style: TextStyle(
                      color: ResponsiveHelper.textTertiary,
                      fontSize: 14,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                OmiButton(
                  label: 'Try Another App',
                  type: OmiButtonType.neutral,
                  enabled: true,
                  onPressed: () => _showAppSelectionSheet(context, provider),
                  icon: FontAwesomeIcons.chevronDown,
                ),
              ],
            ),
          ] else ...[
            SelectionArea(
              child: getMarkdownWidget(context, content),
            ),
            if (app != null) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 20,
                      height: 20,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(4),
                        image: DecorationImage(
                          image: CachedNetworkImageProvider(app.getImageUrl()),
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'Generated by ${app.name}',
                      style: const TextStyle(
                        color: ResponsiveHelper.textTertiary,
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String title, IconData icon) {
    return Row(
      children: [
        OmiIconButton(
          icon: icon,
          style: OmiIconButtonStyle.neutral,
          size: 24,
          iconSize: 12,
          borderRadius: 6,
          onPressed: null,
        ),
        const SizedBox(width: 8),
        Text(
          title,
          style: const TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }

  Widget _buildContentCard(BuildContext context, String content) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: SelectionArea(
        child: getMarkdownWidget(context, content),
      ),
    );
  }

  Widget _buildAppResultCard(BuildContext context, AppResponse result) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const OmiAvatar(
                size: 20,
                fallback: Icon(FontAwesomeIcons.robot, size: 10, color: ResponsiveHelper.purplePrimary),
              ),
              const SizedBox(width: 8),
              Text(
                result.appId ?? 'Unknown App',
                style: const TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SelectionArea(
            child: getMarkdownWidget(context, result.content.decodeString),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState(BuildContext context, ConversationDetailProvider provider) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        children: [
          const OmiEmptyState(
            icon: FontAwesomeIcons.fileAlt,
            title: 'No Summary Available',
            message: 'This conversation doesn\'t have a summary yet.',
          ),
          if (!conversation.discarded) ...[
            const SizedBox(height: 24),
            OmiButton(
              label: 'Generate Summary',
              type: OmiButtonType.primary,
              onPressed: () => _showAppSelectionSheet(context, provider),
              icon: FontAwesomeIcons.wandMagicSparkles,
            ),
          ],
        ],
      ),
    );
  }

  void _showAppSelectionSheet(BuildContext context, ConversationDetailProvider provider) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => _DesktopAppSelectionSheet(provider: provider),
    );
  }

  void _copySummary(BuildContext context, AppResponse summarizedApp, ConversationDetailProvider provider) {
    final content = summarizedApp.content.decodeString;
    Clipboard.setData(ClipboardData(text: content));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Summary copied to clipboard'),
        backgroundColor: ResponsiveHelper.purplePrimary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        duration: const Duration(seconds: 2),
      ),
    );
    MixpanelManager().copiedConversationDetails(provider.conversation, source: 'App Response');
  }
}

class _DesktopAppSelectionSheet extends StatelessWidget {
  final ConversationDetailProvider provider;

  const _DesktopAppSelectionSheet({
    required this.provider,
  });

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.7,
      minChildSize: 0.5,
      maxChildSize: 0.9,
      expand: false,
      builder: (context, scrollController) {
        final summarizedApp = provider.getSummarizedApp();
        final currentAppId = summarizedApp?.appId;
        final conversationId = provider.conversation.id;

        MixpanelManager().summarizedAppSheetViewed(
          conversationId: conversationId,
          currentSummarizedAppId: currentAppId,
        );

        return Container(
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundSecondary,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
              width: 1,
            ),
          ),
          child: Column(
            children: [
              // Header
              OmiPanelHeader(
                icon: FontAwesomeIcons.solidStar,
                title: 'Choose Summarization App',
                onClose: () => Navigator.pop(context),
              ),

              // Apps list
              Expanded(
                child: ListView(
                  controller: scrollController,
                  padding: const EdgeInsets.all(16),
                  children: [
                    // Auto option
                    _AppSelectionItem(
                      app: null,
                      isSelected: currentAppId == null,
                      onTap: () => _handleAutoAppTap(context),
                      trailingIcon: const Icon(
                        FontAwesomeIcons.wandMagicSparkles,
                        color: ResponsiveHelper.textSecondary,
                        size: 16,
                      ),
                    ),

                    const SizedBox(height: 8),

                    // Installed apps
                    ...provider.appsList.where((app) => app.worksWithMemories() && app.enabled).map(
                          (app) => _AppSelectionItem(
                            app: app,
                            isSelected: app.id == currentAppId,
                            onTap: () => _handleAppTap(context, app),
                          ),
                        ),

                    const SizedBox(height: 16),

                    // Enable Apps option
                    Material(
                      color: Colors.transparent,
                      child: InkWell(
                        onTap: () {
                          Navigator.pop(context);
                          MixpanelManager().summarizedAppEnableAppsClicked(conversationId: conversationId);
                          routeToPage(context, const AppsPage(showAppBar: true));
                        },
                        borderRadius: BorderRadius.circular(12),
                        child: Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                              width: 1,
                            ),
                          ),
                          child: const Row(
                            children: [
                              Icon(
                                FontAwesomeIcons.store,
                                color: ResponsiveHelper.textSecondary,
                                size: 16,
                              ),
                              SizedBox(width: 12),
                              Text(
                                'Enable More Apps',
                                style: TextStyle(
                                  color: ResponsiveHelper.textPrimary,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                              Spacer(),
                              Icon(
                                FontAwesomeIcons.chevronRight,
                                color: ResponsiveHelper.textTertiary,
                                size: 12,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  void _handleAutoAppTap(BuildContext context) async {
    Navigator.pop(context);
    final previousAppId = provider.getSummarizedApp()?.appId;
    final conversationId = provider.conversation.id;

    MixpanelManager().summarizedAppSelected(
      conversationId: conversationId,
      selectedAppId: 'auto',
      previousAppId: previousAppId,
    );

    provider.clearSelectedAppForReprocessing();
    await provider.reprocessConversation();
  }

  void _handleAppTap(BuildContext context, App app) async {
    final currentAppId = provider.getSummarizedApp()?.appId;

    if (app.id != currentAppId) {
      Navigator.pop(context);

      final previousAppId = provider.getSummarizedApp()?.appId;
      final conversationId = provider.conversation.id;

      MixpanelManager().summarizedAppSelected(
        conversationId: conversationId,
        selectedAppId: app.id,
        previousAppId: previousAppId,
      );

      provider.setSelectedAppForReprocessing(app);
      provider.setPreferredSummarizationApp(app.id);
      await provider.reprocessConversation(appId: app.id);
    }
  }
}

class _AppSelectionItem extends StatelessWidget {
  final App? app;
  final bool isSelected;
  final VoidCallback onTap;
  final Widget? trailingIcon;

  const _AppSelectionItem({
    required this.app,
    required this.isSelected,
    required this.onTap,
    this.trailingIcon,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: isSelected
                  ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
                  : ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: isSelected
                    ? ResponsiveHelper.purplePrimary.withOpacity(0.3)
                    : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                width: 1,
              ),
            ),
            child: Row(
              children: [
                // App icon
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(8),
                    image: app != null
                        ? DecorationImage(
                            image: CachedNetworkImageProvider(app!.getImageUrl()),
                            fit: BoxFit.cover,
                          )
                        : DecorationImage(
                            image: AssetImage(Assets.images.herologo.path),
                            fit: BoxFit.cover,
                          ),
                  ),
                ),

                const SizedBox(width: 12),

                // App details
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        app?.name ?? 'Auto',
                        style: const TextStyle(
                          color: ResponsiveHelper.textPrimary,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (app != null) ...[
                        const SizedBox(height: 2),
                        Text(
                          app!.description.decodeString,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: ResponsiveHelper.textTertiary,
                            fontSize: 12,
                          ),
                        ),
                      ] else ...[
                        const SizedBox(height: 2),
                        const Text(
                          'Let Omi choose the best app automatically',
                          style: TextStyle(
                            color: ResponsiveHelper.textTertiary,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),

                const SizedBox(width: 12),

                // Selection indicator or trailing icon
                if (isSelected)
                  const Icon(
                    FontAwesomeIcons.circleCheck,
                    color: ResponsiveHelper.purplePrimary,
                    size: 16,
                  )
                else if (trailingIcon != null)
                  trailingIcon!,
              ],
            ),
          ),
        ),
      ),
    );
  }
}

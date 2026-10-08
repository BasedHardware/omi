part of 'app_detail.dart';

/// Presentation only. All enable, consent, setup, payment and review mutations use the page owner.
extension _NativeAppDetailPresentation on _AppDetailPageState {
  Widget _nativeDetail(Widget classic) {
    final l10n = context.l10n;
    final primary = _buildPrimaryAction(l10n) as OmiButton;
    final isOwner = app.isOwner(SharedPreferencesUtil().uid);
    final provider = context.read<AppProvider>();
    final steps = app.worksExternally() ? app.externalIntegration?.authSteps ?? <AuthStep>[] : <AuthStep>[];
    final capabilities = app
        .getCapabilitiesFromIds(context.read<AddAppProvider>().capabilities)
        .where((capability) => capability.id != 'external_integration')
        .toList();
    if (app.chatTools?.isNotEmpty == true) {
      if (!capabilities.any((capability) => capability.id == 'chat')) {
        final chat =
            context.read<AddAppProvider>().capabilities.firstWhereOrNull((capability) => capability.id == 'chat');
        if (chat != null) capabilities.add(chat);
      }
      if (!capabilities.any((capability) => capability.id == 'push_to_talk')) {
        capabilities.add(AppCapability(title: l10n.pushToTalk, id: 'push_to_talk'));
      }
    }
    final permissions = AppPermissionsCard(app: app).presentationLabels(context);
    void openReviews() {
      final recent = app.reviews.sorted((a, b) => b.ratedAt.compareTo(a.ratedAt)).take(3).toList();
      // The native sheet hosts the section's own surface or editor; the Flutter sheet keeps the classic section.
      showOmiSheet<void>(
          context: context,
          title: l10n.ratingsAndReviews,
          builder: (_) => SingleChildScrollView(
              child: RecentReviewsSection(
                  app: app, userReview: app.userReview, reviews: recent, onReviewUpdated: _refreshAfterNativeReview)),
          nativeBuilder: (_) => RecentReviewsSection(
              nativePage: true,
              app: app,
              userReview: app.userReview,
              reviews: recent,
              onReviewUpdated: _refreshAfterNativeReview));
    }

    return IosNativeSurface(
      title: app.name.decodeString,
      fallback: classic,
      loading: isLoading || appLoading,
      toolbar: [
        NativeRow('app_detail_back', l10n.back,
            symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
        if (app.enabled && app.worksWithChat())
          NativeRow('app_detail_chat', l10n.chatWithApp(app.name.decodeString),
              symbol: 'bubble.left', enabled: !chatButtonLoading, action: (_) => _openChatWithApp()),
        if (app.enabled && app.externalIntegration?.appHomeUrl?.isNotEmpty == true)
          NativeRow('app_detail_settings', l10n.appSettingsLabel(app.name.decodeString),
              symbol: 'gearshape', action: (_) => routeToPage(context, AppHomeWebPage(app: app))),
        if (!isLoading && !app.private)
          NativeRow('app_detail_share', l10n.share, symbol: 'square.and.arrow.up', action: (_) => _shareApp(context)),
        if (provider.isAppOwner && !isLoading)
          NativeRow('app_detail_options', l10n.appOptions,
              symbol: 'ellipsis', action: (_) => showAppOptionsSheet(context, app)),
      ],
      sections: [
        NativeSection('app_detail_summary', [
          NativeRow('app_detail_identity', app.name.decodeString,
              kind: 'label',
              imageUri: nativeImageUri(app.getImageUrl()),
              subtitle: [
                app.author.decodeString,
                if (app.ratingCount > 0) '${app.getRatingAvg() ?? ''} · ${l10n.appRatingCount(app.ratingCount)}',
                if (app.installs > 0) l10n.appUsersCount(app.installs)
              ].join('\n')),
          NativeRow('app_detail_enable', primary.label,
              enabled: primary.onPressed != null && !primary.isLoading,
              action: primary.onPressed == null ? null : (_) => primary.onPressed!()),
          if (!isLoading && !app.private && app.isPaid && _hasActiveSubscription() && !provider.isAppOwner)
            NativeRow('app_detail_cancel', l10n.cancelSubscriptionButton,
                destructive: true, enabled: !_isCancelingSubscription, action: (_) => _confirmCancelSubscription()),
          if ((app.isUnderReview() || app.private) && !isOwner)
            NativeRow('app_detail_beta', l10n.betaTesterMessage, kind: 'label'),
          if (app.isUnderReview() && !app.private && isOwner)
            NativeRow('app_detail_review_notice', l10n.appUnderReviewMessage, kind: 'label'),
          if (app.isRejected()) NativeRow('app_detail_rejected', l10n.appRejectedMessage, kind: 'label'),
          if (app.isDisabled()) ...[
            NativeRow('app_detail_disabled', l10n.appDisabledTitle,
                kind: 'label',
                subtitle: [
                  app.disabledReason == 'webhook_failures' ? l10n.appDisabledWebhookFailures : l10n.appDisabledGeneric,
                  if (app.disabledAt != null && app.disabledAt!.length >= 10)
                    l10n.appDisabledOn(app.disabledAt!.substring(0, 10)),
                  if (app.disabledError?.isNotEmpty == true) l10n.appDisabledLastError(app.disabledError!),
                  if (isOwner) l10n.appDisabledOwnerHint,
                ].join('\n')),
            if (isOwner)
              NativeRow('app_detail_reenable', l10n.appReEnable, enabled: !_reEnabling, action: (_) => _reEnableApp()),
          ],
        ]),
        if (steps.isNotEmpty ||
            app.worksExternally() && app.externalIntegration?.setupInstructionsFilePath?.isNotEmpty == true)
          NativeSection(
              'app_detail_setup',
              [
                for (final (index, step) in steps.indexed)
                  NativeRow('app_setup_$index', step.name, symbol: setupCompleted ? 'checkmark.circle' : null,
                      action: (_) async {
                    final uri = Uri.tryParse(appSetupUrlWithUid(step.url, SharedPreferencesUtil().uid));
                    if (uri == null) {
                      OmiFeedback.error(context, l10n.invalidIntegrationUrl);
                      return;
                    }
                    await _launchUrlSafely(uri);
                    checkSetupCompleted(autoInstallIfCompleted: true);
                  }),
                if (steps.isEmpty)
                  NativeRow('app_setup_instructions', l10n.integrationInstructions, action: (_) async {
                    await _openSetupInstructions();
                    checkSetupCompleted();
                  }),
              ],
              title: l10n.integrationInstructions),
        if (app.thumbnailUrls.isNotEmpty)
          NativeSection(
              'app_detail_previews',
              [
                for (final (index, url) in app.thumbnailUrls.indexed)
                  NativeRow('app_preview_$index', l10n.previewAndScreenshots,
                      imageUri: nativeImageUri(url),
                      action: (_) => AppPreviewGallery(
                          imageUrls: app.thumbnailUrls,
                          onImageOpened: (index) => PlatformManager.instance.analytics
                              .appDetailPreviewImageViewed(appId: app.id, imageIndex: index)).open(context, index)),
              ],
              title: l10n.previewAndScreenshots),
        NativeSection('app_detail_description', [
          NativeRow('app_description', l10n.descriptionLabel,
              subtitle: app.description.decodeString,
              action: (_) => routeToPage(
                  context, MarkdownViewer(title: l10n.descriptionLabel, markdown: app.description.decodeString))),
          if (capabilities.isNotEmpty)
            NativeRow('app_capabilities', l10n.appCapabilities,
                kind: 'label',
                subtitle: capabilities.map((capability) => capability.getLocalizedTitle(context)).join('\n')),
          if (app.chatTools?.isNotEmpty == true)
            NativeRow('app_chat_tools', l10n.chatFeatures,
                kind: 'label',
                subtitle: app.chatTools!.map((tool) => AppChatToolsCard.formatToolName(tool.name)).join('\n')),
          if (app.conversationPrompt != null)
            NativeRow('app_summary_prompt', l10n.summaryPrompt,
                subtitle: app.conversationPrompt!.decodeString,
                action: (_) => routeToPage(context,
                    MarkdownViewer(title: l10n.summaryPrompt, markdown: app.conversationPrompt!.decodeString))),
          if (app.chatPrompt != null)
            NativeRow('app_chat_prompt', l10n.chatPersonality,
                subtitle: app.chatPrompt!.decodeString,
                action: (_) => routeToPage(
                    context, MarkdownViewer(title: l10n.chatPersonality, markdown: app.chatPrompt!.decodeString))),
          if (permissions.isNotEmpty)
            NativeRow('app_permissions', l10n.permissionsAndTriggers, kind: 'label', subtitle: permissions.join('\n')),
          if (app.reviews.isNotEmpty || (!isOwner && app.enabled))
            NativeRow('app_reviews', l10n.ratingsAndReviews, action: (_) => openReviews()),
        ]),
      ],
    );
  }
}

import 'package:flutter/material.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/api_keys_widget.dart';
import 'package:omi/pages/apps/widgets/app_form_fields.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:omi/pages/settings/ai_app_generator_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Presentation only. The mounted original forms retain their validators and
/// the provider retains uploads, capability constraints and submit/update I/O.
Widget nativeAppOwnerForm(
  BuildContext context,
  AddAppProvider provider,
  Widget classic, {
  required VoidCallback onSave,
  required VoidCallback onDocs,
  required bool updating,
  bool allowExit = false,
}) {
  if (!iosSwiftUiEnabled) return classic;
  final l10n = context.l10n;
  final busy = provider.isLoading || provider.isSubmitting || provider.isUpdating;
  NativeRow text(String id, String title, TextEditingController controller, {String? keyboard}) =>
      NativeRow(id, title, kind: 'text', value: controller.text, keyboard: keyboard, enabled: !busy, action: (value) {
        controller.text = value as String;
        provider.checkValidity();
      });
  final previewIds = List<String>.of(provider.thumbnailIds);
  final fields = <NativeSection>[
    NativeSection('owner_metadata', [
      if (provider.updateAppId != null) NativeRow('owner_app_id', provider.updateAppId!, kind: 'label'),
      NativeRow('owner_logo', l10n.appIconLabel,
          symbol: 'photo',
          enabled: !busy,
          imageUri: nativeImageUri(provider.imageFile?.path ?? provider.imageUrl),
          action: (_) => updating ? provider.updateImage() : provider.pickImage()),
      text('owner_name', l10n.appNameLabel, provider.appNameController),
      text('owner_description', l10n.description, provider.appDescriptionController),
      NativeRow('owner_generate_description', l10n.generateDescription,
          symbol: 'wand.and.stars',
          enabled: !busy && !provider.isGenratingDescription,
          action: (_) => provider.generateDescription()),
      NativeRow('owner_category', l10n.selectCategory,
          kind: 'choice',
          enabled: !busy,
          value: provider.appCategory ?? '__unset__',
          options: {
            '__unset__': l10n.selectCategory,
            for (final category in provider.categories) category.id: category.getLocalizedTitle(context)
          }, action: (value) {
        if (value != '__unset__') provider.setAppCategory(value as String);
      })
    ]),
    NativeSection(
        'owner_capabilities',
        [
          for (final capability in provider.capabilities)
            NativeRow('owner_capability:${capability.id}', capability.getLocalizedTitle(context),
                kind: 'toggle',
                value: provider.isCapabilitySelected(capability),
                enabled: !busy,
                action: (_) => provider.addOrRemoveCapability(capability))
        ],
        title: l10n.capabilities),
    NativeSection(
        'owner_previews',
        [
          for (final (index, url) in provider.thumbnailUrls.indexed)
            NativeRow('owner_preview:${index < previewIds.length ? previewIds[index] : '$index:${url.hashCode}'}',
                '${l10n.previewScreenshots} ${index + 1}',
                kind: 'navigation',
                imageUri: nativeImageUri(url),
                enabled: !busy,
                options: {'delete': l10n.delete}, action: (value) async {
              final current = index < previewIds.length ? provider.thumbnailIds.indexOf(previewIds[index]) : index;
              if (current < 0 || current >= provider.thumbnailUrls.length || provider.thumbnailUrls[current] != url) {
                return;
              }
              if (value == 'delete') {
                provider.removeThumbnail(current);
              } else {
                openAppScreenshots(context, List.of(provider.thumbnailUrls), current);
              }
            }),
          NativeRow('owner_add_preview', l10n.selectImages,
              symbol: 'plus',
              enabled: !busy && !provider.isUploadingThumbnail,
              action: (_) => provider.pickThumbnail()),
        ],
        title: l10n.previewScreenshots),
    if (provider.isCapabilitySelectedById('chat') || provider.isCapabilitySelectedById('memories'))
      NativeSection('owner_prompts', [
        if (provider.isCapabilitySelectedById('chat'))
          text('owner_chat_prompt', l10n.chatPrompt, provider.chatPromptController),
        if (provider.isCapabilitySelectedById('memories'))
          text('owner_conversation_prompt', l10n.conversationPrompt, provider.conversationPromptController)
      ]),
    if (provider.isCapabilitySelectedById('external_integration')) ...[
      NativeSection(
          'owner_scopes',
          [
            for (final action in provider.getActionTypes())
              NativeRow('owner_scope:${action.id}', action.getLocalizedTitle(context),
                  kind: 'toggle',
                  enabled: !busy,
                  value: provider.actions.any((value) => value['action'] == action.id),
                  action: (value) =>
                      value == true ? provider.addSpecificAction(action.id) : provider.removeActionByType(action.id))
          ],
          title: l10n.scopes),
      NativeSection('owner_external', [
        NativeRow('owner_trigger', l10n.triggerEvents,
            kind: 'choice',
            enabled: !busy,
            value: provider.triggerEvent ?? '__none__',
            options: {
              '__none__': l10n.sttNone,
              for (final trigger in provider.getTriggerEvents()) trigger.id: trigger.getLocalizedTitle(context)
            },
            action: (value) => provider.setTriggerEvent(value == '__none__' ? null : value as String)),
        text('owner_webhook', l10n.webhookUrl, provider.webhookUrlController, keyboard: 'url'),
        text('owner_home_url', l10n.appHomeUrl, provider.appHomeUrlController, keyboard: 'url'),
        text('owner_instructions', l10n.setupInstructions, provider.instructionsController),
        text('owner_auth_url', l10n.authUrl, provider.authUrlController, keyboard: 'url'),
        text('owner_setup_complete', l10n.setupCompletedUrl, provider.setupCompletedController, keyboard: 'url'),
        text('owner_tools_manifest', l10n.chatToolsManifestUrl, provider.chatToolsManifestUrlController,
            keyboard: 'url'),
        if (updating && provider.chatToolsManifestUrlController.text.isNotEmpty)
          NativeRow('owner_refresh_manifest', l10n.refreshManifest,
              symbol: 'arrow.clockwise',
              enabled: !busy && !provider.isRefreshingManifest,
              action: (_) => provider.refreshManifest()),
      ])
    ],
    if (provider.isCapabilitySelectedById('proactive_notification'))
      NativeSection(
          'owner_notifications',
          [
            for (final scope in provider.getNotificationScopes())
              NativeRow('owner_notification:${scope.id}', scope.getLocalizedTitle(context),
                  kind: 'toggle',
                  enabled: !busy,
                  value: provider.isScopesSelected(scope),
                  action: (_) => provider.addOrRemoveScope(scope))
          ],
          title: l10n.notificationScopes),
    if (provider.isCapabilitySelectedById('external_integration') ||
        provider.isCapabilitySelectedById('proactive_notification'))
      NativeSection('owner_source',
          [text('owner_source_url', l10n.githubRepositoryUrl, provider.sourceCodeUrlController, keyboard: 'url')]),
    NativeSection('owner_visibility', [
      NativeRow('owner_terms', l10n.termsAndPrivacyPolicy,
          kind: 'navigation', action: (_) => launchUrl(Uri.parse('https://omi.me/pages/privacy'))),
      if (!updating)
        NativeRow('owner_public', l10n.makePublic,
            kind: 'toggle',
            enabled: !busy,
            value: provider.makeAppPublic,
            subtitle: provider.makeAppPublic ? l10n.anyoneCanDiscover : l10n.onlyYouCanUse,
            action: (value) => provider.setIsPrivate(value as bool)),
      if (provider.allowPaidApps)
        NativeRow('owner_paid', l10n.paidApp,
            kind: 'toggle',
            enabled: !busy,
            value: provider.isPaid,
            action: (value) => provider.setIsPaid(value as bool)),
      if (provider.allowPaidApps && provider.isPaid) ...[
        text('owner_price', l10n.appPricingLabel, provider.priceController, keyboard: 'decimal'),
        NativeRow('owner_plan', l10n.perMonth,
            kind: 'choice',
            enabled: !busy,
            value: provider.selectePaymentPlan ?? '__unset__',
            options: {'__unset__': l10n.perMonth, for (final plan in provider.paymentPlans) plan.id: plan.title},
            action: (value) {
          if (value != '__unset__') provider.setPaymentPlan(value as String);
        })
      ],
      if (updating && provider.updateAppId != null)
        NativeRow('owner_api_keys', l10n.developerApi,
            kind: 'navigation',
            action: (_) => routeToPage(context, ApiKeysWidget(appId: provider.updateAppId!, page: true)))
    ])
  ];
  return _NativeOwnerExitGuard(
      provider: provider,
      allowExit: allowExit,
      child: Scaffold(
          body: IosNativeSurface(
              title: updating ? l10n.manageYourApp : l10n.submitApp,
              fallback: classic,
              nativeOwner: classic,
              loading: busy,
              sections: fields,
              toolbar: [
            NativeRow('owner_back', l10n.back,
                symbol: 'chevron.left', enabled: !busy, action: (_) => Navigator.of(context).maybePop()),
            NativeRow('owner_docs', l10n.docs, symbol: 'arrow.up.right', action: (_) => onDocs()),
            if (!updating)
              NativeRow('owner_generator', l10n.aiAppGeneratorBannerTitle, symbol: 'wand.and.stars', action: (_) {
                OmiHaptics.light();
                PlatformManager.instance.analytics.track('AI App Generator Banner Clicked');
                routeToPage(context, const AiAppGeneratorPage());
              }),
            NativeRow('owner_save', updating ? l10n.updateApp : l10n.submitApp,
                symbol: 'checkmark',
                enabled: !busy && provider.isValid && (!updating || provider.hasChanges),
                action: (_) => onSave())
          ])));
}

class _NativeOwnerExitGuard extends StatefulWidget {
  const _NativeOwnerExitGuard({required this.provider, required this.child, required this.allowExit});
  final AddAppProvider provider;
  final Widget child;
  final bool allowExit;
  @override
  State<_NativeOwnerExitGuard> createState() => _NativeOwnerExitGuardState();
}

class _NativeOwnerExitGuardState extends State<_NativeOwnerExitGuard> {
  bool _leaving = false;
  bool _confirming = false;

  @override
  Widget build(BuildContext context) => PopScope(
        canPop: widget.allowExit || _leaving || !widget.provider.hasChanges,
        onPopInvokedWithResult: (didPop, result) async {
          if (didPop || _confirming) return;
          _confirming = true;
          final leave = await showOmiConfirm(context,
              title: context.l10n.discardChangesTitle,
              message: context.l10n.discardChangesMessage,
              confirmLabel: context.l10n.discard,
              cancelLabel: context.l10n.keepEditing,
              destructive: true);
          _confirming = false;
          if (!mounted || !leave) return;
          setState(() => _leaving = true);
          await WidgetsBinding.instance.endOfFrame;
          if (context.mounted) Navigator.of(context).pop(result);
        },
        child: widget.child,
      );
}

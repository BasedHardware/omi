import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/ai_app_generator_banner.dart';
import 'package:omi/pages/apps/widgets/app_form_fields.dart';
import 'package:omi/pages/apps/widgets/app_metadata_widget.dart';
import 'package:omi/pages/apps/widgets/external_trigger_fields_widget.dart';
import 'package:omi/pages/apps/widgets/notification_scopes_chips_widget.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'widgets/capabilities_chips_widget.dart';
import 'widgets/prompt_text_field.dart';

class AddAppPage extends StatefulWidget {
  final bool presetForConversationAnalysis;
  final bool presetExternalIntegration;

  const AddAppPage({super.key, this.presetForConversationAnalysis = false, this.presetExternalIntegration = false});

  @override
  State<AddAppPage> createState() => _AddAppPageState();
}

class _AddAppPageState extends State<AddAppPage> {
  static const _docsUrl = 'https://docs.omi.me/doc/developer/apps/Introduction';

  late bool showSubmitAppConfirmation;

  @override
  void initState() {
    showSubmitAppConfirmation = SharedPreferencesUtil().showSubmitAppConfirmation;
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) async {
      await Provider.of<AddAppProvider>(context, listen: false).init(
        presetForConversationAnalysis: widget.presetForConversationAnalysis,
        presetExternalIntegration: widget.presetExternalIntegration,
      );
    });
    super.initState();
  }

  Future<void> _startEarningSheet(BuildContext context) async {
    final l10n = context.l10n;
    await showOmiSheet<void>(
      context: context,
      showCloseButton: false,
      builder: (sheetContext) => Padding(
        padding: const EdgeInsets.only(bottom: OmiSpacing.md),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(l10n.startEarning, style: OmiType.title2),
            const SizedBox(height: OmiSpacing.sm),
            Text(
              l10n.connectStripeOrPayPal,
              textAlign: TextAlign.center,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            ),
            const SizedBox(height: OmiSpacing.xl),
            OmiButton(
              label: l10n.connectNow,
              expand: true,
              onPressed: () {
                Navigator.pop(sheetContext);
                routeToPage(context, const PaymentsPage());
              },
            ),
            const SizedBox(height: OmiSpacing.xs),
            OmiButton.tertiary(
              label: l10n.notNow,
              expand: true,
              onPressed: () => Navigator.pop(sheetContext),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _confirmAndSubmit(BuildContext context, AddAppProvider provider) async {
    final l10n = context.l10n;
    if (!provider.validateForm()) return;
    await showDialog(
      context: context,
      builder: (ctx) {
        return ConfirmationDialog(
          title: l10n.submitAppQuestion,
          description: provider.makeAppPublic ? l10n.submitAppPublicDescription : l10n.submitAppPrivateDescription,
          checkboxText: l10n.dontShowAgain,
          confirmText: l10n.submitApp,
          checkboxValue: !showSubmitAppConfirmation,
          onCheckboxChanged: (value) {
            setState(() {
              showSubmitAppConfirmation = !value;
            });
          },
          onConfirm: () async {
            if (provider.makeAppPublic) {
              PlatformManager.instance.analytics.publicAppSubmitted({
                'app_name': provider.appNameController.text,
                'app_category': provider.appCategory,
                'app_capabilities': provider.capabilities.map((e) => e.id).toList(),
                'is_paid': provider.isPaid,
              });
            } else {
              PlatformManager.instance.analytics.privateAppSubmitted({
                'app_name': provider.appNameController.text,
                'app_category': provider.appCategory,
                'app_capabilities': provider.capabilities.map((e) => e.id).toList(),
                'is_paid': provider.isPaid,
              });
            }
            SharedPreferencesUtil().showSubmitAppConfirmation = showSubmitAppConfirmation;
            Navigator.pop(context);
            String? appId = await provider.submitApp();
            App? app;
            if (appId != null && context.mounted) {
              app = await context.read<AppProvider>().getAppFromId(appId);
            }
            var paymentProvider = PaymentMethodProvider();
            await paymentProvider.getPaymentMethodsStatus();

            if (app != null && mounted && context.mounted) {
              if (app.isPaid && paymentProvider.activeMethod == null) {
                await _startEarningSheet(context);
              } else {
                Navigator.pop(context);
                routeToPage(context, AppDetailPage(app: app));
              }
            }
          },
          onCancel: () {
            Navigator.pop(context);
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<AddAppProvider>(
      builder: (context, provider, child) {
        return Scaffold(
          backgroundColor: OmiColors.surface0,
          appBar: AppBar(
            leading: const OmiBackButton(),
            title: Text(l10n.submitApp),
            backgroundColor: OmiColors.surface0,
            actions: [
              Center(
                child: Padding(
                  padding: const EdgeInsets.only(right: OmiSpacing.md),
                  child: OmiButton(
                    label: l10n.docs,
                    leading: const FaIcon(FontAwesomeIcons.arrowUpRightFromSquare),
                    size: OmiButtonSize.compact,
                    onPressed: () {
                      PlatformManager.instance.analytics.pageOpened('App Submission Help');
                      launchUrl(Uri.parse(_docsUrl));
                    },
                  ),
                ),
              ),
            ],
          ),
          extendBody: true,
          body: provider.isLoading || provider.isSubmitting
              ? OmiLoadingState(label: provider.isSubmitting ? l10n.submittingYourApp : l10n.holdOnPreparingForm)
              : GestureDetector(
                  onTap: () {
                    FocusScope.of(context).unfocus();
                  },
                  child: SingleChildScrollView(
                    child: Padding(
                      padding: const EdgeInsets.all(OmiSpacing.md),
                      child: Form(
                        key: provider.formKey,
                        onChanged: () {
                          provider.checkValidity();
                        },
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const AiAppGeneratorBanner(),
                            const SizedBox(height: OmiSpacing.xxs),
                            AppMetadataWidget(
                              pickImage: () async {
                                await provider.pickImage();
                              },
                              generatingDescription: provider.isGenratingDescription,
                              allowPaidApps: false,
                              appPricing: null,
                              appNameController: provider.appNameController,
                              appDescriptionController: provider.appDescriptionController,
                              categories: provider.categories,
                              setAppCategory: provider.setAppCategory,
                              imageFile: provider.imageFile,
                              category: provider.mapCategoryIdToName(provider.appCategory),
                            ),
                            const SizedBox(height: 18),
                            AppScreenshotsSection(
                              title: l10n.previewScreenshots,
                              urls: provider.thumbnailUrls,
                              isUploading: provider.isUploadingThumbnail,
                              onAdd: provider.pickThumbnail,
                              onRemove: provider.removeThumbnail,
                              collapseWhenEmpty: true,
                            ),
                            const SizedBox(height: 18),
                            AppFormCard(
                              padding: const EdgeInsets.fromLTRB(14.0, 20.0, 14.0, 14.0),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.only(left: 8.0, right: 8.0),
                                    child: Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        AppFormSectionTitle(l10n.capabilities, isRequired: true),
                                        const AppFormDocsButton(url: _docsUrl),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(height: 18),
                                  const CapabilitiesChipsWidget(),
                                  const SizedBox(height: 6),
                                ],
                              ),
                            ),
                            if (provider.isCapabilitySelectedById('chat') ||
                                provider.isCapabilitySelectedById('memories'))
                              Column(
                                children: [
                                  const SizedBox(height: 12),
                                  GestureDetector(
                                    onTap: () {
                                      FocusScope.of(context).unfocus();
                                    },
                                    child: Form(
                                      key: provider.promptKey,
                                      onChanged: () {
                                        provider.checkValidity();
                                      },
                                      child: AppFormCard(
                                        child: Column(
                                          children: [
                                            if (provider.isCapabilitySelectedById('chat'))
                                              PromptTextField(
                                                controller: provider.chatPromptController,
                                                label: l10n.chatPrompt,
                                                hint: l10n.chatPromptPlaceholder,
                                              ),
                                            if (provider.isCapabilitySelectedById('memories') &&
                                                provider.isCapabilitySelectedById('chat'))
                                              const SizedBox(height: 20),
                                            if (provider.isCapabilitySelectedById('memories'))
                                              PromptTextField(
                                                controller: provider.conversationPromptController,
                                                label: l10n.conversationPrompt,
                                                hint: l10n.conversationPromptPlaceholder,
                                              ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            const ExternalTriggerFieldsWidget(),
                            if (provider.isCapabilitySelectedById('proactive_notification'))
                              Column(
                                children: [
                                  const SizedBox(height: 12),
                                  AppFormCard(
                                    padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 20.0),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Padding(
                                          padding: const EdgeInsets.only(left: 8.0),
                                          child: AppFormSectionTitle(l10n.notificationScopes),
                                        ),
                                        const SizedBox(height: 16),
                                        const NotificationScopesChipsWidget(),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            if (provider.isCapabilitySelectedById('external_integration') ||
                                provider.isCapabilitySelectedById('proactive_notification'))
                              Column(
                                children: [
                                  const SizedBox(height: 12),
                                  AppSourceCodeUrlSection(controller: provider.sourceCodeUrlController),
                                ],
                              ),
                            const SizedBox(height: 22),
                            // App Settings Card
                            OmiSettingsGroup(
                              children: [
                                OmiSettingsRow.toggle(
                                  leading:
                                      FaIcon(provider.makeAppPublic ? FontAwesomeIcons.globe : FontAwesomeIcons.lock),
                                  title: l10n.makePublic,
                                  subtitle: provider.makeAppPublic ? l10n.anyoneCanDiscover : l10n.onlyYouCanUse,
                                  value: provider.makeAppPublic,
                                  onChanged: provider.setIsPrivate,
                                ),
                                if (provider.allowPaidApps)
                                  OmiSettingsRow.toggle(
                                    leading: const FaIcon(FontAwesomeIcons.dollarSign),
                                    title: l10n.paidApp,
                                    subtitle: provider.isPaid ? l10n.usersPayToUse : l10n.freeForEveryone,
                                    value: provider.isPaid,
                                    onChanged: provider.setIsPaid,
                                  ),
                              ],
                            ),
                            if (provider.allowPaidApps && provider.isPaid) ...[
                              const SizedBox(height: OmiSpacing.sm),
                              AppFormCard(
                                child: Row(
                                  children: [
                                    const Text('\$', style: OmiType.title3),
                                    const SizedBox(width: OmiSpacing.xs),
                                    Expanded(
                                      child: TextField(
                                        controller: provider.priceController,
                                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                        style: OmiType.title3,
                                        decoration: InputDecoration(
                                          hintText: '0.00',
                                          hintStyle: OmiType.title3.copyWith(color: OmiColors.textTertiary),
                                          border: InputBorder.none,
                                          isDense: true,
                                          contentPadding: EdgeInsets.zero,
                                        ),
                                      ),
                                    ),
                                    Text(l10n.perMonth,
                                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                                  ],
                                ),
                              ),
                            ],
                            const SizedBox(height: 106),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
          bottomNavigationBar: (provider.isLoading || provider.isSubmitting)
              ? null
              : Container(
                  padding: const EdgeInsets.only(left: 16.0, right: 16, bottom: 30, top: 10),
                  decoration: BoxDecoration(
                    borderRadius: OmiRadius.mdAll,
                    color: OmiColors.surface1,
                    gradient: LinearGradient(
                      colors: [OmiColors.surface0, OmiColors.surface0.withValues(alpha: 0)],
                      begin: Alignment.bottomCenter,
                      end: Alignment.topCenter,
                    ),
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      OmiButton(
                        label: l10n.submitApp,
                        expand: true,
                        // Not awaited: the confirmation dialog (and the submit it guards) run on their
                        // own, the same as the pre-migration hand-drawn button. The page-level
                        // OmiLoadingState above already covers provider.isSubmitting.
                        onPressed: provider.isValid
                            ? () {
                                _confirmAndSubmit(context, provider);
                              }
                            : null,
                      ),
                      const SizedBox(height: 10),
                      GestureDetector(
                        onTap: () {
                          launchUrl(Uri.parse('https://omi.me/pages/privacy'));
                        },
                        child: Text.rich(
                          TextSpan(
                            text: l10n.bySubmittingYouAgreeToOmi,
                            style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                            children: [
                              TextSpan(
                                text: l10n.termsAndPrivacyPolicy,
                                style: OmiType.caption.copyWith(
                                  color: OmiColors.textSecondary,
                                  decoration: TextDecoration.underline,
                                ),
                              ),
                            ],
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ],
                  ),
                ),
        );
      },
    );
  }
}

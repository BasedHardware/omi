import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/api_keys_widget.dart';
import 'package:omi/pages/apps/widgets/notification_scopes_chips_widget.dart';
import 'package:omi/ui/ui.dart';
import 'widgets/app_form_fields.dart';
import 'widgets/app_metadata_widget.dart';
import 'widgets/capabilities_chips_widget.dart';
import 'widgets/external_trigger_fields_widget.dart';
import 'widgets/payment_details_widget.dart';
import 'widgets/prompt_text_field.dart';

class UpdateAppPage extends StatefulWidget {
  final App app;
  const UpdateAppPage({super.key, required this.app});

  @override
  State<UpdateAppPage> createState() => _UpdateAppPageState();
}

class _UpdateAppPageState extends State<UpdateAppPage> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AddAppProvider>().prepareUpdate(widget.app);
    });
    super.initState();
  }

  Future<void> _confirmAndUpdate(BuildContext context, AddAppProvider provider) async {
    final l10n = context.l10n;
    if (!provider.validateForm()) return;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.updateAppQuestion,
      message: l10n.updateAppConfirmation,
      confirmLabel: l10n.updateApp,
    );
    if (!confirmed || !context.mounted) return;
    final ok = await provider.updateApp();
    if (ok && context.mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<AddAppProvider>(
      builder: (context, provider, child) {
        return GestureDetector(
          onTap: () {
            FocusScope.of(context).unfocus();
          },
          child: Scaffold(
            backgroundColor: OmiColors.surface0,
            extendBody: true,
            appBar: AppBar(
              leading: const OmiBackButton(),
              title: Text(l10n.manageYourApp),
              backgroundColor: OmiColors.surface0,
              actions: [
                if (provider.selectedCapabilities.any((c) => c.id == 'external_integration') &&
                    provider.chatToolsManifestUrlController.text.isNotEmpty)
                  provider.isRefreshingManifest
                      ? const SizedBox(
                          width: kOmiMinTapTarget,
                          height: kOmiMinTapTarget,
                          child: Center(child: OmiSpinner(size: OmiSpinnerSize.small)),
                        )
                      : OmiIconButton(
                          icon: const Icon(Icons.refresh),
                          label: l10n.refreshManifest,
                          onPressed: () async {
                            await provider.refreshManifest();
                          },
                        ),
              ],
            ),
            body: PopScope(
              onPopInvokedWithResult: (didPop, result) {
                context.read<AddAppProvider>().clear();
              },
              child: Builder(
                builder: (context) {
                  if (provider.isUpdating) {
                    return OmiLoadingState(label: l10n.updatingYourApp);
                  }
                  if (provider.isLoading) {
                    return OmiLoadingState(label: l10n.fetchingYourAppDetails);
                  }
                  return SingleChildScrollView(
                    child: Padding(
                      padding: const EdgeInsets.all(OmiSpacing.md),
                      child: Form(
                        key: provider.formKey,
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const SizedBox(height: 18),
                            AppMetadataWidget(
                              pickImage: () async {
                                await provider.updateImage();
                              },
                              generatingDescription: provider.isGenratingDescription,
                              allowPaidApps: provider.allowPaidApps,
                              appPricing: provider.isPaid ? l10n.pricingPaid : l10n.pricingFree,
                              imageFile: provider.imageFile,
                              appNameController: provider.appNameController,
                              appDescriptionController: provider.appDescriptionController,
                              categories: provider.categories,
                              setAppCategory: provider.setAppCategory,
                              imageUrl: provider.imageUrl,
                              category: provider.mapCategoryIdToName(provider.appCategory),
                            ),
                            provider.isPaid
                                ? PaymentDetailsWidget(
                                    appPricingController: provider.priceController,
                                    paymentPlan: provider.mapPaymentPlanIdToName(provider.selectePaymentPlan),
                                  )
                                : const SizedBox.shrink(),
                            const SizedBox(height: 18),
                            AppScreenshotsSection(
                              title: l10n.previewAndScreenshots,
                              urls: provider.thumbnailUrls,
                              isUploading: provider.isUploadingThumbnail,
                              onAdd: provider.pickThumbnail,
                              onRemove: provider.removeThumbnail,
                            ),
                            const SizedBox(height: 18),
                            AppFormCard(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.only(left: 8.0),
                                    child: AppFormSectionTitle(l10n.appCapabilities),
                                  ),
                                  const SizedBox(height: 10),
                                  const CapabilitiesChipsWidget(),
                                ],
                              ),
                            ),
                            if (provider.isCapabilitySelectedById('chat') ||
                                provider.isCapabilitySelectedById('memories'))
                              Column(
                                children: [
                                  const SizedBox(height: 18),
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
                                  const SizedBox(height: 18),
                                  AppFormCard(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Padding(
                                          padding: const EdgeInsets.only(left: 8.0),
                                          child: AppFormSectionTitle(l10n.notificationScopes),
                                        ),
                                        const SizedBox(height: 10),
                                        const SizedBox(height: 48, child: NotificationScopesChipsWidget()),
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
                            // API Keys section
                            Column(
                              children: [
                                const SizedBox(height: 18),
                                ApiKeysWidget(appId: widget.app.id),
                              ],
                            ),
                            const SizedBox(height: 120),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
            bottomNavigationBar: (provider.isUpdating)
                ? null
                : Container(
                    padding: const EdgeInsets.only(left: 30.0, right: 30, bottom: 50, top: 10),
                    decoration: BoxDecoration(
                      borderRadius: OmiRadius.mdAll,
                      color: OmiColors.surface1,
                      gradient: LinearGradient(
                        colors: [OmiColors.surface0, OmiColors.surface0.withValues(alpha: 0)],
                        begin: Alignment.bottomCenter,
                        end: Alignment.topCenter,
                      ),
                    ),
                    child: OmiButton(
                      label: l10n.updateApp,
                      expand: true,
                      // Not awaited: the confirmation dialog (and the update it guards) run on their
                      // own, the same as the pre-migration hand-drawn button. provider.isUpdating
                      // already drives the page-level OmiLoadingState above.
                      onPressed: (!provider.isValid || !provider.hasChanges)
                          ? null
                          : () {
                              _confirmAndUpdate(context, provider);
                            },
                    ),
                  ),
          ),
        );
      },
    );
  }
}

import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:shimmer/shimmer.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/widgets/full_screen_image_viewer.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/notification_scopes_chips_widget.dart';
import 'package:omi/pages/apps/widgets/api_keys_widget.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:provider/provider.dart';

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

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      return GestureDetector(
        onTap: () {
          FocusScope.of(context).unfocus();
        },
        child: Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          extendBody: true,
          appBar: AppBar(
            title: const Text('Manage Your App'),
            backgroundColor: Theme.of(context).colorScheme.primary,
          ),
          body: PopScope(
            onPopInvoked: (didPop) {
              context.read<AddAppProvider>().clear();
            },
            child: Builder(builder: (context) {
              if (provider.isUpdating) {
                return const Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
                      SizedBox(
                        height: 14,
                      ),
                      Text(
                        'Updating your app',
                        style: TextStyle(color: Colors.white),
                      ),
                    ],
                  ),
                );
              }
              if (provider.isLoading) {
                return const Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
                      SizedBox(
                        height: 14,
                      ),
                      Text(
                        'Fetching your app details',
                        style: TextStyle(color: Colors.white),
                      ),
                    ],
                  ),
                );
              }
              return SingleChildScrollView(
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
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
                          appPricing: provider.isPaid ? 'Paid' : 'Free',
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
                        Container(
                          decoration: BoxDecoration(
                            color: Colors.grey.shade900,
                            borderRadius: BorderRadius.circular(12.0),
                          ),
                          padding: const EdgeInsets.all(14.0),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Padding(
                                padding: const EdgeInsets.only(left: 8.0),
                                child: Text(
                                  'Preview and Screenshots',
                                  style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                                ),
                              ),
                              const SizedBox(height: 18),
                              SizedBox(
                                height: 180,
                                child: ListView.builder(
                                  scrollDirection: Axis.horizontal,
                                  itemCount: provider.thumbnailUrls.length + 1,
                                  itemBuilder: (context, index) {
                                    // Calculate dimensions to maintain 2:3 ratio
                                    const width = 120.0;
                                    const height = width * 1.5; // 2:3 ratio

                                    if (index == provider.thumbnailUrls.length) {
                                      return GestureDetector(
                                        onTap: provider.isUploadingThumbnail ? null : provider.pickThumbnail,
                                        child: Container(
                                          width: width,
                                          height: height,
                                          margin: const EdgeInsets.only(right: 8),
                                          decoration: BoxDecoration(
                                            color: Colors.grey.shade800,
                                            borderRadius: BorderRadius.circular(8),
                                          ),
                                          child: provider.isUploadingThumbnail
                                              ? Shimmer.fromColors(
                                                  baseColor: Colors.grey[900]!,
                                                  highlightColor: Colors.grey[800]!,
                                                  child: Container(
                                                    width: width,
                                                    height: height,
                                                    decoration: BoxDecoration(
                                                      color: Colors.black,
                                                      borderRadius: BorderRadius.circular(8),
                                                    ),
                                                    child: const Icon(Icons.photo, size: 32),
                                                  ),
                                                )
                                              : const Icon(Icons.add_photo_alternate_outlined, size: 32),
                                        ),
                                      );
                                    }
                                    return Stack(
                                      children: [
                                        GestureDetector(
                                          onTap: () {
                                            Navigator.push(
                                              context,
                                              MaterialPageRoute(
                                                builder: (context) => FullScreenImageViewer(
                                                  imageUrl: provider.thumbnailUrls[index],
                                                ),
                                              ),
                                            );
                                          },
                                          child: CachedNetworkImage(
                                            imageUrl: provider.thumbnailUrls[index],
                                            imageBuilder: (context, imageProvider) => Container(
                                              width: 120,
                                              height: 180, // 2:3 ratio (120 * 1.5)
                                              margin: const EdgeInsets.only(right: 8),
                                              decoration: BoxDecoration(
                                                borderRadius: BorderRadius.circular(8),
                                                border: Border.all(
                                                  color: const Color(0xFF424242),
                                                  width: 1,
                                                ),
                                                image: DecorationImage(
                                                  image: imageProvider,
                                                  fit: BoxFit.cover,
                                                ),
                                              ),
                                            ),
                                            placeholder: (context, url) => Shimmer.fromColors(
                                              baseColor: Colors.grey[900]!,
                                              highlightColor: Colors.grey[800]!,
                                              child: Container(
                                                width: 120,
                                                height: 180,
                                                margin: const EdgeInsets.only(right: 8),
                                                decoration: BoxDecoration(
                                                  color: Colors.black,
                                                  borderRadius: BorderRadius.circular(8),
                                                ),
                                              ),
                                            ),
                                            errorWidget: (context, url, error) => Container(
                                              width: 120,
                                              height: 180,
                                              margin: const EdgeInsets.only(right: 8),
                                              decoration: BoxDecoration(
                                                color: Colors.grey[900],
                                                borderRadius: BorderRadius.circular(8),
                                              ),
                                              child: const Icon(Icons.error),
                                            ),
                                          ),
                                        ),
                                        Positioned(
                                          top: 4,
                                          right: 12,
                                          child: GestureDetector(
                                            onTap: () => provider.removeThumbnail(index),
                                            child: Container(
                                              padding: const EdgeInsets.all(4),
                                              decoration: BoxDecoration(
                                                color: Colors.black.withOpacity(0.6),
                                                shape: BoxShape.circle,
                                              ),
                                              child: const Icon(Icons.close, size: 16),
                                            ),
                                          ),
                                        ),
                                      ],
                                    );
                                  },
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 18),
                        Container(
                          decoration: BoxDecoration(
                            color: Colors.grey.shade900,
                            borderRadius: BorderRadius.circular(12.0),
                          ),
                          padding: const EdgeInsets.all(14.0),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Padding(
                                padding: const EdgeInsets.only(left: 8.0),
                                child: Text(
                                  'App Capabilities',
                                  style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                                ),
                              ),
                              const SizedBox(
                                height: 10,
                              ),
                              const SizedBox(height: 48, child: CapabilitiesChipsWidget()),
                            ],
                          ),
                        ),
                        if (provider.isCapabilitySelectedById('chat') || provider.isCapabilitySelectedById('memories'))
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
                                  child: Container(
                                    decoration: BoxDecoration(
                                      color: Colors.grey.shade900,
                                      borderRadius: BorderRadius.circular(12.0),
                                    ),
                                    padding: const EdgeInsets.all(14.0),
                                    child: Column(
                                      children: [
                                        if (provider.isCapabilitySelectedById('chat'))
                                          PromptTextField(
                                            controller: provider.chatPromptController,
                                            label: 'Chat Prompt',
                                            hint:
                                                'You are an awesome app, your job is to respond to the user queries and make them feel good...',
                                          ),
                                        if (provider.isCapabilitySelectedById('memories') &&
                                            provider.isCapabilitySelectedById('chat'))
                                          const SizedBox(
                                            height: 20,
                                          ),
                                        if (provider.isCapabilitySelectedById('memories'))
                                          PromptTextField(
                                            controller: provider.conversationPromptController,
                                            label: 'Conversation Prompt',
                                            hint:
                                                'You are an awesome app, you will be given transcript and summary of a conversation...',
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
                              Container(
                                decoration: BoxDecoration(
                                  color: Colors.grey.shade900,
                                  borderRadius: BorderRadius.circular(12.0),
                                ),
                                padding: const EdgeInsets.all(14.0),
                                width: double.infinity,
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Padding(
                                      padding: const EdgeInsets.only(left: 8.0),
                                      child: Text(
                                        'Notification Scopes',
                                        style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                                      ),
                                    ),
                                    const SizedBox(
                                      height: 10,
                                    ),
                                    const SizedBox(height: 48, child: NotificationScopesChipsWidget()),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        // API Keys section
                        Column(
                          children: [
                            const SizedBox(height: 18),
                            ApiKeysWidget(appId: widget.app.id),
                          ],
                        ),
                        const SizedBox(
                          height: 120,
                        ),
                      ],
                    ),
                  ),
                ),
              );
            }),
          ),
          bottomNavigationBar: (provider.isUpdating)
              ? null
              : Container(
                  padding: const EdgeInsets.only(left: 30.0, right: 30, bottom: 50, top: 10),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(12.0),
                    color: Colors.grey.shade900,
                    gradient: LinearGradient(
                      colors: [Colors.black, Colors.black.withOpacity(0)],
                      begin: Alignment.bottomCenter,
                      end: Alignment.topCenter,
                    ),
                  ),
                  child: GestureDetector(
                    onTap: !provider.isValid
                        ? null
                        : () {
                            var isValid = provider.validateForm();
                            if (isValid) {
                              showDialog(
                                context: context,
                                builder: (c) => getDialog(
                                  context,
                                  () => Navigator.pop(context),
                                  () async {
                                    Navigator.pop(context);
                                    bool ok = await provider.updateApp();
                                    if (ok) {
                                      Navigator.pop(context);
                                    }
                                  },
                                  'Update App?',
                                  'Are you sure you want to update your app? The changes will reflect once reviewed by our team.',
                                  okButtonText: 'Confirm',
                                ),
                              );
                            }
                          },
                    child: Container(
                      padding: const EdgeInsets.all(12.0),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(12.0),
                        color: provider.isValid ? Colors.white : Colors.grey.shade700,
                      ),
                      child: const Text(
                        'Update App',
                        style: TextStyle(color: Colors.black, fontSize: 16),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ),
                ),
        ),
      );
    });
  }
}

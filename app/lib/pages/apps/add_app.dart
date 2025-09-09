import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/app_metadata_widget.dart';
import 'package:omi/pages/apps/widgets/external_trigger_fields_widget.dart';
import 'package:omi/pages/apps/widgets/full_screen_image_viewer.dart';
import 'package:omi/pages/apps/widgets/notification_scopes_chips_widget.dart';
import 'package:omi/pages/apps/widgets/payment_details_widget.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';
import 'package:url_launcher/url_launcher.dart';

import 'widgets/capabilities_chips_widget.dart';
import 'widgets/prompt_text_field.dart';

class AddAppPage extends StatefulWidget {
  final bool presetForConversationAnalysis;

  const AddAppPage({
    super.key,
    this.presetForConversationAnalysis = false,
  });

  @override
  State<AddAppPage> createState() => _AddAppPageState();
}

class _AddAppPageState extends State<AddAppPage> {
  late bool showSubmitAppConfirmation;

  @override
  void initState() {
    showSubmitAppConfirmation = SharedPreferencesUtil().showSubmitAppConfirmation;
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) async {
      await Provider.of<AddAppProvider>(context, listen: false).init(
        presetForConversationAnalysis: widget.presetForConversationAnalysis,
      );
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          title: const Text('Submit App'),
          backgroundColor: Theme.of(context).colorScheme.primary,
        ),
        extendBody: true,
        body: provider.isLoading || provider.isSubmitting
            ? Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    const CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
                    const SizedBox(
                      height: 14,
                    ),
                    Text(
                      provider.isSubmitting ? 'Submitting your app...' : 'Hold on, we are preparing the form for you',
                      style: const TextStyle(color: Colors.white),
                    ),
                  ],
                ),
              )
            : GestureDetector(
                onTap: () {
                  FocusScope.of(context).unfocus();
                },
                child: SingleChildScrollView(
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Form(
                      key: provider.formKey,
                      onChanged: () {
                        provider.checkValidity();
                      },
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          GestureDetector(
                            onTap: () {
                              MixpanelManager().pageOpened('App Submission Help');
                              launchUrl(Uri.parse('https://omi.me/apps/introduction'));
                            },
                            child: Container(
                              padding: const EdgeInsets.all(12.0),
                              margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 12, bottom: 14),
                              decoration: BoxDecoration(
                                color: const Color(0xFF1F1F25),
                                borderRadius: BorderRadius.circular(16.0),
                              ),
                              child: const ListTile(
                                title: Text(
                                  'Want to build an app but not sure where to begin? Click here!',
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(height: 18),
                          AppMetadataWidget(
                            pickImage: () async {
                              await provider.pickImage();
                            },
                            generatingDescription: provider.isGenratingDescription,
                            allowPaidApps: provider.allowPaidApps,
                            appPricing: provider.isPaid ? 'Paid' : 'Free',
                            appNameController: provider.appNameController,
                            appDescriptionController: provider.appDescriptionController,
                            categories: provider.categories,
                            setAppCategory: provider.setAppCategory,
                            imageFile: provider.imageFile,
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
                              color: const Color(0xFF1F1F25),
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
                                const SizedBox(height: 12),
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
                                              color: Color(0xFF35343B),
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
                                                  color: Colors.black.withValues(alpha: 0.6),
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
                              color: const Color(0xFF1F1F25),
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
                          if (provider.isCapabilitySelectedById('chat') ||
                              provider.isCapabilitySelectedById('memories'))
                            Column(
                              children: [
                                const SizedBox(
                                  height: 12,
                                ),
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
                                        color: const Color(0xFF1F1F25),
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
                                const SizedBox(
                                  height: 12,
                                ),
                                Container(
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF1F1F25),
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
                          const SizedBox(
                            height: 22,
                          ),
                          const Text(
                            'App Privacy',
                            style: TextStyle(color: Colors.white, fontSize: 16),
                          ),
                          const SizedBox(
                            height: 8,
                          ),
                          Row(
                            children: [
                              Checkbox(
                                value: provider.makeAppPublic,
                                onChanged: (value) {
                                  if (value != null) {
                                    provider.setIsPrivate(value);
                                  }
                                },
                                shape: const CircleBorder(),
                              ),
                              const Expanded(
                                child: Text("Make my app public"),
                              ),
                            ],
                          ),
                          const SizedBox(
                            height: 8,
                          ),
                          Row(
                            children: [
                              Checkbox(
                                value: provider.termsAgreed,
                                onChanged: provider.setTermsAgreed,
                                shape: const CircleBorder(),
                              ),
                              const Expanded(
                                child: Text(
                                    "By submitting this app, I agree to the Omi AI Terms of Service and Privacy Policy"),
                              ),
                            ],
                          ),
                          const SizedBox(
                            height: 106,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
        bottomNavigationBar: (provider.isLoading || provider.isSubmitting)
            ? null
            : Container(
                padding: const EdgeInsets.only(left: 30.0, right: 30, bottom: 50, top: 10),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12.0),
                  color: const Color(0xFF1F1F25),
                  gradient: LinearGradient(
                    colors: [Colors.black, Colors.black.withValues(alpha: 0)],
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
                              builder: (ctx) {
                                return ConfirmationDialog(
                                  title: 'Submit App?',
                                  description: provider.makeAppPublic
                                      ? 'Your app will be reviewed and made public. You can start using it immediately, even during the review!'
                                      : 'Your app will be reviewed and made available to you privately. You can start using it immediately, even during the review!',
                                  checkboxText: "Don't show it again",
                                  checkboxValue: !showSubmitAppConfirmation,
                                  onCheckboxChanged: (value) {
                                    setState(() {
                                      showSubmitAppConfirmation = !value;
                                    });
                                  },
                                  onConfirm: () async {
                                    if (provider.makeAppPublic) {
                                      MixpanelManager().publicAppSubmitted({
                                        'app_name': provider.appNameController.text,
                                        'app_category': provider.appCategory,
                                        'app_capabilities': provider.capabilities.map((e) => e.id).toList(),
                                        'is_paid': provider.isPaid,
                                      });
                                    } else {
                                      MixpanelManager().privateAppSubmitted({
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
                                    if (appId != null) {
                                      app = await context.read<AppProvider>().getAppFromId(appId);
                                    }
                                    var paymentProvider = context.read<PaymentMethodProvider>();
                                    paymentProvider.getPaymentMethodsStatus();

                                    if (app != null && mounted && context.mounted) {
                                      if (app.isPaid && paymentProvider.activeMethod == null) {
                                        showCupertinoModalPopup(
                                          context: context,
                                          builder: (ctx) => Container(
                                            padding: const EdgeInsets.all(20),
                                            decoration: BoxDecoration(
                                              color: const Color(0xFF1F1F25),
                                              borderRadius: const BorderRadius.vertical(
                                                top: Radius.circular(20),
                                              ),
                                            ),
                                            child: Material(
                                              color: Colors.transparent,
                                              child: Column(
                                                mainAxisSize: MainAxisSize.min,
                                                children: [
                                                  Container(
                                                    width: 40,
                                                    height: 4,
                                                    margin: const EdgeInsets.only(bottom: 20),
                                                    decoration: BoxDecoration(
                                                      color: Colors.grey.shade700,
                                                      borderRadius: BorderRadius.circular(2),
                                                    ),
                                                  ),
                                                  const SizedBox(height: 20),
                                                  const Text(
                                                    'Start Earning! 💰',
                                                    style: TextStyle(
                                                      color: Colors.white,
                                                      fontSize: 24,
                                                      fontWeight: FontWeight.bold,
                                                    ),
                                                  ),
                                                  const SizedBox(height: 12),
                                                  const Text(
                                                    'Connect Stripe or PayPal to receive payments for your app.',
                                                    textAlign: TextAlign.center,
                                                    style: TextStyle(
                                                      color: Colors.grey,
                                                      fontSize: 16,
                                                    ),
                                                  ),
                                                  const SizedBox(height: 32),
                                                  CupertinoButton(
                                                    color: Colors.white,
                                                    borderRadius: BorderRadius.circular(12),
                                                    onPressed: () {
                                                      Navigator.pop(ctx);
                                                      routeToPage(context, const PaymentsPage());
                                                    },
                                                    child: const Text(
                                                      'Connect Now',
                                                      style: TextStyle(
                                                        color: Colors.black,
                                                        fontWeight: FontWeight.w600,
                                                      ),
                                                    ),
                                                  ),
                                                  const SizedBox(height: 8),
                                                  CupertinoButton(
                                                    onPressed: () => Navigator.pop(ctx),
                                                    child: Text(
                                                      'Maybe Later',
                                                      style: TextStyle(
                                                        color: Colors.grey.shade400,
                                                      ),
                                                    ),
                                                  ),
                                                  SizedBox(height: MediaQuery.of(context).padding.bottom),
                                                ],
                                              ),
                                            ),
                                          ),
                                        );
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
                        },
                  child: Container(
                    padding: const EdgeInsets.all(12.0),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(12.0),
                      color: provider.isValid ? Colors.white : Colors.grey.shade700,
                    ),
                    child: const Text(
                      'Submit App',
                      style: TextStyle(color: Colors.black, fontSize: 16),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              ),
      );
    });
  }
}

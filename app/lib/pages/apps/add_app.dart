import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/pages/apps/widgets/app_metadata_widget.dart';
import 'package:friend_private/pages/apps/widgets/external_trigger_fields_widget.dart';
import 'package:friend_private/pages/apps/widgets/notification_scopes_chips_widget.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/confirmation_dialog.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'widgets/capabilities_chips_widget.dart';
import 'widgets/prompt_text_field.dart';

class AddAppPage extends StatefulWidget {
  const AddAppPage({super.key});

  @override
  State<AddAppPage> createState() => _AddAppPageState();
}

class _AddAppPageState extends State<AddAppPage> {
  late bool showSubmitAppConfirmation;
  @override
  void initState() {
    showSubmitAppConfirmation = SharedPreferencesUtil().showSubmitAppConfirmation;
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) async {
      await Provider.of<AddAppProvider>(context, listen: false).init();
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          title: const Text('Submit Your App'),
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
            : SingleChildScrollView(
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
                              color: Colors.grey.shade900,
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
                        const SizedBox(
                          height: 18,
                        ),
                        AppMetadataWidget(
                          pickImage: () async {
                            await provider.pickImage();
                          },
                          appNameController: provider.appNameController,
                          appDescriptionController: provider.appDescriptionController,
                          creatorNameController: provider.creatorNameController,
                          creatorEmailController: provider.creatorEmailController,
                          categories: provider.categories,
                          setAppCategory: provider.setAppCategory,
                          imageFile: provider.imageFile,
                          category: provider.mapCategoryIdToName(provider.appCategory),
                        ),
                        const SizedBox(
                          height: 12,
                        ),
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
                                            controller: provider.memoryPromptController,
                                            label: 'Memory Prompt',
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
                            SizedBox(
                              width: MediaQuery.of(context).size.width * 0.80,
                              child: const Text("Make my app public"),
                            ),
                          ],
                        ),
                        const SizedBox(
                          height: 30,
                        ),
                        Row(
                          children: [
                            Checkbox(
                              value: provider.termsAgreed,
                              onChanged: provider.setTermsAgreed,
                              shape: const CircleBorder(),
                            ),
                            SizedBox(
                              width: MediaQuery.of(context).size.width * 0.80,
                              child: const Text(
                                  "By submitting this app, I agree to the Omi AI Terms of Service and Privacy Policy"),
                            ),
                          ],
                        ),
                        const SizedBox(
                          height: 90,
                        ),
                      ],
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
                              builder: (ctx) {
                                return ConfirmationDialog(
                                  title: 'Submit App?',
                                  description: provider.makeAppPublic
                                      ? 'Your app will be reviewed and made public. You can start using it immediately, even during the review!'
                                      : 'Your app will be reviewed and made available to you privately. You can start using it immediately, even during the review!',
                                  checkboxText: "Don't show it again",
                                  checkboxValue: !showSubmitAppConfirmation,
                                  updateCheckboxValue: (value) {
                                    if (value != null) {
                                      setState(() {
                                        showSubmitAppConfirmation = !value;
                                      });
                                    }
                                  },
                                  onConfirm: () async {
                                    if (provider.makeAppPublic) {
                                      MixpanelManager().publicAppSubmitted({
                                        'app_name': provider.appNameController.text,
                                        'app_category': provider.appCategory,
                                        'app_capabilities': provider.capabilities.map((e) => e.id).toList(),
                                      });
                                    } else {
                                      MixpanelManager().privateAppSubmitted({
                                        'app_name': provider.appNameController.text,
                                        'app_category': provider.appCategory,
                                        'app_capabilities': provider.capabilities.map((e) => e.id).toList(),
                                      });
                                    }
                                    SharedPreferencesUtil().showSubmitAppConfirmation = showSubmitAppConfirmation;
                                    Navigator.pop(context);
                                    await provider.submitApp();
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

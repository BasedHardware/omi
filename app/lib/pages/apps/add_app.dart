import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/pages/apps/widgets/app_metadata_widget.dart';
import 'package:friend_private/pages/apps/widgets/external_trigger_fields_widget.dart';
import 'package:friend_private/pages/apps/widgets/notification_scopes_chips_widget.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/confirmation_dialog.dart';
import 'package:friend_private/widgets/gradient_button.dart';
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
                          height: 12,
                        ),
                        const Text(
                          'App Capabilities',
                          style: TextStyle(color: Colors.white, fontSize: 16),
                        ),
                        const SizedBox(height: 60, child: CapabilitiesChipsWidget()),
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
                        ),
                        const SizedBox(
                          height: 30,
                        ),
                        if (provider.capabilitySelected())
                          const Text(
                            'App Specific Details',
                            style: TextStyle(color: Colors.white, fontSize: 16),
                          ),
                        if (provider.isCapabilitySelectedById('chat'))
                          const SizedBox(
                            height: 20,
                          ),
                        if (provider.isCapabilitySelectedById('chat'))
                          PromptTextField(
                            controller: provider.chatPromptController,
                            label: 'Chat Prompt',
                            icon: Icons.chat,
                          ),
                        if (provider.isCapabilitySelectedById('memories'))
                          const SizedBox(
                            height: 24,
                          ),
                        if (provider.isCapabilitySelectedById('memories'))
                          PromptTextField(
                            controller: provider.memoryPromptController,
                            label: 'Memory Prompt',
                            icon: Icons.memory,
                          ),
                        const ExternalTriggerFieldsWidget(),
                        if (provider.capabilitySelected())
                          const SizedBox(
                            height: 30,
                          ),
                        const NotificationScopesChipsWidget(),
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
                            ),
                            SizedBox(
                              width: MediaQuery.of(context).size.width * 0.80,
                              child: const Text(
                                  "By submitting this app, I agree to the Omi AI Terms of Service and Privacy Policy"),
                            ),
                          ],
                        ),
                        const SizedBox(
                          height: 12,
                        ),
                        GradientButton(
                          title: 'Submit App',
                          onPressed: () {
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
                        ),
                        const SizedBox(
                          height: 30,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
      );
    });
  }
}

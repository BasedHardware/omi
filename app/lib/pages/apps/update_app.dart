import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/pages/apps/widgets/notification_scopes_chips_widget.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:provider/provider.dart';

import 'widgets/app_metadata_widget.dart';
import 'widgets/capabilities_chips_widget.dart';
import 'widgets/external_trigger_fields_widget.dart';
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
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        extendBody: true,
        appBar: AppBar(
          title: const Text('Update Your App'),
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
                      const SizedBox(
                        height: 18,
                      ),
                      AppMetadataWidget(
                        pickImage: () async {
                          await provider.updateImage();
                        },
                        imageFile: provider.imageFile,
                        appNameController: provider.appNameController,
                        appDescriptionController: provider.appDescriptionController,
                        creatorNameController: provider.creatorNameController,
                        creatorEmailController: provider.creatorEmailController,
                        categories: provider.categories,
                        setAppCategory: provider.setAppCategory,
                        imageUrl: provider.imageUrl,
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
                        height: 90,
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
                                  await provider.updateApp();
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
      );
    });
  }
}

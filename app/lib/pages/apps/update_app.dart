import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/pages/apps/widgets/notification_scopes_chips_widget.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/gradient_button.dart';
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
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('Update Your App'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      body: PopScope(
        onPopInvoked: (didPop) {
          context.read<AddAppProvider>().clear();
        },
        child: Consumer<AddAppProvider>(builder: (context, provider, child) {
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
                      category: provider.appCategory,
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
                    const SizedBox(
                      height: 30,
                    ),
                    GradientButton(
                      title: 'Update App',
                      onPressed: () {
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
                    ),
                    const SizedBox(
                      height: 30,
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ),
    );
  }
}

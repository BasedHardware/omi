import 'package:dotted_border/dotted_border.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/pages/apps/widgets/external_trigger_fields_widget.dart';
import 'package:provider/provider.dart';

import 'widgets/capabilities_chips_widget.dart';
import 'widgets/prompt_text_field.dart';

class AddAppPage extends StatefulWidget {
  const AddAppPage({super.key});

  @override
  State<AddAppPage> createState() => _AddAppPageState();
}

class _AddAppPageState extends State<AddAppPage> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) {
      Provider.of<AddAppProvider>(context, listen: false).init();
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
        body: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.all(16.0),
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
                const Text(
                  'App Metadata',
                  style: TextStyle(color: Colors.white, fontSize: 16),
                ),
                const SizedBox(
                  height: 16,
                ),
                GestureDetector(
                  onTap: () async {
                    await provider.pickImage();
                  },
                  child: provider.imageFile != null
                      ? Container(
                          height: 100,
                          width: double.infinity,
                          decoration: BoxDecoration(
                            border: Border.all(color: Colors.grey[500] ?? Colors.grey),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            mainAxisAlignment: MainAxisAlignment.start,
                            children: [
                              const SizedBox(
                                width: 30,
                              ),
                              Image.file(
                                provider.imageFile!,
                                height: 60,
                                width: 60,
                                fit: BoxFit.cover,
                              ),
                              const SizedBox(
                                width: 30,
                              ),
                              const Text(
                                'Replace App Icon?',
                                style: TextStyle(color: Colors.white, fontSize: 16),
                              ),
                            ],
                          ),
                        )
                      : DottedBorder(
                          borderType: BorderType.RRect,
                          dashPattern: [6, 3],
                          radius: const Radius.circular(10),
                          color: Colors.grey[600] ?? Colors.grey,
                          child: Container(
                            height: 100,
                            width: double.infinity,
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(10),
                              color: Colors.transparent,
                            ),
                            child: const Center(
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    Icons.cloud_upload,
                                    color: Colors.grey,
                                    size: 32,
                                  ),
                                  SizedBox(
                                    height: 8,
                                  ),
                                  Text(
                                    'Upload App Icon',
                                    style: TextStyle(color: Colors.grey),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                ),
                const SizedBox(
                  height: 16,
                ),
                TextFormField(
                  controller: provider.appNameController,
                  decoration: InputDecoration(
                    border: const OutlineInputBorder(
                      borderRadius: BorderRadius.all(Radius.circular(10)),
                    ),
                    focusedBorder: const OutlineInputBorder(
                      borderRadius: BorderRadius.all(Radius.circular(10)),
                      borderSide: BorderSide(
                        color: Colors.white,
                      ),
                    ),
                    label: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.apps,
                            color: WidgetStateColor.resolveWith(
                                (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                        const SizedBox(
                          width: 8,
                        ),
                        const Text(
                          'App Name',
                        ),
                      ],
                    ),
                    alignLabelWithHint: true,
                    labelStyle: const TextStyle(
                      color: Colors.grey,
                    ),
                    floatingLabelStyle: const TextStyle(
                      color: Colors.white,
                    ),
                  ),
                ),
                const SizedBox(
                  height: 16,
                ),
                DropdownButtonFormField(
                  decoration: InputDecoration(
                    border: const OutlineInputBorder(
                      borderRadius: BorderRadius.all(Radius.circular(10)),
                    ),
                    focusedBorder: const OutlineInputBorder(
                      borderRadius: BorderRadius.all(Radius.circular(10)),
                      borderSide: BorderSide(
                        color: Colors.white,
                      ),
                    ),
                    label: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.category,
                            color: WidgetStateColor.resolveWith(
                                (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                        const SizedBox(
                          width: 8,
                        ),
                        const Text(
                          'App Category',
                        ),
                      ],
                    ),
                    labelStyle: const TextStyle(
                      color: Colors.grey,
                    ),
                    floatingLabelStyle: const TextStyle(
                      color: Colors.white,
                    ),
                  ),
                  items: const [
                    DropdownMenuItem(
                      value: 'Memory Creation',
                      child: Text('Memory Creation'),
                    ),
                    DropdownMenuItem(
                      value: 'Transcript Processed',
                      child: Text('Transcript Processed'),
                    ),
                  ],
                  onChanged: (v) {
                    FocusScope.of(context).unfocus();
                  },
                ),
                const SizedBox(
                  height: 16,
                ),
                TextFormField(
                  controller: provider.creatorNameController,
                  decoration: InputDecoration(
                    border: const OutlineInputBorder(
                      borderRadius: BorderRadius.all(Radius.circular(10)),
                    ),
                    focusedBorder: const OutlineInputBorder(
                      borderRadius: BorderRadius.all(Radius.circular(10)),
                      borderSide: BorderSide(
                        color: Colors.white,
                      ),
                    ),
                    label: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.person,
                            color: WidgetStateColor.resolveWith(
                                (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                        const SizedBox(
                          width: 8,
                        ),
                        const Text(
                          'Creator Name',
                        ),
                      ],
                    ),
                    alignLabelWithHint: true,
                    labelStyle: const TextStyle(
                      color: Colors.grey,
                    ),
                    floatingLabelStyle: const TextStyle(
                      color: Colors.white,
                    ),
                  ),
                ),
                const SizedBox(
                  height: 16,
                ),
                TextFormField(
                  controller: provider.creatorEmailController,
                  decoration: InputDecoration(
                    border: const OutlineInputBorder(
                      borderRadius: BorderRadius.all(Radius.circular(10)),
                    ),
                    focusedBorder: const OutlineInputBorder(
                      borderRadius: BorderRadius.all(Radius.circular(10)),
                      borderSide: BorderSide(
                        color: Colors.white,
                      ),
                    ),
                    label: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.email,
                            color: WidgetStateColor.resolveWith(
                                (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                        const SizedBox(
                          width: 8,
                        ),
                        const Text(
                          'Email Address',
                        ),
                      ],
                    ),
                    alignLabelWithHint: true,
                    labelStyle: const TextStyle(
                      color: Colors.grey,
                    ),
                    floatingLabelStyle: const TextStyle(
                      color: Colors.white,
                    ),
                  ),
                ),
                const SizedBox(
                  height: 16,
                ),
                TextFormField(
                  maxLines: null,
                  controller: provider.appDescriptionController,
                  decoration: InputDecoration(
                    border: const OutlineInputBorder(
                      borderRadius: BorderRadius.all(Radius.circular(10)),
                    ),
                    focusedBorder: const OutlineInputBorder(
                      borderRadius: BorderRadius.all(Radius.circular(10)),
                      borderSide: BorderSide(
                        color: Colors.white,
                      ),
                    ),
                    label: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.description,
                            color: WidgetStateColor.resolveWith(
                                (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                        const SizedBox(
                          width: 8,
                        ),
                        const Text(
                          'Description',
                        ),
                      ],
                    ),
                    alignLabelWithHint: true,
                    labelStyle: const TextStyle(
                      color: Colors.grey,
                    ),
                    floatingLabelStyle: const TextStyle(
                      color: Colors.white,
                    ),
                  ),
                ),
                const SizedBox(
                  height: 30,
                ),
                if (provider.capabilitySelected())
                  const Text(
                    'App Specific Details',
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  ),
                if (provider.isCapabilitySelected('Chat'))
                  const SizedBox(
                    height: 18,
                  ),
                if (provider.isCapabilitySelected('Chat'))
                  PromptTextField(
                    controller: provider.chatPromptController,
                    label: 'Chat Prompt',
                    icon: Icons.chat,
                  ),
                if (provider.isCapabilitySelected('Memories'))
                  const SizedBox(
                    height: 16,
                  ),
                if (provider.isCapabilitySelected('Memories'))
                  PromptTextField(
                    controller: provider.memoryPromptController,
                    label: 'Memory Prompt',
                    icon: Icons.memory,
                  ),
                const SizedBox(
                  height: 16,
                ),
                ExternalTriggerFieldsWidget()
              ],
            ),
          ),
        ),
      );
    });
  }
}

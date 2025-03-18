import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:omi/env/env.dart';

import 'dart:convert';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/app_metadata_widget.dart';
import 'package:omi/pages/apps/widgets/external_trigger_fields_widget.dart';
import 'package:omi/pages/apps/widgets/full_screen_image_viewer.dart';
import 'package:omi/pages/apps/widgets/api_keys_widget.dart';
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
  const AddAppPage({super.key});

  @override
  State<AddAppPage> createState() => _AddAppPageState();
}

class _AddAppPageState extends State<AddAppPage> {
  late bool showSubmitAppConfirmation;
  final TextEditingController _promptController = TextEditingController();
  bool _isGenerating = false;
  String _generatedResult = '';

  @override
  void initState() {
    showSubmitAppConfirmation =
        SharedPreferencesUtil().showSubmitAppConfirmation;
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) async {
      await Provider.of<AddAppProvider>(context, listen: false).init();
    });
    super.initState();
  }

  @override
  void dispose() {
    _promptController.dispose();
    super.dispose();
  }

  Future<void> _generateApp() async {
    final prompt = _promptController.text.trim();
    if (prompt.isEmpty) return;

    setState(() {
      _isGenerating = true;
    });

    try {
      final apiKey = ""; // TODO: Get API key from environment variables
      if (apiKey == null || apiKey.isEmpty) {
        throw Exception('OpenAI API key not found in environment variables');
      }

      final systemPrompt = '''
      You are an AI that creates structured app descriptions based on user input. 
      Your job is to turn user ideas into well-structured app descriptions with specific capabilities.
      You MUST respond with a valid JSON object in the following format:
      {
        "name": "string - concise app name",
        "description": "string - detailed description",
        "category": "string - one from: Productivity, Entertainment, Education, Lifestyle, Utilities, Health & Fitness, Finance, Social, Travel, Games",
        "capabilities": ["array of strings from: chat, memories, proactive_notification, external_trigger, app_actions"],
        "chat_prompt": "string - if chat capability is selected, provide a detailed system prompt",
        "conversation_prompt": "string - if memories capability is selected, provide a detailed memory processing prompt",
        "notification_scopes": ["array of strings from: all_day, conversation_end, conversation_start, memory_creation, transcript_processed"] - if proactive_notification capability is selected
      }
      Be creative but practical, focusing on what can realistically be built within the Omi ecosystem.
''';

      int retryCount = 0;
      const maxRetries = 3;
      bool validResponse = false;
      String? validJsonResponse;

      while (!validResponse && retryCount < maxRetries) {
        final response = await http.post(
          Uri.parse('https://api.openai.com/v1/chat/completions'),
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer $apiKey',
          },
          body: jsonEncode({
            'model': 'gpt-4',
            'messages': [
              {'role': 'system', 'content': systemPrompt},
              {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.7,
          }),
        );

        if (response.statusCode == 200) {
          final data = jsonDecode(response.body);
          final rawContent = data['choices'][0]['message']['content'];

          try {
            // Try to parse the response as JSON
            final jsonResponse = jsonDecode(rawContent);

            // Validate the JSON structure
            if (_validateAppJson(jsonResponse)) {
              validResponse = true;
              validJsonResponse = rawContent;
            } else {
              retryCount++;
              if (retryCount >= maxRetries) {
                throw Exception(
                    'Failed to generate valid app structure after $maxRetries attempts');
              }
            }
          } catch (e) {
            retryCount++;
            if (retryCount >= maxRetries) {
              throw Exception(
                  'Failed to generate valid JSON response after $maxRetries attempts');
            }
          }
        } else {
          throw Exception('Failed to generate app: ${response.body}');
        }
      }

      if (validJsonResponse != null) {
        setState(() {
          _generatedResult = validJsonResponse!;
          _isGenerating = false;
        });
        _showResultDialog();
      } else {
        throw Exception('Failed to generate valid app structure');
      }
    } catch (e) {
      setState(() {
        _isGenerating = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error generating app: ${e.toString()}')),
      );
    }
  }

  // Add this new method to validate the JSON structure
  bool _validateAppJson(Map<String, dynamic> json) {
    // Check required fields
    final requiredFields = ['name', 'description', 'category', 'capabilities'];
    for (final field in requiredFields) {
      if (!json.containsKey(field)) return false;
    }

    // Validate category
    final validCategories = [
      'Productivity',
      'Entertainment',
      'Education',
      'Lifestyle',
      'Utilities',
      'Health & Fitness',
      'Finance',
      'Social',
      'Travel',
      'Games'
    ];
    if (!validCategories.contains(json['category'])) return false;

    // Validate capabilities
    final validCapabilities = [
      'chat',
      'memories',
      'proactive_notification',
      'external_trigger',
      'app_actions'
    ];
    if (json['capabilities'] is! List) return false;
    for (final capability in json['capabilities']) {
      if (!validCapabilities.contains(capability)) return false;
    }

    // Validate optional fields based on capabilities
    if (json['capabilities'].contains('chat') &&
        (!json.containsKey('chat_prompt') || json['chat_prompt'].isEmpty)) {
      return false;
    }
    if (json['capabilities'].contains('memories') &&
        (!json.containsKey('conversation_prompt') ||
            json['conversation_prompt'].isEmpty)) {
      return false;
    }

    // Validate notification scopes if proactive_notification capability is selected
    if (json['capabilities'].contains('proactive_notification')) {
      if (!json.containsKey('notification_scopes') ||
          json['notification_scopes'] is! List) {
        return false;
      }
      final validScopes = [
        'all_day',
        'conversation_end',
        'conversation_start',
        'memory_creation',
        'transcript_processed'
      ];
      for (final scope in json['notification_scopes']) {
        if (!validScopes.contains(scope)) return false;
      }
    }

    return true;
  }

  // Update the _parseGeneratedApp method to handle JSON
  Map<String, dynamic> _parseGeneratedApp(String text) {
    try {
      final jsonResponse = jsonDecode(text);
      return {
        'name': jsonResponse['name'] ?? '',
        'description': jsonResponse['description'] ?? '',
        'category': jsonResponse['category'] ?? '',
        'capabilities': List<String>.from(jsonResponse['capabilities'] ?? []),
        'chat_prompt': jsonResponse['chat_prompt'] ?? '',
        'conversation_prompt': jsonResponse['conversation_prompt'] ?? '',
        'notification_scopes':
            List<String>.from(jsonResponse['notification_scopes'] ?? []),
      };
    } catch (e) {
      // Fallback to the old parsing method if JSON parsing fails
      return _parseGeneratedAppLegacy(text);
    }
  }

  // Keep the old parsing method as fallback
  Map<String, dynamic> _parseGeneratedAppLegacy(String text) {
    final Map<String, dynamic> result = {
      'name': '',
      'description': '',
      'category': '',
      'capabilities': <String>[],
      'chat_prompt': '',
      'conversation_prompt': '',
      'notification_scopes': <String>[],
    };

    // Extract app name (using exact prompt format)
    final nameRegex = RegExp(r'App name:\s*(.*?)(?=\n)', caseSensitive: false);
    final nameMatch = nameRegex.firstMatch(text);
    if (nameMatch != null && nameMatch.groupCount >= 1) {
      result['name'] = nameMatch.group(1)?.trim() ?? '';
    }

    // Extract description (using exact prompt format)
    final descRegex = RegExp(r'Description:\s*([\s\S]*?)(?=\n\s*Category:)',
        caseSensitive: false);
    final descMatch = descRegex.firstMatch(text);
    if (descMatch != null && descMatch.groupCount >= 1) {
      result['description'] = descMatch.group(1)?.trim() ?? '';
    }

    // Extract category (using exact prompt format)
    final categoryRegex =
        RegExp(r'Category:\s*(.*?)(?=\n)', caseSensitive: false);
    final categoryMatch = categoryRegex.firstMatch(text);
    if (categoryMatch != null && categoryMatch.groupCount >= 1) {
      result['category'] = categoryMatch.group(1)?.trim() ?? '';
    }

    // Extract capabilities (using exact prompt format)
    final capabilitiesRegex = RegExp(
        r'Capabilities:\s*([\s\S]*?)(?=\n\s*(?:Chat Prompt:|Conversation Prompt:|$))',
        caseSensitive: false);
    final capabilitiesMatch = capabilitiesRegex.firstMatch(text);

    if (capabilitiesMatch != null && capabilitiesMatch.groupCount >= 1) {
      final capabilitiesText = capabilitiesMatch.group(1)?.trim() ?? '';

      // Check for each specific capability in the capabilities text
      final List<String> commonCapabilities = [
        'chat',
        'memories',
        'proactive_notification',
        'external_trigger',
        'app_actions'
      ];

      for (final capability in commonCapabilities) {
        if (capabilitiesText
            .toLowerCase()
            .contains(capability.toLowerCase().replaceAll('_', ' '))) {
          result['capabilities'].add(capability);
        }
      }
    }

    // Extract Chat Prompt (using exact prompt format)
    final chatPromptRegex = RegExp(
        r'Chat Prompt:\s*([\s\S]*?)(?=\n\s*(?:Conversation Prompt:|$))',
        caseSensitive: false);
    final chatPromptMatch = chatPromptRegex.firstMatch(text);
    if (chatPromptMatch != null && chatPromptMatch.groupCount >= 1) {
      result['chat_prompt'] = chatPromptMatch.group(1)?.trim() ?? '';
    }

    // Extract Conversation Prompt (using exact prompt format)
    final convPromptRegex =
        RegExp(r'Conversation Prompt:\s*([\s\S]*?)(?=$)', caseSensitive: false);
    final convPromptMatch = convPromptRegex.firstMatch(text);
    if (convPromptMatch != null && convPromptMatch.groupCount >= 1) {
      result['conversation_prompt'] = convPromptMatch.group(1)?.trim() ?? '';
    }

    return result;
  }

  // Apply the parsed information to the form
  void _applyGeneratedApp(
      Map<String, dynamic> appData, AddAppProvider provider) {
    // Fill app name
    if (appData['name'].isNotEmpty) {
      provider.appNameController.text = appData['name'];
    }

    // Fill description
    if (appData['description'].isNotEmpty) {
      provider.appDescriptionController.text = appData['description'];
    }

    // Set category if it matches any of the available categories
    if (appData['category'].isNotEmpty) {
      final categoryText = appData['category'].toLowerCase();
      for (final cat in provider.categories) {
        if (cat.name.toLowerCase().contains(categoryText) ||
            categoryText.contains(cat.name.toLowerCase())) {
          provider.setAppCategory(cat.id);
          break;
        }
      }
    }

    // Set capabilities and their metadata
    if (appData['capabilities'] is List) {
      final List<String> capabilities =
          List<String>.from(appData['capabilities']);
      for (final capability in capabilities) {
        // Toggle the capability
        provider.toggleCapability(capability);

        // Set metadata for specific capabilities
        if (capability == 'chat' &&
            appData['chat_prompt']?.isNotEmpty == true) {
          provider.chatPromptController.text = appData['chat_prompt'];
        }
        if (capability == 'memories' &&
            appData['conversation_prompt']?.isNotEmpty == true) {
          provider.conversationPromptController.text =
              appData['conversation_prompt'];
        }
      }
    }

    // Validate form after autofill
    provider.checkValidity();
  }

  void _showPromptDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: const Text('Generate App with AI'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Describe the app you want to create:',
              style: TextStyle(color: Colors.white70),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _promptController,
              decoration: const InputDecoration(
                hintText: 'E.g., A fitness tracking app that helps users...',
                border: OutlineInputBorder(),
              ),
              maxLines: 4,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _generateApp();
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.white,
              foregroundColor: Colors.black,
            ),
            child: const Text('Generate'),
          ),
        ],
      ),
    );
  }

  void _showResultDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: const Text('Generated App'),
        content: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_generatedResult),
              const SizedBox(height: 20),
              const Text(
                'Would you like to apply these suggestions to your form?',
                style: TextStyle(color: Colors.white70),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              final provider =
                  Provider.of<AddAppProvider>(context, listen: false);
              final parsedApp = _parseGeneratedApp(_generatedResult);
              _applyGeneratedApp(parsedApp, provider);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text(
                      'Form fields have been filled based on AI suggestions'),
                  backgroundColor: Colors.green,
                ),
              );
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.white,
              foregroundColor: Colors.black,
            ),
            child: const Text('Apply'),
          ),
        ],
      ),
    );
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
                      provider.isSubmitting
                          ? 'Submitting your app...'
                          : 'Hold on, we are preparing the form for you',
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
                              MixpanelManager()
                                  .pageOpened('App Submission Help');
                              launchUrl(Uri.parse(
                                  'https://omi.me/apps/introduction'));
                            },
                            child: Container(
                              padding: const EdgeInsets.all(12.0),
                              margin: const EdgeInsets.only(
                                  left: 2.0, right: 2.0, top: 12, bottom: 8),
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
                          GestureDetector(
                            onTap: _isGenerating ? null : _showPromptDialog,
                            child: Container(
                              padding: const EdgeInsets.all(12.0),
                              margin: const EdgeInsets.only(
                                  left: 2.0, right: 2.0, bottom: 14),
                              decoration: BoxDecoration(
                                color: Colors.blue.shade900,
                                borderRadius: BorderRadius.circular(16.0),
                              ),
                              child: ListTile(
                                leading: _isGenerating
                                    ? const SizedBox(
                                        width: 24,
                                        height: 24,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          valueColor:
                                              AlwaysStoppedAnimation<Color>(
                                                  Colors.white),
                                        ),
                                      )
                                    : const Icon(Icons.auto_awesome,
                                        color: Colors.white),
                                title: Text(
                                  _isGenerating
                                      ? 'Generating App...'
                                      : 'Generate App with AI',
                                  textAlign: TextAlign.center,
                                  style: const TextStyle(color: Colors.white),
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(height: 18),
                          AppMetadataWidget(
                            pickImage: () async {
                              await provider.pickImage();
                            },
                            generatingDescription:
                                provider.isGenratingDescription,
                            allowPaidApps: provider.allowPaidApps,
                            appPricing: provider.isPaid ? 'Paid' : 'Free',
                            appNameController: provider.appNameController,
                            appDescriptionController:
                                provider.appDescriptionController,
                            categories: provider.categories,
                            setAppCategory: provider.setAppCategory,
                            imageFile: provider.imageFile,
                            category: provider
                                .mapCategoryIdToName(provider.appCategory),
                          ),
                          provider.isPaid
                              ? PaymentDetailsWidget(
                                  appPricingController:
                                      provider.priceController,
                                  paymentPlan: provider.mapPaymentPlanIdToName(
                                      provider.selectePaymentPlan),
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
                                    style: TextStyle(
                                        color: Colors.grey.shade300,
                                        fontSize: 16),
                                  ),
                                ),
                                const SizedBox(height: 12),
                                SizedBox(
                                  height: 180,
                                  child: ListView.builder(
                                    scrollDirection: Axis.horizontal,
                                    itemCount:
                                        provider.thumbnailUrls.length + 1,
                                    itemBuilder: (context, index) {
                                      // Calculate dimensions to maintain 2:3 ratio
                                      final width = 120.0;
                                      final height = width * 1.5; // 2:3 ratio

                                      if (index ==
                                          provider.thumbnailUrls.length) {
                                        return GestureDetector(
                                          onTap: provider.isUploadingThumbnail
                                              ? null
                                              : provider.pickThumbnail,
                                          child: Container(
                                            width: width,
                                            height: height,
                                            margin:
                                                const EdgeInsets.only(right: 8),
                                            decoration: BoxDecoration(
                                              color: Colors.grey.shade800,
                                              borderRadius:
                                                  BorderRadius.circular(8),
                                            ),
                                            child: provider.isUploadingThumbnail
                                                ? Shimmer.fromColors(
                                                    baseColor:
                                                        Colors.grey[900]!,
                                                    highlightColor:
                                                        Colors.grey[800]!,
                                                    child: Container(
                                                      width: width,
                                                      height: height,
                                                      decoration: BoxDecoration(
                                                        color: Colors.black,
                                                        borderRadius:
                                                            BorderRadius
                                                                .circular(8),
                                                      ),
                                                      child: const Icon(
                                                          Icons.photo,
                                                          size: 32),
                                                    ),
                                                  )
                                                : const Icon(
                                                    Icons
                                                        .add_photo_alternate_outlined,
                                                    size: 32),
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
                                                  builder: (context) =>
                                                      FullScreenImageViewer(
                                                    imageUrl: provider
                                                        .thumbnailUrls[index],
                                                  ),
                                                ),
                                              );
                                            },
                                            child: CachedNetworkImage(
                                              imageUrl:
                                                  provider.thumbnailUrls[index],
                                              imageBuilder:
                                                  (context, imageProvider) =>
                                                      Container(
                                                width: 120,
                                                height:
                                                    180, // 2:3 ratio (120 * 1.5)
                                                margin: const EdgeInsets.only(
                                                    right: 8),
                                                decoration: BoxDecoration(
                                                  borderRadius:
                                                      BorderRadius.circular(8),
                                                  border: Border.all(
                                                    color:
                                                        const Color(0xFF424242),
                                                    width: 1,
                                                  ),
                                                  image: DecorationImage(
                                                    image: imageProvider,
                                                    fit: BoxFit.cover,
                                                  ),
                                                ),
                                              ),
                                              placeholder: (context, url) =>
                                                  Shimmer.fromColors(
                                                baseColor: Colors.grey[900]!,
                                                highlightColor:
                                                    Colors.grey[800]!,
                                                child: Container(
                                                  width: 120,
                                                  height: 180,
                                                  margin: const EdgeInsets.only(
                                                      right: 8),
                                                  decoration: BoxDecoration(
                                                    color: Colors.black,
                                                    borderRadius:
                                                        BorderRadius.circular(
                                                            8),
                                                  ),
                                                ),
                                              ),
                                              errorWidget:
                                                  (context, url, error) =>
                                                      Container(
                                                width: 120,
                                                height: 180,
                                                margin: const EdgeInsets.only(
                                                    right: 8),
                                                decoration: BoxDecoration(
                                                  color: Colors.grey[900],
                                                  borderRadius:
                                                      BorderRadius.circular(8),
                                                ),
                                                child: const Icon(Icons.error),
                                              ),
                                            ),
                                          ),
                                          Positioned(
                                            top: 4,
                                            right: 12,
                                            child: GestureDetector(
                                              onTap: () => provider
                                                  .removeThumbnail(index),
                                              child: Container(
                                                padding:
                                                    const EdgeInsets.all(4),
                                                decoration: BoxDecoration(
                                                  color: Colors.black
                                                      .withOpacity(0.6),
                                                  shape: BoxShape.circle,
                                                ),
                                                child: const Icon(Icons.close,
                                                    size: 16),
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
                                    style: TextStyle(
                                        color: Colors.grey.shade300,
                                        fontSize: 16),
                                  ),
                                ),
                                const SizedBox(
                                  height: 10,
                                ),
                                const SizedBox(
                                    height: 48,
                                    child: CapabilitiesChipsWidget()),
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
                                        color: Colors.grey.shade900,
                                        borderRadius:
                                            BorderRadius.circular(12.0),
                                      ),
                                      padding: const EdgeInsets.all(14.0),
                                      child: Column(
                                        children: [
                                          if (provider
                                              .isCapabilitySelectedById('chat'))
                                            PromptTextField(
                                              controller:
                                                  provider.chatPromptController,
                                              label: 'Chat Prompt',
                                              hint:
                                                  'You are an awesome app, your job is to respond to the user queries and make them feel good...',
                                            ),
                                          if (provider.isCapabilitySelectedById(
                                                  'memories') &&
                                              provider.isCapabilitySelectedById(
                                                  'chat'))
                                            const SizedBox(
                                              height: 20,
                                            ),
                                          if (provider.isCapabilitySelectedById(
                                              'memories'))
                                            PromptTextField(
                                              controller: provider
                                                  .conversationPromptController,
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
                          if (provider.isCapabilitySelectedById(
                              'proactive_notification'))
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
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Padding(
                                        padding:
                                            const EdgeInsets.only(left: 8.0),
                                        child: Text(
                                          'Notification Scopes',
                                          style: TextStyle(
                                              color: Colors.grey.shade300,
                                              fontSize: 16),
                                        ),
                                      ),
                                      const SizedBox(
                                        height: 10,
                                      ),
                                      const SizedBox(
                                          height: 48,
                                          child:
                                              NotificationScopesChipsWidget()),
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
                padding: const EdgeInsets.only(
                    left: 30.0, right: 30, bottom: 50, top: 10),
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
                                  onCheckboxChanged: (value) {
                                    setState(() {
                                      showSubmitAppConfirmation = !value;
                                    });
                                  },
                                  onConfirm: () async {
                                    if (provider.makeAppPublic) {
                                      MixpanelManager().publicAppSubmitted({
                                        'app_name':
                                            provider.appNameController.text,
                                        'app_category': provider.appCategory,
                                        'app_capabilities': provider
                                            .capabilities
                                            .map((e) => e.id)
                                            .toList(),
                                        'is_paid': provider.isPaid,
                                      });
                                    } else {
                                      MixpanelManager().privateAppSubmitted({
                                        'app_name':
                                            provider.appNameController.text,
                                        'app_category': provider.appCategory,
                                        'app_capabilities': provider
                                            .capabilities
                                            .map((e) => e.id)
                                            .toList(),
                                        'is_paid': provider.isPaid,
                                      });
                                    }
                                    SharedPreferencesUtil()
                                            .showSubmitAppConfirmation =
                                        showSubmitAppConfirmation;
                                    Navigator.pop(context);
                                    String? appId = await provider.submitApp();
                                    App? app;
                                    if (appId != null) {
                                      app = await context
                                          .read<AppProvider>()
                                          .getAppFromId(appId);
                                    }
                                    var paymentProvider =
                                        context.read<PaymentMethodProvider>();
                                    paymentProvider.getPaymentMethodsStatus();

                                    if (app != null &&
                                        mounted &&
                                        context.mounted) {
                                      if (app.isPaid &&
                                          paymentProvider.activeMethod ==
                                              null) {
                                        showCupertinoModalPopup(
                                          context: context,
                                          builder: (ctx) => Container(
                                            padding: const EdgeInsets.all(20),
                                            decoration: BoxDecoration(
                                              color: Colors.grey.shade900,
                                              borderRadius:
                                                  const BorderRadius.vertical(
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
                                                    margin:
                                                        const EdgeInsets.only(
                                                            bottom: 20),
                                                    decoration: BoxDecoration(
                                                      color:
                                                          Colors.grey.shade700,
                                                      borderRadius:
                                                          BorderRadius.circular(
                                                              2),
                                                    ),
                                                  ),
                                                  const SizedBox(height: 20),
                                                  const Text(
                                                    'Start Earning! 💰',
                                                    style: TextStyle(
                                                      color: Colors.white,
                                                      fontSize: 24,
                                                      fontWeight:
                                                          FontWeight.bold,
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
                                                    borderRadius:
                                                        BorderRadius.circular(
                                                            12),
                                                    onPressed: () {
                                                      Navigator.pop(ctx);
                                                      routeToPage(context,
                                                          const PaymentsPage());
                                                    },
                                                    child: const Text(
                                                      'Connect Now',
                                                      style: TextStyle(
                                                        color: Colors.black,
                                                        fontWeight:
                                                            FontWeight.w600,
                                                      ),
                                                    ),
                                                  ),
                                                  const SizedBox(height: 8),
                                                  CupertinoButton(
                                                    onPressed: () =>
                                                        Navigator.pop(ctx),
                                                    child: Text(
                                                      'Maybe Later',
                                                      style: TextStyle(
                                                        color: Colors
                                                            .grey.shade400,
                                                      ),
                                                    ),
                                                  ),
                                                  SizedBox(
                                                      height:
                                                          MediaQuery.of(context)
                                                              .padding
                                                              .bottom),
                                                ],
                                              ),
                                            ),
                                          ),
                                        );
                                      } else {
                                        Navigator.pop(context);
                                        routeToPage(
                                            context, AppDetailPage(app: app));
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
                      color: provider.isValid
                          ? Colors.white
                          : Colors.grey.shade700,
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

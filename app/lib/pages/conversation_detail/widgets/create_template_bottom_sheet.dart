import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';

class CreateTemplateBottomSheet extends StatefulWidget {
  final String? conversationId;

  const CreateTemplateBottomSheet({
    super.key,
    this.conversationId,
  });

  @override
  State<CreateTemplateBottomSheet> createState() => _CreateTemplateBottomSheetState();
}

class _CreateTemplateBottomSheetState extends State<CreateTemplateBottomSheet> {
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _promptController = TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  bool _isPublic = false;
  bool _isCreating = false;
  String _statusMessage = '';

  @override
  void dispose() {
    _nameController.dispose();
    _promptController.dispose();
    super.dispose();
  }

  Future<File> _createEmojiIcon(String emoji) async {
    // Create a simple widget with white background and emoji
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    const size = 256.0;

    // Draw white background
    final bgPaint = Paint()..color = Colors.white;
    canvas.drawRect(Rect.fromLTWH(0, 0, size, size), bgPaint);

    // Draw emoji text
    final textPainter = TextPainter(
      text: TextSpan(
        text: emoji,
        style: const TextStyle(fontSize: 140),
      ),
      textDirection: TextDirection.ltr,
    );
    textPainter.layout();

    // Center the emoji
    final offsetX = (size - textPainter.width) / 2;
    final offsetY = (size - textPainter.height) / 2;
    textPainter.paint(canvas, Offset(offsetX, offsetY));

    // Convert to image
    final picture = recorder.endRecording();
    final image = await picture.toImage(size.toInt(), size.toInt());
    final byteData = await image.toByteData(format: ui.ImageByteFormat.png);

    if (byteData == null) {
      throw Exception('Failed to create icon image');
    }

    // Save to temp file
    final tempDir = await getTemporaryDirectory();
    final file = File('${tempDir.path}/emoji_icon_${DateTime.now().millisecondsSinceEpoch}.png');
    await file.writeAsBytes(byteData.buffer.asUint8List());

    return file;
  }

  Future<void> _createTemplate() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isCreating = true;
      _statusMessage = 'Generating description...';
    });

    try {
      final name = _nameController.text.trim();
      final prompt = _promptController.text.trim();
      const category = 'conversation-analysis';

      // Generate description and emoji using AI
      final result = await getGeneratedDescriptionAndEmoji(name, prompt);
      final description = result.description;
      final emoji = result.emoji;

      setState(() {
        _statusMessage = 'Creating app icon...';
      });

      // Create simple emoji icon
      final iconFile = await _createEmojiIcon(emoji);

      setState(() {
        _statusMessage = 'Creating your app...';
      });

      // Prepare app data
      final Map<String, dynamic> appData = {
        'name': name,
        'description': description,
        'capabilities': ['memories'],
        'deleted': false,
        'uid': SharedPreferencesUtil().uid,
        'category': category,
        'private': !_isPublic,
        'is_paid': false,
        'price': 0.0,
        'memory_prompt': prompt,
        'thumbnails': [],
      };

      // Submit app
      final submitResult = await submitAppServer(iconFile, appData);

      // Clean up temp icon file
      if (iconFile.existsSync()) {
        await iconFile.delete();
      }

      if (submitResult.$1) {
        // Success
        MixpanelManager().quickTemplateCreated(
          conversationId: widget.conversationId ?? '',
          appName: name,
          isPublic: _isPublic,
        );

        // Refresh apps list
        if (mounted) {
          await context.read<AppProvider>().getApps();
        }

        // Get the created app
        App? createdApp;
        if (submitResult.$3 != null && mounted) {
          final appDetails = await getAppDetailsServer(submitResult.$3!);
          if (appDetails != null) {
            createdApp = App.fromJson(appDetails);
          }
        }

        if (mounted && createdApp != null) {
          setState(() {
            _statusMessage = 'Installing app...';
          });

          // Enable/install the app for the user
          final success = await enableAppServer(createdApp.id);
          if (success) {
            SharedPreferencesUtil().enableApp(createdApp.id);
            createdApp.enabled = true;

            // Update the conversation detail provider's cached apps
            if (mounted) {
              final conversationProvider = context.read<ConversationDetailProvider>();
              conversationProvider.addToEnabledConversationApps(createdApp);
            }
          }

          if (mounted) {
            // Close the create template bottom sheet
            Navigator.pop(context);
            AppSnackbar.showSnackbarSuccess('App created and installed! 🚀');

            // Show the summarized apps sheet so user can use the new app
            showModalBottomSheet(
              context: context,
              isScrollControlled: true,
              backgroundColor: Colors.transparent,
              builder: (context) => const SummarizedAppsBottomSheet(),
            );
          }
        } else if (mounted) {
          Navigator.pop(context);
          AppSnackbar.showSnackbarSuccess('App created successfully! 🚀');
        }
      } else {
        // Error
        if (mounted) {
          setState(() {
            _isCreating = false;
            _statusMessage = '';
          });
          AppSnackbar.showSnackbarError(
              submitResult.$2.isNotEmpty ? submitResult.$2 : 'Failed to create app. Please try again.');
        }
      }
    } catch (e) {
      debugPrint('Error creating template: $e');
      if (mounted) {
        setState(() {
          _isCreating = false;
          _statusMessage = '';
        });
        AppSnackbar.showSnackbarError('Failed to create app. Please try again.');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF0F0F14),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Handle bar
          Container(
            width: 40,
            height: 4,
            margin: const EdgeInsets.only(top: 12),
            decoration: BoxDecoration(
              color: Colors.grey.shade700,
              borderRadius: BorderRadius.circular(2),
            ),
          ),

          // Header
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(
                    Icons.auto_fix_high,
                    color: Colors.white,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 14),
                const Expanded(
                  child: Text(
                    'Create Custom Template',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                IconButton(
                  onPressed: _isCreating ? null : () => Navigator.pop(context),
                  icon: Icon(
                    Icons.close,
                    color: Colors.grey.shade500,
                  ),
                ),
              ],
            ),
          ),

          // Form content
          Flexible(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Name field
                    Text(
                      'Template Name',
                      style: TextStyle(
                        color: Colors.grey.shade300,
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextFormField(
                      controller: _nameController,
                      enabled: !_isCreating,
                      style: const TextStyle(color: Colors.white),
                      decoration: InputDecoration(
                        hintText: 'e.g., Meeting Action Items Extractor',
                        hintStyle: TextStyle(color: Colors.grey.shade600),
                        filled: true,
                        fillColor: const Color(0xFF1F1F25),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide.none,
                        ),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                      ),
                      validator: (value) {
                        if (value == null || value.trim().isEmpty) {
                          return 'Please enter a name for your app';
                        }
                        if (value.trim().length < 3) {
                          return 'Name must be at least 3 characters';
                        }
                        return null;
                      },
                    ),

                    const SizedBox(height: 20),

                    // Prompt field
                    Text(
                      'Conversation Prompt',
                      style: TextStyle(
                        color: Colors.grey.shade300,
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextFormField(
                      controller: _promptController,
                      enabled: !_isCreating,
                      style: const TextStyle(color: Colors.white),
                      maxLines: 4,
                      decoration: InputDecoration(
                        hintText:
                            'e.g., Extract action items, decisions made, and key takeaways from the provided conversation.',
                        hintStyle: TextStyle(color: Colors.grey.shade600),
                        filled: true,
                        fillColor: const Color(0xFF1F1F25),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide.none,
                        ),
                        contentPadding: const EdgeInsets.all(16),
                      ),
                      validator: (value) {
                        if (value == null || value.trim().isEmpty) {
                          return 'Please enter a prompt for your app';
                        }
                        if (value.trim().length < 10) {
                          return 'Prompt must be at least 10 characters';
                        }
                        return null;
                      },
                    ),

                    const SizedBox(height: 20),

                    // Public toggle
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1F1F25),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: const Color(0xFF2A2A2E),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Center(
                              child: FaIcon(
                                _isPublic ? FontAwesomeIcons.globe : FontAwesomeIcons.lock,
                                color: Colors.grey.shade400,
                                size: 16,
                              ),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Make public',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  _isPublic ? 'Anyone can discover your template' : 'Only you can use this template',
                                  style: TextStyle(
                                    color: Colors.grey.shade500,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Switch(
                            value: _isPublic,
                            onChanged: _isCreating
                                ? null
                                : (value) {
                                    setState(() {
                                      _isPublic = value;
                                    });
                                  },
                            activeColor: const Color(0xFF6366F1),
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 24),

                    // Create button
                    SizedBox(
                      width: double.infinity,
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        child: ElevatedButton(
                          onPressed: _isCreating ? null : _createTemplate,
                          style: ElevatedButton.styleFrom(
                            backgroundColor: _isCreating ? const Color(0xFF2A2A2E) : Colors.white,
                            foregroundColor: Colors.black,
                            padding: const EdgeInsets.symmetric(vertical: 16),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            elevation: 0,
                          ),
                          child: _isCreating
                              ? Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    const SizedBox(
                                      width: 18,
                                      height: 18,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    Text(
                                      _statusMessage,
                                      style: const TextStyle(
                                        color: Colors.white,
                                        fontSize: 16,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ],
                                )
                              : const Text(
                                  'Create App',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                        ),
                      ),
                    ),

                    SizedBox(height: MediaQuery.of(context).padding.bottom + 8),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Shows the create template bottom sheet
void showCreateTemplateBottomSheet(BuildContext context, {String? conversationId}) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (context) => DraggableScrollableSheet(
      initialChildSize: 0.65,
      minChildSize: 0.4,
      maxChildSize: 0.85,
      expand: false,
      builder: (context, _) => CreateTemplateBottomSheet(
        conversationId: conversationId,
      ),
    ),
  );
}

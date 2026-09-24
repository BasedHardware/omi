import 'dart:io';
import 'dart:ui' as ui;

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/template_creation_outcome.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/ui/ui.dart';

class CreateTemplateBottomSheet extends StatefulWidget {
  final String? conversationId;

  const CreateTemplateBottomSheet({super.key, this.conversationId});

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
    canvas.drawRect(const Rect.fromLTWH(0, 0, size, size), bgPaint);

    // Draw emoji text
    final textPainter = TextPainter(
      text: TextSpan(
          text: emoji, style: const TextStyle(fontSize: 140)), // omi-ux-allow: font-size-literal -- icon bitmap
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
      _statusMessage = context.l10n.generatingDescription;
    });

    try {
      final name = _nameController.text.trim();
      final prompt = _promptController.text.trim();
      const category = 'conversation-analysis';

      // Generate description and emoji using AI
      final result = await getGeneratedDescriptionAndEmoji(name, prompt);
      final description = result.description;
      final emoji = result.emoji;
      if (!mounted) return;

      setState(() {
        _statusMessage = context.l10n.creatingAppIcon;
      });

      // Create simple emoji icon
      final iconFile = await _createEmojiIcon(emoji);
      if (!mounted) return;

      setState(() {
        _statusMessage = context.l10n.creatingYourApp;
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
        PlatformManager.instance.analytics.quickTemplateCreated(
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
            _statusMessage = context.l10n.installingApp;
          });

          // Enable/install through the provider: it owns prefs, app-list
          // state, and the failure dialog, so a failed install can no longer
          // be reported as success (#10074 follow-up).
          final success = await context.read<AppProvider>().toggleApp(createdApp.id, true, null);
          if (success) {
            createdApp.enabled = true;

            // Update the conversation detail provider's cached apps
            if (mounted) {
              final conversationProvider = context.read<ConversationDetailProvider>();
              conversationProvider.addToEnabledConversationApps(createdApp);
            }
          }

          if (mounted) {
            // Close the create template sheet; follow-up sheets open from the navigator, which
            // outlives it.
            final navigatorContext = Navigator.of(context).context;
            Navigator.pop(context);
            // Polarity comes from the tested classifier so a failed install
            // can never be reported as success (#10074).
            final outcome = success ? TemplateCreationOutcome.installed : TemplateCreationOutcome.installFailed;
            if (templateCreationOutcomeIsError(outcome)) {
              // The provider already showed the failure dialog; tell the user
              // what state they are actually in.
              AppSnackbar.showSnackbarError(context.l10n.failedToInstallApp(createdApp.name));
            } else {
              AppSnackbar.showSnackbarSuccess(context.l10n.appCreatedAndInstalled);

              // Show the summarized apps sheet so user can use the new app
              if (navigatorContext.mounted) showSummarizedAppsSheet(navigatorContext);
            }
          }
        } else if (mounted) {
          Navigator.pop(context);
          AppSnackbar.showSnackbarSuccess(context.l10n.appCreatedSuccessfully);
        }
      } else {
        // Error
        if (mounted) {
          setState(() {
            _isCreating = false;
            _statusMessage = '';
          });
          AppSnackbar.showSnackbarError(submitResult.$2.isNotEmpty ? submitResult.$2 : context.l10n.failedToCreateApp);
        }
      }
    } catch (e) {
      Logger.debug('Error creating template: $e');
      if (mounted) {
        setState(() {
          _isCreating = false;
          _statusMessage = '';
        });
        AppSnackbar.showSnackbarError(context.l10n.failedToCreateApp);
      }
    }
  }

  InputDecoration _fieldDecoration(String hint) => InputDecoration(
        hintText: hint,
        hintStyle: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
        filled: true,
        fillColor: OmiColors.surface2,
        border: const OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
        contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
      );

  Widget _fieldLabel(String text) => Padding(
        padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
        child:
            Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500)),
      );

  @override
  Widget build(BuildContext context) {
    return PopScope(
      // Leaving while the template is being created would orphan the request's result.
      canPop: !_isCreating,
      child: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(vertical: OmiSpacing.md),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _fieldLabel(context.l10n.templateName),
                TextFormField(
                  controller: _nameController,
                  enabled: !_isCreating,
                  style: OmiType.subhead,
                  decoration: _fieldDecoration(context.l10n.templateNameHint),
                  validator: (value) {
                    if (value == null || value.trim().isEmpty) {
                      return context.l10n.pleaseEnterAppName;
                    }
                    if (value.trim().length < 3) {
                      return context.l10n.nameMustBeAtLeast3Characters;
                    }
                    return null;
                  },
                ),
                const SizedBox(height: OmiSpacing.lg),
                _fieldLabel(context.l10n.conversationPrompt),
                TextFormField(
                  controller: _promptController,
                  enabled: !_isCreating,
                  style: OmiType.subhead,
                  maxLines: 4,
                  decoration: _fieldDecoration(context.l10n.conversationPromptHint),
                  validator: (value) {
                    if (value == null || value.trim().isEmpty) {
                      return context.l10n.pleaseEnterAppPrompt;
                    }
                    if (value.trim().length < 10) {
                      return context.l10n.promptMustBeAtLeast10Characters;
                    }
                    return null;
                  },
                ),
                const SizedBox(height: OmiSpacing.lg),
                Container(
                  padding: const EdgeInsets.all(OmiSpacing.md),
                  decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                  child: Row(
                    children: [
                      FaIcon(
                        _isPublic ? FontAwesomeIcons.globe : FontAwesomeIcons.lock,
                        color: OmiColors.textSecondary,
                        size: 16,
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(context.l10n.makePublic, style: OmiType.callout.copyWith(fontWeight: FontWeight.w500)),
                            const SizedBox(height: 2),
                            Text(
                              _isPublic ? context.l10n.anyoneCanDiscoverTemplate : context.l10n.onlyYouCanUseTemplate,
                              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                            ),
                          ],
                        ),
                      ),
                      OmiSwitch(
                        value: _isPublic,
                        onChanged: _isCreating ? null : (value) => setState(() => _isPublic = value),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: OmiSpacing.xl),
                OmiButton(
                  label: _isCreating ? _statusMessage : context.l10n.createApp,
                  expand: true,
                  isLoading: _isCreating,
                  onPressed: _isCreating ? null : _createTemplate,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Shows the create template bottom sheet
void showCreateTemplateBottomSheet(BuildContext context, {String? conversationId}) {
  showOmiSheet<void>(
    context: context,
    title: context.l10n.createCustomTemplate,
    builder: (_) => CreateTemplateBottomSheet(conversationId: conversationId),
  );
}

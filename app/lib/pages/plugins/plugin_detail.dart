import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:friend_private/backend/http/api/plugins.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/plugins/instructions.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/services/translation_service.dart';

import '../../backend/schema/plugin.dart';

class PluginDetailPage extends StatefulWidget {
  final Plugin plugin;

  const PluginDetailPage({super.key, required this.plugin});

  @override
  State<PluginDetailPage> createState() => _PluginDetailPageState();
}

class _PluginDetailPageState extends State<PluginDetailPage> {
  String? instructionsMarkdown;
  bool setupCompleted = false;
  bool pluginLoading = false;

  checkSetupCompleted() {
    // TODO: move check to backend
    isPluginSetupCompleted(widget.plugin.externalIntegration!.setupCompletedUrl).then((value) {
      if (mounted) {
        setState(() => setupCompleted = value);
      }
    });
  }

  @override
  void initState() {
    if (widget.plugin.worksExternally()) {
      getPluginMarkdown(widget.plugin.externalIntegration!.setupInstructionsFilePath).then((value) {
        value = value.replaceAll(
          '](assets/',
          '](https://raw.githubusercontent.com/BasedHardware/Omi/main/plugins/instructions/${widget.plugin.id}/assets/',
        );
        setState(() => instructionsMarkdown = value);
      });
      checkSetupCompleted();
    }

    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    bool isMemoryPrompt = widget.plugin.worksWithMemories();
    bool isChatPrompt = widget.plugin.worksWithChat();
    bool isIntegration = widget.plugin.worksExternally();

    return Scaffold(
        appBar: AppBar(
          title: Text(widget.plugin.name),
          backgroundColor: Theme.of(context).colorScheme.primary,
          elevation: 0,
        ),
        backgroundColor: Theme.of(context).colorScheme.primary,
        body: ListView(
          children: [
            const SizedBox(height: 32),
            ListTile(
              leading: CachedNetworkImage(
                imageUrl: widget.plugin.getImageUrl(),
                imageBuilder: (context, imageProvider) => Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    shape: BoxShape.rectangle,
                    borderRadius: BorderRadius.circular(8),
                    image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                  ),
                ),
                placeholder: (context, url) => const CircularProgressIndicator(),
                errorWidget: (context, url, error) => const Icon(Icons.error),
              ),
              title: Column(
                mainAxisAlignment: MainAxisAlignment.start,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(height: widget.plugin.ratingAvg != null ? 4 : 0),
                  Text(
                    widget.plugin.description,
                    style: const TextStyle(color: Colors.grey, fontSize: 14),
                  ),
                  SizedBox(height: widget.plugin.ratingAvg != null ? 4 : 0),
                  widget.plugin.ratingAvg != null
                      ? Row(
                          children: [
                            Text(widget.plugin.getRatingAvg()!),
                            const SizedBox(width: 4),
                            RatingBar.builder(
                              initialRating: widget.plugin.ratingAvg!,
                              minRating: 1,
                              ignoreGestures: true,
                              direction: Axis.horizontal,
                              allowHalfRating: true,
                              itemCount: 5,
                              itemSize: 16,
                              tapOnlyMode: false,
                              itemPadding: const EdgeInsets.symmetric(horizontal: 0),
                              itemBuilder: (context, _) => const Icon(Icons.star, color: Colors.deepPurple),
                              maxRating: 5.0,
                              onRatingUpdate: (rating) {},
                            ),
                            const SizedBox(width: 4),
                            Text('(${widget.plugin.ratingCount})'),
                          ],
                        )
                      : Container(),
                ],
              ),
              trailing: pluginLoading
                  ? const SizedBox(
                      height: 24,
                      width: 24,
                      child: CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
                    )
                  : IconButton(
                      icon: Icon(
                        widget.plugin.enabled ? Icons.check : Icons.arrow_downward_rounded,
                        color: widget.plugin.enabled ? Colors.white : Colors.grey,
                      ),
                      onPressed: () {
                        final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                        if (!connectivityProvider.isConnected) {
                          ScaffoldMessenger.of(context).showSnackBar( SnackBar(
                            content: Text(TranslationService.translate("Can't enable plugin without internet connection.")),
                          ));
                          return;
                        }
                        if (widget.plugin.worksExternally() && !widget.plugin.enabled) {
                          showDialog(
                            context: context,
                            builder: (c) => getDialog(
                              context,
                              () => Navigator.pop(context),
                              () {
                                Navigator.pop(context);
                                _togglePlugin(widget.plugin.id.toString(), !widget.plugin.enabled);
                              },
                            TranslationService.translate('Authorize External Plugin'),
                        TranslationService.translate('Do you allow this plugin to access your memories, transcripts, and recordings? Your data will be sent to the plugin\'s server for processing.'),
                              okButtonText: TranslationService.translate('Confirm'),
                            ),
                          );
                        } else {
                          _togglePlugin(widget.plugin.id.toString(), !widget.plugin.enabled);
                        }
                      },
                    ),
            ),
            const SizedBox(height: 16),
            isMemoryPrompt
                ? const Padding(
                    padding: EdgeInsets.all(16),
                    child: Text(
                      'Memories Prompt',
                      style: TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
                    ),
                  )
                : const SizedBox.shrink(),
            isMemoryPrompt
                ? Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      (widget.plugin.memoryPrompt ?? '').decodeSting,
                      style: const TextStyle(color: Colors.grey, fontSize: 15, height: 1.4),
                    ),
                  )
                : const SizedBox.shrink(),
            isChatPrompt ? const SizedBox(height: 16) : const SizedBox.shrink(),
            isChatPrompt
                ? const Padding(
                    padding: EdgeInsets.all(16),
                    child: Text(
                      'Chat Personality',
                      style: TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
                    ),
                  )
                : const SizedBox.shrink(),
            isChatPrompt
                ? Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      widget.plugin.chatPrompt ?? '',
                      style: const TextStyle(color: Colors.grey, fontSize: 15, height: 1.4),
                    ),
                  )
                : const SizedBox.shrink(),
            isIntegration ? const SizedBox(height: 16) : const SizedBox.shrink(),
            isIntegration && widget.plugin.externalIntegration?.setupInstructionsFilePath.isNotEmpty == true
                ? ListTile(
                    onTap: () async {
                      await routeToPage(
                        context,
                        PluginSetupInstructions(markdown: instructionsMarkdown ?? ''),
                      );
                      checkSetupCompleted();
                    },
                    trailing: const Padding(
                      padding: EdgeInsets.only(right: 12.0),
                      child: Icon(Icons.arrow_forward_ios, size: 20, color: Colors.grey),
                    ),
                    title: Text(
                      TranslationService.translate('Integration Instructions'),
                      style: TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
                    ),
                  )
                : const SizedBox.shrink(),
            isIntegration && widget.plugin.externalIntegration?.setupCompletedUrl != null
                ? CheckboxListTile(
                    title: Text(TranslationService.translate('Setup Completed ?')),
                    contentPadding: const EdgeInsets.only(left: 16, right: 18),
                    value: setupCompleted,
                    checkboxShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    onChanged: (s) {},
                    enabled: false,
                  )
                : const SizedBox.shrink(),
            // widget.plugin.worksExternally() ? const SizedBox(height: 16) : const SizedBox.shrink(),
            const SizedBox(height: 24),
            Row(
              mainAxisAlignment: MainAxisAlignment.start,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                    widget.plugin.userReview?.score == null ? TranslationService.translate(TranslationService.translate('Rate it')+':') : TranslationService.translate('Your rating:'),
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 0),
                  child: RatingBar.builder(
                    initialRating: widget.plugin.userReview?.score ?? 0,
                    minRating: 1,
                    direction: Axis.horizontal,
                    allowHalfRating: true,
                    itemCount: 5,
                    itemSize: 24,
                    itemPadding: const EdgeInsets.symmetric(horizontal: 2),
                    itemBuilder: (context, _) => const Icon(Icons.star, color: Colors.deepPurple),
                    maxRating: 5.0,
                    onRatingUpdate: (rating) {
                      final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                      if (connectivityProvider.isConnected) {
                        reviewPlugin(widget.plugin.id, rating);
                        bool hadReview = widget.plugin.userReview != null;
                        if (!hadReview) widget.plugin.ratingCount += 1;
                        widget.plugin.userReview = PluginReview(
                          uid: SharedPreferencesUtil().uid,
                          ratedAt: DateTime.now(),
                          review: '',
                          score: rating,
                        );
                        var pluginsList = SharedPreferencesUtil().pluginsList;
                        var index = pluginsList.indexWhere((element) => element.id == widget.plugin.id);
                        pluginsList[index] = widget.plugin;
                        SharedPreferencesUtil().pluginsList = pluginsList;
                        MixpanelManager().pluginRated(widget.plugin.id.toString(), rating);
                        debugPrint('Refreshed plugins list.');
                        // TODO: refresh ratings on plugin
                        setState(() {});
                      } else {
                        ScaffoldMessenger.of(context).showSnackBar( SnackBar(
                          content: Text(TranslationService.translate("Can't rate plugin without internet connection.")),
                        ));
                      }
                    },
                  ),
                ),
              ],
            ),

            const SizedBox(height: 32),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18.0),
              child: RichText(
                  text: TextSpan(children: [TextSpan(text: TranslationService.translate('By')+': ', style: TextStyle(fontSize: 16)),
                TextSpan(
                  text: '${widget.plugin.author}.',
                  style: const TextStyle(fontSize: 16, fontStyle: FontStyle.italic, color: Colors.grey),
                ),
              ])),
            ),
            const SizedBox(height: 32),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.start,
                children: [
                  const SizedBox(width: 2),
                  isMemoryPrompt
                      ? Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.grey,
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            TranslationService.translate('Memories'),
                            style: TextStyle(color: Colors.deepPurple, fontSize: 14, fontWeight: FontWeight.w500),
                          ),
                        )
                      : const SizedBox.shrink(),
                  SizedBox(width: isMemoryPrompt && isChatPrompt ? 8 : 0),
                  isChatPrompt
                      ? Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.grey,
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: const Text(
                            'Chat',
                            style: TextStyle(color: Colors.deepPurple, fontSize: 14, fontWeight: FontWeight.w500),
                          ),
                        )
                      : const SizedBox.shrink(),
                  SizedBox(width: isChatPrompt ? 8 : 0),
                  ([isMemoryPrompt, isChatPrompt, isIntegration].where((value) => value).length > 1) && isIntegration
                      ? Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.grey,
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: const Text(
                            'Integration',
                            style: TextStyle(color: Colors.deepPurple, fontSize: 14, fontWeight: FontWeight.w500),
                          ),
                        )
                      : const SizedBox.shrink(),
                ],
              ),
            ),
            const SizedBox(height: 24),
          ],
        ));
  }

  Future<void> _togglePlugin(String pluginId, bool isEnabled) async {
    var prefs = SharedPreferencesUtil();
    setState(() => pluginLoading = true);
    if (isEnabled) {
      var enabled = await enablePluginServer(pluginId);
      if (!enabled) {
        if (mounted) {
          showDialog(
            context: context,
            builder: (c) => getDialog(
              context,
              () => Navigator.pop(context),
              () => Navigator.pop(context),
              TranslationService.translate('Error activating the plugin'),
                TranslationService.translate('If this is an integration plugin, make sure the setup is completed.'),
              singleButton: true,
            ),
          );
        }

        setState(() => pluginLoading = false);
        return;
      }

      prefs.enablePlugin(pluginId);
      MixpanelManager().pluginEnabled(pluginId);
    } else {
      prefs.disablePlugin(pluginId);
      await enablePluginServer(pluginId);
      MixpanelManager().pluginDisabled(pluginId);
    }
    setState(() => widget.plugin.enabled = isEnabled);
    setState(() => pluginLoading = false);
  }
}

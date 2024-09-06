import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/plugins.dart';
import 'package:friend_private/firebase/model/plugin_model.dart';
import 'package:friend_private/firebase/model/user_memories_model.dart';
import 'package:friend_private/pages/plugins/instructions.dart';
import 'package:friend_private/utils/connectivity_controller.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/extensions/string.dart';

class PluginTabDetailPage extends StatefulWidget {
  final UserMemoriesModel userMemoriesModel;
  final PluginModel pluginModel;

  const PluginTabDetailPage(
      {super.key, required this.userMemoriesModel, required this.pluginModel});

  @override
  State<PluginTabDetailPage> createState() => _PluginTabDetailPageState();
}

class _PluginTabDetailPageState extends State<PluginTabDetailPage> {
  String? instructionsMarkdown;
  bool setupCompleted = false;
  bool pluginLoading = false;

  checkSetupCompleted() {
    isPluginSetupCompleted(
            widget.pluginModel.externalIntegration!.setupCompletedUrl)
        .then((value) {
      setState(() => setupCompleted = value);
    });
  }

  @override
  void initState() {
    if (widget.pluginModel.worksExternally()) {
      getPluginMarkdown(widget
              .pluginModel.externalIntegration!.setupInstructionsFilePath!)
          .then((value) {
        value = value.replaceAll(
          '](assets/',
          '](https://raw.githubusercontent.com/BasedHardware/Friend/main/plugins/instructions/${widget.pluginModel.id}/assets/',
        );
        setState(() => instructionsMarkdown = value);
      });
      checkSetupCompleted();
    }

    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
        appBar: AppBar(
          title: Text(widget.pluginModel.name ?? ""),
          backgroundColor: Theme.of(context).colorScheme.primary,
          elevation: 0,
        ),
        backgroundColor: Theme.of(context).colorScheme.primary,
        body: ListView(
          children: [
            const SizedBox(height: 32),
            ListTile(
              leading: CircleAvatar(
                backgroundColor: Colors.white,
                maxRadius: 28,
                child: CachedNetworkImage(
                  imageUrl: widget.pluginModel.image ?? "",
                  imageBuilder: (context, imageProvider) => CircleAvatar(
                    backgroundColor: Colors.white,
                    maxRadius: 28,
                    backgroundImage: imageProvider,
                  ),
                  placeholder: (context, url) =>
                      const CircularProgressIndicator(),
                  errorWidget: (context, url, error) => const Icon(Icons.error),
                ),
              ),
              title: Column(
                mainAxisAlignment: MainAxisAlignment.start,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  //SizedBox(height: widget.plugin.ratingAvg != null ? 4 : 0),
                  Padding(
                    padding: const EdgeInsets.only(top: 4.0),
                    child: Text(
                      widget.pluginModel.description ?? "",
                      style: const TextStyle(color: Colors.grey, fontSize: 14),
                    ),
                  ),
                  /*SizedBox(height: widget.plugin.ratingAvg != null ? 4 : 0),
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
                              itemPadding:
                                  const EdgeInsets.symmetric(horizontal: 0),
                              itemBuilder: (context, _) => const Icon(
                                  Icons.star,
                                  color: Colors.deepPurple),
                              maxRating: 5.0,
                              onRatingUpdate: (rating) {},
                            ),
                            const SizedBox(width: 4),
                            Text('(${widget.plugin.ratingCount})'),
                          ],
                        )
                      : Container(),*/
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
                      icon: const Icon(Icons.check, color: Colors.white),
                      onPressed: () {
                        if (!ConnectivityController().isConnected.value) {
                          ScaffoldMessenger.of(context)
                              .showSnackBar(const SnackBar(
                            content: Text(
                                "Can't enable plugin without internet connection."),
                          ));
                          return;
                        }
                      },
                    ),
            ),
            const SizedBox(height: 16),
            widget.pluginModel.worksWithMemories()
                ? const Padding(
                    padding: EdgeInsets.all(16),
                    child: Text(
                      'Memories Prompt',
                      style:
                          TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
                    ),
                  )
                : const SizedBox.shrink(),
            widget.pluginModel.worksWithMemories()
                ? Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      (widget.pluginModel.memoryPrompt ?? '').decodeSting,
                      style: const TextStyle(
                          color: Colors.grey, fontSize: 15, height: 1.4),
                    ),
                  )
                : const SizedBox.shrink(),
            widget.pluginModel.worksWithChat()
                ? const SizedBox(height: 16)
                : const SizedBox.shrink(),
            widget.pluginModel.worksWithChat()
                ? const Padding(
                    padding: EdgeInsets.all(16),
                    child: Text(
                      'Chat Prompt',
                      style:
                          TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
                    ),
                  )
                : const SizedBox.shrink(),
            widget.pluginModel.worksWithChat()
                ? Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      widget.pluginModel.chatPrompt!,
                      style: const TextStyle(
                          color: Colors.grey, fontSize: 15, height: 1.4),
                    ),
                  )
                : const SizedBox.shrink(),
            widget.pluginModel.worksExternally()
                ? const SizedBox(height: 16)
                : const SizedBox.shrink(),
            widget.pluginModel.worksExternally()
                ? ListTile(
                    onTap: () async {
                      await routeToPage(
                        context,
                        PluginSetupInstructions(
                            markdown: instructionsMarkdown ?? ''),
                      );
                      checkSetupCompleted();
                    },
                    trailing: const Padding(
                      padding: EdgeInsets.only(right: 12.0),
                      child: Icon(
                        Icons.arrow_forward_ios,
                        size: 20,
                        color: Colors.grey,
                      ),
                    ),
                    title: const Text(
                      'Integration Instructions',
                      style:
                          TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
                    ),
                    subtitle: Text(
                      'Triggers on ${widget.pluginModel.externalIntegration!.getTriggerOnString()}',
                      style: const TextStyle(
                          fontWeight: FontWeight.w400, fontSize: 14),
                    ),
                  )
                : const SizedBox.shrink(),
            widget.pluginModel.worksExternally() &&
                    widget.pluginModel.externalIntegration?.setupCompletedUrl !=
                        null
                ? CheckboxListTile(
                    title: const Text('Setup Completed'),
                    value: setupCompleted,
                    checkboxShape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16)),
                    onChanged: (s) {},
                    enabled: false,
                  )
                : const SizedBox.shrink(),
            widget.pluginModel.worksExternally()
                ? const SizedBox(height: 16)
                : const SizedBox.shrink(),
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18.0),
              child: RichText(
                  text: TextSpan(children: [
                const TextSpan(
                  text: 'By: ',
                  style: TextStyle(fontSize: 16),
                ),
                TextSpan(
                  text: '${widget.pluginModel.author}.',
                  style: const TextStyle(
                      fontSize: 16,
                      fontStyle: FontStyle.italic,
                      color: Colors.grey),
                ),
              ])),
            ),
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.start,
                children: [
                  const Text(
                    'Works with',
                    style: TextStyle(fontSize: 16),
                  ),
                  const SizedBox(width: 16),
                  widget.pluginModel.worksWithMemories()
                      ? Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.grey,
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: const Text(
                            'Memories',
                            style: TextStyle(
                                color: Colors.deepPurple,
                                fontSize: 14,
                                fontWeight: FontWeight.w500),
                          ),
                        )
                      : const SizedBox.shrink(),
                  SizedBox(width: widget.pluginModel.worksWithChat() ? 8 : 0),
                  widget.pluginModel.worksWithMemories()
                      ? Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.grey,
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: const Text(
                            'Chat',
                            style: TextStyle(
                                color: Colors.deepPurple,
                                fontSize: 14,
                                fontWeight: FontWeight.w500),
                          ),
                        )
                      : const SizedBox.shrink(),
                  SizedBox(width: widget.pluginModel.worksWithChat() ? 8 : 0),
                  widget.pluginModel.worksExternally()
                      ? Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.grey,
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: const Text(
                            'Integration',
                            style: TextStyle(
                                color: Colors.deepPurple,
                                fontSize: 14,
                                fontWeight: FontWeight.w500),
                          ),
                        )
                      : const SizedBox.shrink(),
                ],
              ),
            ),
            const SizedBox(height: 32),
            /*const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                'Your rating:',
                style: TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
              ),
            ),
            const SizedBox(height: 8),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14),
              child: RatingBar.builder(
                initialRating: widget.plugin.userReview?.score ?? 0,
                minRating: 1,
                direction: Axis.horizontal,
                allowHalfRating: true,
                itemCount: 5,
                itemSize: 24,
                itemPadding: const EdgeInsets.symmetric(horizontal: 2),
                itemBuilder: (context, _) =>
                    const Icon(Icons.star, color: Colors.deepPurple),
                maxRating: 5.0,
                onRatingUpdate: (rating) {
                  if (ConnectivityController().isConnected.value) {
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
                    var index = pluginsList.indexWhere(
                        (element) => element.id == widget.plugin.id);
                    pluginsList[index] = widget.plugin;
                    SharedPreferencesUtil().pluginsList = pluginsList;
                    MixpanelManager()
                        .pluginRated(widget.plugin.id.toString(), rating);
                    debugPrint('Refreshed plugins list.');
                    // TODO: refresh ratings on plugin
                    setState(() {});
                  } else {
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text(
                          "Can't rate plugin without internet connection."),
                    ));
                  }
                },
              ),
            ),
            const SizedBox(height: 24),*/
          ],
        ));
  }
}

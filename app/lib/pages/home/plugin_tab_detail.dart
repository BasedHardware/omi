import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/plugins.dart';
import 'package:friend_private/firebase/model/plugin_model.dart';
import 'package:friend_private/firebase/model/user_memories_model.dart';
import 'package:friend_private/pages/home/plugin_detail_post.dart';
import 'package:friend_private/pages/home/plugin_detail_profile.dart';
import 'package:friend_private/pages/home/subscription.dart';

class PluginTabDetailPage extends StatefulWidget {
  final UserMemoriesModel userMemoriesModel;
  final PluginModel pluginModel;
  final List<UserMemoriesModel> userMemoriesModels;
  final List<PluginModel> pluginsModels;

  const PluginTabDetailPage(
      {super.key,
      required this.userMemoriesModel,
      required this.pluginModel,
      required this.userMemoriesModels,
      required this.pluginsModels});

  @override
  State<PluginTabDetailPage> createState() => _PluginTabDetailPageState();
}

class _PluginTabDetailPageState extends State<PluginTabDetailPage> {
  String? instructionsMarkdown;
  bool setupCompleted = false;

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
          '](https://raw.githubusercontent.com/maxwell882000/shopify-components/main/plugins/instructions/${widget.pluginModel.id}/assets/',
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
        body: Column(
          children: [
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
              trailing: GestureDetector(
                onTap: () {
                  Navigator.of(context).push(MaterialPageRoute(
                      builder: (c) => const SubscriptionPage()));
                },
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.deepPurple,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: Colors.deepPurple),
                  ),
                  child: const Text(
                    'Subscribe',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.w500),
                  ),
                ),
              ),
              /*IconButton(
                icon: const Icon(Icons.check, color: Colors.white),
                onPressed: () {
                  if (!ConnectivityController().isConnected.value) {
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text(
                          "Can't enable plugin without internet connection."),
                    ));
                    return;
                  }
                },
              ),*/
            ),
            Expanded(
              child: DefaultTabController(
                length: 2, // Number of tabs
                child: Column(
                  children: [
                    const TabBar(
                      tabs: [
                        Tab(text: 'Posts'),
                        Tab(text: 'Profile'),
                      ],
                      labelColor: Colors.white,
                      unselectedLabelColor: Colors.grey,
                      indicatorColor: Colors.deepPurple,
                    ),
                    Expanded(
                      child: TabBarView(
                        children: [
                          PluginDetailPostPage(
                              pluginModel: widget.pluginModel,
                              userMemoriesModels: widget.userMemoriesModels,
                              pluginsModels: widget.pluginsModels),
                          PluginDetailProfilePage(
                              userMemoriesModel: widget.userMemoriesModel,
                              pluginModel: widget.pluginModel)
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ));
  }
}

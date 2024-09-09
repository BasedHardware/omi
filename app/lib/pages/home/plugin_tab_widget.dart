import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/firebase/model/plugin_model.dart';
import 'package:friend_private/firebase/model/user_memories_model.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/expandable_text.dart';
import 'package:share_plus/share_plus.dart';

class PluginTabWidget extends StatefulWidget {
  final UserMemoriesModel userMemoriesModel;
  final PluginsResult pluginsResult;
  final PluginModel pluginModel;
  final Function onTap;
  final bool isDividerShow;
  final bool isInstallButtonShow;

  const PluginTabWidget(
      {super.key,
      required this.userMemoriesModel,
      required this.pluginsResult,
      required this.pluginModel,
      required this.onTap,
      required this.isDividerShow,
      required this.isInstallButtonShow});

  @override
  State<PluginTabWidget> createState() => _PluginTabWidgetState();
}

class _PluginTabWidgetState extends State<PluginTabWidget> {
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        widget.onTap();
      },
      child: Container(
        padding: const EdgeInsets.only(top: 5),
        decoration: const BoxDecoration(
          shape: BoxShape.rectangle,
          color: Colors.black,
        ),
        child: (widget.userMemoriesModel.pluginsResults != null &&
                widget.userMemoriesModel.pluginsResults!.isNotEmpty)
            ? Column(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          margin: const EdgeInsets.only(top: 5),
                          child: CachedNetworkImage(
                            imageUrl: widget.pluginModel.image!,
                            imageBuilder: (context, imageProvider) =>
                                CircleAvatar(
                              backgroundColor: Colors.white,
                              maxRadius: 18,
                              backgroundImage: imageProvider,
                            ),
                            placeholder: (context, url) =>
                                const CircularProgressIndicator(),
                            errorWidget: (context, url, error) =>
                                const Icon(Icons.error),
                          ),
                        ),
                        const SizedBox(width: 5),
                        Expanded(
                          child: Column(
                            children: [
                              Container(
                                height: 45,
                                padding: const EdgeInsets.only(left: 5),
                                alignment: Alignment.center,
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.center,
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        mainAxisAlignment:
                                            MainAxisAlignment.center,
                                        children: [
                                          Text(
                                            widget.pluginModel.name ?? "",
                                            maxLines: 1,
                                            style: const TextStyle(
                                                fontWeight: FontWeight.w600,
                                                color: Colors.white,
                                                fontSize: 16),
                                          ),
                                          Text(
                                            widget.pluginModel.description ??
                                                "",
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: const TextStyle(
                                                color: Colors.grey,
                                                fontSize: 14),
                                          ),
                                        ],
                                      ),
                                    ),
                                    (widget.isInstallButtonShow)
                                        ? const Icon(Icons.check,
                                            size: 20, color: Colors.grey)
                                        : Container(),
                                  ],
                                ),
                              ),
                              Padding(
                                padding: const EdgeInsets.only(
                                    top: 5, right: 5, left: 5),
                                child: ExpandableTextWidget(
                                  onTap: () {
                                    widget.onTap();
                                  },
                                  text: widget.pluginsResult.content ?? '',
                                  isExpanded: widget.pluginsResult.isExpanded,
                                  toggleExpand: () {
                                    widget.pluginsResult.isExpanded =
                                        !widget.pluginsResult.isExpanded;
                                    setState(() {});
                                  },
                                  style: TextStyle(
                                      color: Colors.grey.shade300,
                                      fontSize: 15,
                                      height: 1.3),
                                  linkColor: Colors.white,
                                ),
                              ),
                              Container(
                                color: Colors.transparent,
                                padding:
                                    const EdgeInsets.symmetric(vertical: 2),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.center,
                                  children: [
                                    GestureDetector(
                                      onTap: () {
                                        widget.pluginsResult.isFavourite =
                                            !widget.pluginsResult.isFavourite;
                                        setState(() {});
                                      },
                                      child: Container(
                                        padding: const EdgeInsets.fromLTRB(
                                            0, 8, 6, 5),
                                        child: Icon(
                                          widget.pluginsResult.isFavourite
                                              ? Icons.bookmark_outlined
                                              : Icons.bookmark_outline,
                                          size: 20,
                                          color: Colors.grey,
                                        ),
                                      ),
                                    ),
                                    GestureDetector(
                                      onTap: () async {
                                        await Share.share(
                                            widget.pluginsResult.content ?? '');
                                      },
                                      child: Container(
                                        padding: const EdgeInsets.fromLTRB(
                                            6, 5, 5, 5),
                                        child: const Icon(
                                          Icons.ios_share,
                                          size: 20,
                                          color: Colors.grey,
                                        ),
                                      ),
                                    ),
                                    const Spacer(),
                                    Container(
                                      padding: const EdgeInsets.only(right: 10),
                                      child: Text(
                                        dateTimeFormat(
                                            'MMM d, h:mm a',
                                            widget.pluginsResult.createdAt ??
                                                DateTime.now()),
                                        style: const TextStyle(
                                            color: Colors.grey, fontSize: 12),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                  widget.isDividerShow
                      ? const Divider(color: Colors.grey)
                      : const SizedBox.shrink()
                ],
              )
            : const SizedBox.shrink(),
      ),
    );
  }
}

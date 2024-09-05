import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/expandable_text.dart';
import 'package:intl/intl.dart';
import 'package:share_plus/share_plus.dart';

class PluginTabDetailTempPage extends StatefulWidget {
  final Plugin plugin;
  final Function onTap;

  const PluginTabDetailTempPage({
    super.key,
    required this.plugin,
    required this.onTap,
  });

  @override
  State<PluginTabDetailTempPage> createState() =>
      _PluginTabDetailTempPageState();
}

class _PluginTabDetailTempPageState extends State<PluginTabDetailTempPage> {
  @override
  Widget build(BuildContext context) {
    if (widget.plugin.content != null && widget.plugin.content!.isNotEmpty) {
      return ListView.builder(
        shrinkWrap: true,
        reverse: true,
        itemCount: widget.plugin.content!.length,
        physics: const NeverScrollableScrollPhysics(),
        itemBuilder: (context, index) {
          return Stack(
            children: <Widget>[
              Positioned(
                top: 0.0,
                bottom: 0.0,
                left: 15,
                child: Container(
                  height: double.infinity,
                  width: 1.0,
                  color: Colors.grey,
                ),
              ),
              SizedBox(
                width: MediaQuery.of(context).size.width,
                child: Column(
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (index != widget.plugin.content!.length - 1)
                          Container(
                            padding: const EdgeInsets.symmetric(vertical: 5),
                            color: Colors.grey.shade900,
                            child: Container(
                              height: 26,
                              width: 26,
                              margin: const EdgeInsets.only(left: 2, right: 16),
                              decoration: const BoxDecoration(
                                shape: BoxShape.circle,
                                color: Colors.white,
                              ),
                              child: CachedNetworkImage(
                                imageUrl: widget.plugin.getImageUrl(),
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
                              /*CircleAvatar(
                                backgroundColor: Colors.white,
                                maxRadius: 18,
                                backgroundImage:
                                    NetworkImage(widget.plugin.getImageUrl()),
                              ),*/
                            ),
                          )
                        else
                          Container(
                            height: 26,
                            width: 26,
                            margin: const EdgeInsets.only(left: 2, right: 16),
                          ),
                        Expanded(
                          child: Padding(
                            padding: const EdgeInsets.only(
                                bottom: 5, top: 5, right: 5),
                            child: ExpandableTextWidget(
                              onTap: () {
                                widget.onTap();
                              },
                              text: widget.plugin.content![index].content ?? '',
                              isExpanded:
                                  widget.plugin.content![index].isExpanded,
                              toggleExpand: () {
                                widget.plugin.content![index].isExpanded =
                                    !widget.plugin.content![index].isExpanded;
                                setState(() {});
                              },
                              style: TextStyle(
                                  color: Colors.grey.shade300,
                                  fontSize: 15,
                                  height: 1.3),
                              linkColor: Colors.white,
                            ),

                            /*Text(
                              plugin.content![index].content ?? '',
                              style: const TextStyle(
                                  color: Colors.grey,
                                  fontSize: 15,
                                  height: 1.4),
                            ),*/
                          ),
                        ),
                      ],
                    ),
                    Row(
                      children: [
                        const SizedBox(width: 38),
                        GestureDetector(
                          onTap: () {
                            widget.plugin.content![index].isFavourite =
                                !widget.plugin.content![index].isFavourite;
                            setState(() {});
                          },
                          child: Container(
                            padding: const EdgeInsets.fromLTRB(5, 9, 5, 5),
                            child: Icon(
                              widget.plugin.content![index].isFavourite
                                  ? Icons.bookmark_outlined
                                  : Icons.bookmark_outline,
                              size: 17,
                              color: Colors.grey,
                            ),
                          ),
                        ),
                        GestureDetector(
                          onTap: () async {
                            await Share.share(
                                widget.plugin.content![index].content ?? '');
                          },
                          child: Container(
                            padding: const EdgeInsets.all(5),
                            child: const Icon(
                              Icons.ios_share,
                              size: 17,
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
                                DateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'")
                                    .parse(widget.plugin.content![index].date ??
                                        "")),
                            style: const TextStyle(
                                color: Colors.grey, fontSize: 12),
                          ),
                        ),
                      ],
                    ),
                    if (index != 0)
                      Container(
                          padding: const EdgeInsets.only(left: 40, right: 10),
                          child: const Divider(
                            thickness: 2,
                          ))
                  ],
                ),
              ),
            ],
          );
        },
      );
    } else {
      return Container();
    }
  }
}

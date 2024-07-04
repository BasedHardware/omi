import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:friend_private/backend/api_requests/api/server.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';

import '../../backend/storage/plugin.dart';

class PluginDetailPage extends StatefulWidget {
  final Plugin plugin;

  const PluginDetailPage({super.key, required this.plugin});

  @override
  State<PluginDetailPage> createState() => _PluginDetailPageState();
}

class _PluginDetailPageState extends State<PluginDetailPage> {
  @override
  Widget build(BuildContext context) {
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
              leading: CircleAvatar(
                backgroundColor: Colors.white,
                maxRadius: 28,
                backgroundImage:
                    NetworkImage('https://raw.githubusercontent.com/BasedHardware/Friend/main/${widget.plugin.image}'),
              ),
              title: Column(
                mainAxisAlignment: MainAxisAlignment.start,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(height: widget.plugin.ratingAvg != null ? 4 : 0),
                  Padding(
                    padding: const EdgeInsets.only(top: 4.0),
                    child: Text(
                      widget.plugin.description,
                      style: const TextStyle(color: Colors.grey, fontSize: 14),
                    ),
                  ),
                  SizedBox(height: widget.plugin.ratingAvg != null ? 4 : 0),
                  widget.plugin.ratingAvg != null
                      ? Row(
                          children: [
                            Text(widget.plugin.ratingAvg!.toString()),
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
                              itemBuilder: (context, _) => const Icon(Icons.star, color: Colors.amber),
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
              trailing: IconButton(
                icon: Icon(
                  widget.plugin.isEnabled ? Icons.check : Icons.arrow_downward_rounded,
                  color: widget.plugin.isEnabled ? Colors.white : Colors.grey,
                ),
                onPressed: () {
                  _togglePlugin(widget.plugin.id.toString(), !widget.plugin.isEnabled);
                },
              ),
            ),
            const SizedBox(height: 16),
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'Prompt',
                style: TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                utf8.decode(widget.plugin.prompt.codeUnits),
                style: const TextStyle(color: Colors.grey, fontSize: 15, height: 1.4),
              ),
            ),
            const SizedBox(height: 32),
            const Padding(
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
                itemBuilder: (context, _) => const Icon(Icons.star, color: Colors.amber),
                maxRating: 5.0,
                onRatingUpdate: (rating) {
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
                  debugPrint('Refreshed plugins list.');
                  // TODO: refresh ratings on plugin, simply (rating count * avg) + new rating / rating count + 1
                  setState(() {});
                },
              ),
            ),
          ],
        ));
  }

  Future<void> _togglePlugin(String pluginId, bool isEnabled) async {
    var prefs = SharedPreferencesUtil();
    setState(() {
      widget.plugin.isEnabled = isEnabled;
    });
    if (isEnabled) {
      prefs.enablePlugin(pluginId);
      MixpanelManager().pluginEnabled(pluginId);
    } else {
      prefs.disablePlugin(pluginId);
      MixpanelManager().pluginDisabled(pluginId);
    }
  }
}

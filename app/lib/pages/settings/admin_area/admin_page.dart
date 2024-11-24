import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/extensions/string.dart';

import 'app_detail_tester.dart';

class AdminPage extends StatefulWidget {
  const AdminPage({super.key});

  @override
  State<AdminPage> createState() => _AdminPageState();
}

class _AdminPageState extends State<AdminPage> {
  bool isLoading = false;
  List<bool> toggleLoading = [];
  List<App> apps = [];

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      setIsLoading(true);
      apps = await getUnapprovedApps();
      toggleLoading = List.generate(apps.length, (index) => false);
      setState(() {});
      setIsLoading(false);
    });
    super.initState();
  }

  void setIsLoading(bool value) {
    if (value == isLoading) return;
    setState(() {
      isLoading = value;
    });
  }

  void setToggleLoading(bool value, int index) {
    if (value == toggleLoading[index]) return;
    setState(() {
      toggleLoading[index] = value;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('Admin Area'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      body: isLoading
          ? const Center(
              child: CircularProgressIndicator(
              color: Colors.white,
            ))
          : ListView.builder(
              itemCount: apps.length,
              itemBuilder: (context, index) {
                final app = apps[index];
                return GestureDetector(
                  onTap: () {
                    routeToPage(context, AppDetailTester(app: app));
                  },
                  child: Container(
                    padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
                    margin: EdgeInsets.only(bottom: 12, top: index == 0 ? 24 : 0),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        CachedNetworkImage(
                          imageUrl: app.getImageUrl(),
                          imageBuilder: (context, imageProvider) => Container(
                            width: 48,
                            height: 48,
                            decoration: BoxDecoration(
                              shape: BoxShape.rectangle,
                              borderRadius: BorderRadius.circular(8),
                              image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                            ),
                          ),
                          placeholder: (context, url) => const SizedBox(
                            width: 48,
                            height: 48,
                            child: CircularProgressIndicator(
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          ),
                          errorWidget: (context, url, error) => const Icon(Icons.error),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.start,
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text(
                                    app.name.decodeString,
                                    maxLines: 1,
                                    style:
                                        const TextStyle(fontWeight: FontWeight.w600, color: Colors.white, fontSize: 16),
                                  ),
                                  app.private
                                      ? const SizedBox(
                                          width: 6,
                                        )
                                      : const SizedBox(),
                                  app.private ? const Icon(Icons.lock, color: Colors.grey, size: 16) : const SizedBox(),
                                  app.status == 'rejected'
                                      ? const SizedBox(
                                          width: 6,
                                        )
                                      : const SizedBox(),
                                  app.status == 'rejected'
                                      ? const Icon(Icons.close, color: Colors.red, size: 16)
                                      : const SizedBox(),
                                ],
                              ),
                              SizedBox(height: app.ratingAvg != null ? 4 : 0),
                              Padding(
                                padding: const EdgeInsets.only(top: 4.0),
                                child: Text(
                                  app.description.decodeString,
                                  maxLines: 2,
                                  style: const TextStyle(color: Colors.grey, fontSize: 14),
                                ),
                              ),
                              Row(
                                children: [
                                  app.ratingAvg != null || app.installs > 0
                                      ? Padding(
                                          padding: const EdgeInsets.only(top: 8),
                                          child: Row(
                                            crossAxisAlignment: CrossAxisAlignment.center,
                                            mainAxisAlignment: MainAxisAlignment.start,
                                            children: [
                                              app.ratingAvg != null
                                                  ? Row(
                                                      crossAxisAlignment: CrossAxisAlignment.center,
                                                      children: [
                                                        Text(app.getRatingAvg()!),
                                                        const SizedBox(width: 4),
                                                        const Icon(Icons.star, color: Colors.deepPurple, size: 16),
                                                        const SizedBox(width: 4),
                                                        Text('(${app.ratingCount})'),
                                                        const SizedBox(width: 16),
                                                      ],
                                                    )
                                                  : const SizedBox(),
                                            ],
                                          ),
                                        )
                                      : Container(),
                                ],
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 16),
                        app.enabled
                            ? Icon(
                                Icons.check,
                                color: app.enabled ? Colors.white : Colors.grey,
                              )
                            : const SizedBox(),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/schema/app.dart';

class AppAnalytics extends StatefulWidget {
  final App app;

  const AppAnalytics({super.key, required this.app});

  @override
  State<AppAnalytics> createState() => _AppAnalyticsState();
}

class _AppAnalyticsState extends State<AppAnalytics> {
  List<AppUsageHistory> data = [];
  int total = 0;
  double money = 0;
  bool loading = true;

  @override
  void initState() {
    retrieveAppUsageHistory(widget.app.id).then((List<AppUsageHistory> history) {
      if (mounted) {
        setState(() {
          data = history;
          total = history.fold(0, (previousValue, element) => previousValue + element.count);
          loading = false;
        });
      }
    });
    getAppMoneyMade(widget.app.id).then((double money) {
      if (mounted) {
        setState(() {
          this.money = money;
        });
      }
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Analytics'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: Center(
        child: loading
            ? const CircularProgressIndicator(
                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
              )
            : Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Text(
                    '$total',
                    style: const TextStyle(color: Colors.white, fontSize: 80),
                  ),
                  const SizedBox(height: 16),
                  const Text('Times Used', style: TextStyle(color: Colors.white, fontSize: 18)),
                  const SizedBox(height: 120),
                  Text(
                    '\$$money',
                    style: const TextStyle(color: Colors.white, fontSize: 64),
                  ),
                  const SizedBox(height: 16),
                  const Text('USD Made! 🤑', style: TextStyle(color: Colors.white, fontSize: 18)),
                  const SizedBox(height: 120),
                ],
              ),
      ),
    );
  }
}

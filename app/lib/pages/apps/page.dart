import 'package:flutter/material.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:friend_private/pages/apps/store/discovery/page.dart';
import 'package:friend_private/pages/apps/store/maps/page.dart';
class AppsPage extends StatelessWidget {
  const AppsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.background,
      body: ErrorHandler(
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: GridView.builder(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 4,
                childAspectRatio: 0.75,
                crossAxisSpacing: 16,
                mainAxisSpacing: 16,
              ),
              itemCount: dummyApps.length,
              itemBuilder: (context, index) {
                return AppIcon(app: dummyApps[index]);
              },
            ),
          ),
        ),
      ),
    );
  }
}

class ErrorHandler extends StatelessWidget {
  final Widget child;

  const ErrorHandler({Key? key, required this.child}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Builder(
      builder: (BuildContext context) {
        try {
          return child;
        } catch (error, stackTrace) {
          Logger.instance.talker.error(
            'Error in AppsPage: $error',
            stackTrace,
          );
          return Center(
            child: Text(
              'An error occurred: $error',
              style: const TextStyle(color: Colors.red),
            ),
          );
        }
      },
    );
  }
}

class AppIcon extends StatelessWidget {
  final AppData app;

  const AppIcon({super.key, required this.app});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () {
        if (app.name == 'Discovery Feed') {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (context) => const DiscoveryPage()),
          );
        } else if (app.name == 'Maps') {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (context) => const MapsPage()),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Launching ${app.name}...')),
          );
        }
      },
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          AspectRatio(
            aspectRatio: 1,
            child: Container(
              decoration: BoxDecoration(
                color: app.color,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Padding(
                padding: const EdgeInsets.all(12.0),
                child: Icon(app.icon, color: Colors.white, size: 36),
              ),
            ),
          ),
          const SizedBox(height: 4),
          Flexible(
            child: Text(
              app.name,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 10, color: Colors.white),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
class AppData {
  final String name;
  final IconData icon;
  final Color color;

  AppData({required this.name, required this.icon, required this.color});
}

final List<AppData> dummyApps = [
  AppData(name: 'Discovery Feed', icon: Icons.compass_calibration, color: Colors.blue),
  AppData(name: 'Maps', icon: Icons.map, color: Colors.green),
];

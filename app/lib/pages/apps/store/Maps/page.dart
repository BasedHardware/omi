import 'package:flutter/material.dart';
import 'package:friend_private/utils/logger.dart';

class MapsPage extends StatelessWidget {
  const MapsPage({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Maps'),
        backgroundColor: Colors.green,
      ),
      body: ErrorHandler(
        child: Stack(
          children: [
            // Simulated map background
            Container(
              color: Colors.grey[300],
              child: GridView.builder(
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 15,
                ),
                itemBuilder: (context, index) {
                  return Container(
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.grey[400]!),
                    ),
                  );
                },
              ),
            ),
            // Simulated map markers
            Center(
              child: Icon(Icons.location_on, color: Colors.red, size: 50),
            ),
            Positioned(
              top: 100,
              left: 100,
              child: Icon(Icons.location_on, color: Colors.blue, size: 30),
            ),
            Positioned(
              bottom: 150,
              right: 120,
              child: Icon(Icons.location_on, color: Colors.green, size: 30),
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: Colors.green,
        foregroundColor: Colors.white,
        onPressed: () {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Centering map...')),
          );
        },
        child: const Icon(Icons.center_focus_strong),
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
            'Error in MapsPage: $error',
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

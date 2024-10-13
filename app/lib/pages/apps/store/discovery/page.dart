import 'package:flutter/material.dart';
import 'package:friend_private/utils/logger.dart';

class DiscoveryPage extends StatelessWidget {
  const DiscoveryPage({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Discovery'),
        backgroundColor: Colors.blue,
      ),
      body: ErrorHandler(
        child: ListView.builder(
          itemCount: 20,
          itemBuilder: (context, index) {
            return DiscoveryItem(index: index);
          },
        ),
      ),
    );
  }
}

class DiscoveryItem extends StatelessWidget {
  final int index;

  const DiscoveryItem({Key? key, required this.index}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
      child: ListTile(
        leading: Icon(Icons.explore, color: Colors.blue),
        title: Text('Discovery Item $index'),
        subtitle: Text('This is a sample discovery item description.'),
        onTap: () {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Tapped on Discovery Item $index')),
          );
        },
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
            'Error in DiscoveryPage: $error',
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


import 'package:flutter/material.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:webview_flutter/webview_flutter.dart';

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
        child: WebViewWidget(
          controller: WebViewController()
            ..setJavaScriptMode(JavaScriptMode.unrestricted)
            ..loadRequest(Uri.parse('https://omi-map-notes.vercel.app/')),
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

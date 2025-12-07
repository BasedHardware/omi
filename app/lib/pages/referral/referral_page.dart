import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class ReferralPage extends StatefulWidget {
  const ReferralPage({super.key});

  @override
  State<ReferralPage> createState() => _ReferralPageState();
}

class _ReferralPageState extends State<ReferralPage> {
  WebViewController? _controller;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();

    MixpanelManager().pageOpened('Referral Program');

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;

      final controller = WebViewController()
        ..setJavaScriptMode(JavaScriptMode.unrestricted)
        ..setNavigationDelegate(
          NavigationDelegate(
            onPageStarted: (String url) {
              if (!mounted) return;
              setState(() => _isLoading = true);
            },
            onPageFinished: (String url) {
              if (!mounted) return;
              setState(() => _isLoading = false);
            },
          ),
        )
        ..loadRequest(Uri.parse('https://affiliate.omi.me/'));

      setState(() {
        _controller = controller;
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.surface,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.surface,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () {
            Navigator.of(context).pop();
          },
        ),
        title: const Text(
          'Referral Program',
          style: TextStyle(
            color: Colors.white,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
        centerTitle: true,
      ),
      body: Stack(
        children: [
          if (_controller != null) WebViewWidget(controller: _controller!),
          if (_isLoading || _controller == null)
            const Center(
              child: CircularProgressIndicator(color: Colors.deepPurple),
            ),
        ],
      ),
    );
  }
}

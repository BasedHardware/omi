<content>
import 'package:flutter/material.dart';
import 'package:omi/env/env.dart';

class DeveloperSettingsScreen extends StatefulWidget {
  const DeveloperSettingsScreen({super.key});

  @override
  State<DeveloperSettingsScreen> createState() => _DeveloperSettingsScreenState();
}

class _DeveloperSettingsScreenState extends State<DeveloperSettingsScreen> {
  final _controller = TextEditingController();
  bool _hasCustomUrl = false;

  @override
  void initState() {
    super.initState();
    _loadCurrentUrl();
  }

  void _loadCurrentUrl() {
    final currentUrl = Env.apiBaseUrl;
    if (currentUrl != 'https://api.omi.me') {
      _controller.text = currentUrl;
      _hasCustomUrl = true;
    }
  }

  Future<void> _saveUrl() async {
    final url = _controller.text.trim();
    if (url.isEmpty) {
      await Env.resetApiBaseUrl();
      setState(() {
        _hasCustomUrl = false;
      });
    } else {
      await Env.overrideApiBaseUrl(url);
      setState(() {
        _hasCustomUrl = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Developer Settings'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'API Configuration',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Text(
              'Override the default backend API URL for self-hosted instances.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _controller,
              decoration: InputDecoration(
                labelText: 'Custom API URL',
                hintText: 'https://your-self-hosted-api.com',
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                  icon: const Icon(Icons.clear),
                  onPressed: () {
                    _controller.clear();
                    _saveUrl();
                  },
                ),
              ),
              onChanged: (value) {
                // Optional: Add validation here
              },
            ),
            const SizedBox(height: 16),
            Text(
              _hasCustomUrl
                  ? 'Using custom API URL: ${Env.apiBaseUrl}'
                  : 'Using default API URL',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _saveUrl,
                child: Text(_hasCustomUrl ? 'Update URL' : 'Set Custom URL'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
</content>
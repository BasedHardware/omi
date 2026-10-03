<content>
import 'package:flutter/material.dart';
import 'package:omi/features/settings/screens/developer_settings_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          _buildSection(
            title: 'General',
            children: [
              _buildTile(
                title: 'Account',
                subtitle: 'Manage your account settings',
                onTap: () {
                  // Navigate to account settings
                },
              ),
              _buildTile(
                title: 'Appearance',
                subtitle: 'Theme and display options',
                onTap: () {
                  // Navigate to appearance settings
                },
              ),
            ],
          ),
          const SizedBox(height: 24),
          _buildSection(
            title: 'Advanced',
            children: [
              _buildTile(
                title: 'Developer Settings',
                subtitle: 'API configuration and debugging options',
                onTap: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (context) => const DeveloperSettingsScreen(),
                    ),
                  );
                },
              ),
              _buildTile(
                title: 'About',
                subtitle: 'App version and information',
                onTap: () {
                  // Navigate to about screen
                },
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSection({required String title, required List<Widget> children}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 8),
        ...children,
      ],
    );
  }

  Widget _buildTile({
    required String title,
    required String subtitle,
    required VoidCallback onTap,
  }) {
    return Card(
      child: ListTile(
        title: Text(title),
        subtitle: Text(subtitle),
        onTap: onTap,
      ),
    );
  }
}
</content>
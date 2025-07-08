import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/http/calendar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:url_launcher/url_launcher.dart';

class CalendarIntegrationPage extends StatefulWidget {
  const CalendarIntegrationPage({Key? key}) : super(key: key);

  @override
  State<CalendarIntegrationPage> createState() => _CalendarIntegrationPageState();
}

class _CalendarIntegrationPageState extends State<CalendarIntegrationPage> {
  bool _isLoading = false;
  bool _isConnected = false;
  String? _calendarName;
  String? _timezone;
  Map<String, dynamic>? _config;
  List<Map<String, dynamic>> _upcomingEvents = [];

  @override
  void initState() {
    super.initState();
    _loadCalendarStatus();
  }

  Future<void> _loadCalendarStatus() async {
    setState(() => _isLoading = true);
    
    try {
      var status = await getCalendarStatus();
      if (status != null) {
        setState(() {
          _isConnected = status['connected'] ?? false;
          _calendarName = status['calendar_name'];
          _timezone = status['timezone'];
        });
        
        if (_isConnected) {
          _loadConfig();
          _loadUpcomingEvents();
        }
      }
    } catch (e) {
      _showErrorDialog('Error loading calendar status: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _loadConfig() async {
    try {
      var config = await getCalendarConfig();
      if (config != null) {
        setState(() => _config = config);
      }
    } catch (e) {
      print('Error loading config: $e');
    }
  }

  Future<void> _loadUpcomingEvents() async {
    try {
      var events = await getUpcomingEvents(daysAhead: 7);
      setState(() => _upcomingEvents = events);
    } catch (e) {
      print('Error loading events: $e');
    }
  }

  Future<void> _connectCalendar() async {
    setState(() => _isLoading = true);
    
    try {
      var authUrl = await initiateGoogleCalendarAuth();
      if (authUrl != null) {
        var uri = Uri.parse(authUrl);
        if (await canLaunchUrl(uri)) {
          await launchUrl(uri, mode: LaunchMode.externalApplication);
          
          // Show dialog to refresh after auth
          _showDialog(
            'Calendar Connection',
            'Please complete the authentication in your browser. Once done, come back and refresh this page.',
            actions: [
              TextButton(
                onPressed: () {
                  Navigator.pop(context);
                  _loadCalendarStatus();
                },
                child: const Text('Refresh'),
              ),
            ],
          );
        }
      }
    } catch (e) {
      _showErrorDialog('Error connecting calendar: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _disconnectCalendar() async {
    bool? confirmed = await _showConfirmDialog(
      'Disconnect Calendar',
      'Are you sure you want to disconnect your Google Calendar? This will stop automatic event creation.',
    );
    
    if (confirmed != true) return;
    
    setState(() => _isLoading = true);
    
    try {
      bool success = await disconnectCalendar();
      if (success) {
        setState(() {
          _isConnected = false;
          _calendarName = null;
          _timezone = null;
          _config = null;
          _upcomingEvents = [];
        });
        _showSuccessDialog('Calendar disconnected successfully');
      } else {
        _showErrorDialog('Error disconnecting calendar');
      }
    } catch (e) {
      _showErrorDialog('Error disconnecting calendar: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _updateConfig(Map<String, dynamic> newConfig) async {
    setState(() => _isLoading = true);
    
    try {
      bool success = await updateCalendarConfig(newConfig);
      if (success) {
        setState(() => _config = newConfig);
        _showSuccessDialog('Configuration updated successfully');
      } else {
        _showErrorDialog('Error updating configuration');
      }
    } catch (e) {
      _showErrorDialog('Error updating configuration: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _testIntegration() async {
    setState(() => _isLoading = true);
    
    try {
      var result = await testCalendarIntegration();
      if (result != null) {
        String message = result['message'] ?? 'Test completed';
        String status = result['status'] ?? 'unknown';
        
        _showDialog(
          'Integration Test',
          'Status: $status\n$message',
        );
      }
    } catch (e) {
      _showErrorDialog('Error testing integration: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  void _showDialog(String title, String content, {List<Widget>? actions}) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(content),
        actions: actions ?? [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  void _showErrorDialog(String message) {
    _showDialog('Error', message);
  }

  void _showSuccessDialog(String message) {
    _showDialog('Success', message);
  }

  Future<bool?> _showConfirmDialog(String title, String content) {
    return showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(content),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Confirm'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
        title: const Text('Google Calendar Integration'),
        foregroundColor: Colors.white,
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildStatusCard(),
                  const SizedBox(height: 16),
                  if (_isConnected) ...[
                    _buildConfigCard(),
                    const SizedBox(height: 16),
                    _buildUpcomingEventsCard(),
                  ],
                ],
              ),
            ),
    );
  }

  Widget _buildStatusCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  _isConnected ? Icons.check_circle : Icons.error,
                  color: _isConnected ? Colors.green : Colors.red,
                ),
                const SizedBox(width: 8),
                Text(
                  _isConnected ? 'Connected' : 'Not Connected',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (_isConnected) ...[
              Text('Calendar: $_calendarName'),
              Text('Timezone: $_timezone'),
              const SizedBox(height: 16),
              Row(
                children: [
                  ElevatedButton(
                    onPressed: _disconnectCalendar,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.red,
                    ),
                    child: const Text('Disconnect'),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton(
                    onPressed: _testIntegration,
                    child: const Text('Test Integration'),
                  ),
                ],
              ),
            ] else ...[
              const Text('Connect your Google Calendar to automatically create events from your conversations.'),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: _connectCalendar,
                child: const Text('Connect Google Calendar'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildConfigCard() {
    if (_config == null) return const SizedBox();
    
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Configuration',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 16),
            SwitchListTile(
              title: const Text('Auto-create events'),
              subtitle: const Text('Automatically create calendar events from conversations'),
              value: _config!['auto_create_events'] ?? true,
              onChanged: (value) {
                var newConfig = Map<String, dynamic>.from(_config!);
                newConfig['auto_create_events'] = value;
                _updateConfig(newConfig);
              },
            ),
            SwitchListTile(
              title: const Text('Include transcript'),
              subtitle: const Text('Include conversation transcript in event description'),
              value: _config!['include_transcript'] ?? true,
              onChanged: (value) {
                var newConfig = Map<String, dynamic>.from(_config!);
                newConfig['include_transcript'] = value;
                _updateConfig(newConfig);
              },
            ),
            SwitchListTile(
              title: const Text('Include summary'),
              subtitle: const Text('Include conversation summary in event description'),
              value: _config!['include_summary'] ?? true,
              onChanged: (value) {
                var newConfig = Map<String, dynamic>.from(_config!);
                newConfig['include_summary'] = value;
                _updateConfig(newConfig);
              },
            ),
            ListTile(
              title: const Text('Default event duration'),
              subtitle: Text('${_config!['event_duration_minutes'] ?? 60} minutes'),
              trailing: const Icon(Icons.edit),
              onTap: () {
                // Show duration picker
                _showDurationPicker();
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUpcomingEventsCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Upcoming Events',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                TextButton(
                  onPressed: _loadUpcomingEvents,
                  child: const Text('Refresh'),
                ),
              ],
            ),
            const SizedBox(height: 16),
            if (_upcomingEvents.isEmpty)
              const Text('No upcoming events')
            else
              ListView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: _upcomingEvents.length,
                itemBuilder: (context, index) {
                  var event = _upcomingEvents[index];
                  return ListTile(
                    title: Text(event['summary'] ?? 'No title'),
                    subtitle: Text(event['start'] ?? ''),
                    trailing: event['location'] != null && event['location'].isNotEmpty
                        ? Icon(Icons.location_on)
                        : null,
                  );
                },
              ),
          ],
        ),
      ),
    );
  }

  void _showDurationPicker() {
    int currentDuration = _config!['event_duration_minutes'] ?? 60;
    
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Event Duration'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Select default duration for calendar events:'),
            const SizedBox(height: 16),
            DropdownButton<int>(
              value: currentDuration,
              items: [15, 30, 45, 60, 90, 120].map((duration) {
                return DropdownMenuItem(
                  value: duration,
                  child: Text('$duration minutes'),
                );
              }).toList(),
              onChanged: (value) {
                if (value != null) {
                  var newConfig = Map<String, dynamic>.from(_config!);
                  newConfig['event_duration_minutes'] = value;
                  _updateConfig(newConfig);
                  Navigator.pop(context);
                }
              },
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
        ],
      ),
    );
  }
}
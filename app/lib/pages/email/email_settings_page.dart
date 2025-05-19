import 'package:flutter/material.dart';
import 'package:omi/services/email/email_service.dart';

class EmailSettingsPage extends StatefulWidget {
  const EmailSettingsPage({Key? key}) : super(key: key);

  @override
  State<EmailSettingsPage> createState() => _EmailSettingsPageState();
}

class _EmailSettingsPageState extends State<EmailSettingsPage> {
  final _formKey = GlobalKey<FormState>();
  
  final _smtpController = TextEditingController(text: 'smtp.gmail.com');
  final _portController = TextEditingController(text: '587');
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _ssl = true;
  
  // Test email fields
  final _toController = TextEditingController();
  final _subjectController = TextEditingController();
  final _bodyController = TextEditingController();
  
  bool _isSending = false;
  String? _resultMessage;
  bool _success = false;
  
  @override
  void initState() {
    super.initState();
    // Load configuration if available
    _loadConfiguration();
  }
  
  void _loadConfiguration() {
    // This would load from storage in a full implementation
  }
  
  Future<void> _saveConfiguration() async {
    if (_formKey.currentState!.validate()) {
      try {
        await EmailService.instance.saveConfiguration(
          smtpServer: _smtpController.text,
          port: int.parse(_portController.text),
          username: _usernameController.text,
          password: _passwordController.text,
          ssl: _ssl,
        );
        
        setState(() {
          _resultMessage = 'Configuration saved successfully';
          _success = true;
        });
      } catch (e) {
        setState(() {
          _resultMessage = 'Failed to save configuration: $e';
          _success = false;
        });
      }
    }
  }
  
  Future<void> _sendTestEmail() async {
    if (_toController.text.isEmpty || _subjectController.text.isEmpty || _bodyController.text.isEmpty) {
      setState(() {
        _resultMessage = 'Please fill all test email fields';
        _success = false;
      });
      return;
    }
    
    setState(() {
      _isSending = true;
      _resultMessage = null;
    });
    
    try {
      final result = await EmailService.instance.sendEmail(
        to: _toController.text,
        subject: _subjectController.text,
        body: _bodyController.text,
      );
      
      setState(() {
        _isSending = false;
        _resultMessage = result.message;
        _success = result.success;
      });
    } catch (e) {
      setState(() {
        _isSending = false;
        _resultMessage = 'Error: $e';
        _success = false;
      });
    }
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Email Settings'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // SMTP Configuration Form
            Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'SMTP Configuration',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _smtpController,
                    decoration: const InputDecoration(
                      labelText: 'SMTP Server',
                      hintText: 'e.g., smtp.gmail.com',
                      border: OutlineInputBorder(),
                    ),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter SMTP server';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _portController,
                    decoration: const InputDecoration(
                      labelText: 'Port',
                      hintText: 'e.g., 587',
                      border: OutlineInputBorder(),
                    ),
                    keyboardType: TextInputType.number,
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter port';
                      }
                      if (int.tryParse(value) == null) {
                        return 'Please enter a valid port number';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _usernameController,
                    decoration: const InputDecoration(
                      labelText: 'Email/Username',
                      hintText: 'your.email@example.com',
                      border: OutlineInputBorder(),
                    ),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter email/username';
                      }
                      if (!EmailService.isValidEmail(value)) {
                        return 'Please enter a valid email';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _passwordController,
                    decoration: const InputDecoration(
                      labelText: 'Password/App Password',
                      hintText: 'Your email password or app-specific password',
                      border: OutlineInputBorder(),
                    ),
                    obscureText: true,
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter password';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  SwitchListTile(
                    title: const Text('Use SSL'),
                    value: _ssl,
                    onChanged: (value) {
                      setState(() {
                        _ssl = value;
                      });
                    },
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: _saveConfiguration,
                      child: const Text('Save Configuration'),
                    ),
                  ),
                ],
              ),
            ),
            
            const SizedBox(height: 32),
            
            // Test Email Section
            const Text(
              'Send Test Email',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _toController,
              decoration: const InputDecoration(
                labelText: 'To',
                hintText: 'recipient@example.com',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _subjectController,
              decoration: const InputDecoration(
                labelText: 'Subject',
                hintText: 'Test Email from Omi App',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _bodyController,
              decoration: const InputDecoration(
                labelText: 'Body',
                hintText: 'This is a test email from the Omi app.',
                border: OutlineInputBorder(),
              ),
              maxLines: 4,
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _isSending ? null : _sendTestEmail,
                child: _isSending
                    ? const CircularProgressIndicator()
                    : const Text('Send Test Email'),
              ),
            ),
            
            // Result Message
            if (_resultMessage != null) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(12),
                color: _success ? Colors.green.shade900 : Colors.red.shade900,
                child: Text(
                  _resultMessage!,
                  style: const TextStyle(color: Colors.white),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
  
  @override
  void dispose() {
    _smtpController.dispose();
    _portController.dispose();
    _usernameController.dispose();
    _passwordController.dispose();
    _toController.dispose();
    _subjectController.dispose();
    _bodyController.dispose();
    super.dispose();
  }
}
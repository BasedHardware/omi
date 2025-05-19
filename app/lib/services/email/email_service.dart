import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:mailer/mailer.dart';
import 'package:mailer/smtp_server.dart';
import 'package:email_validator/email_validator.dart';

// Result class for email operations
class EmailResult {
  final bool success;
  final String message;
  final dynamic error;

  EmailResult({
    required this.success,
    required this.message,
    this.error,
  });
}

// Template class for emails
class EmailTemplate {
  final String name;
  final String subject;
  final String body;
  final bool isHtml;

  EmailTemplate({
    required this.name,
    required this.subject,
    required this.body,
    this.isHtml = false,
  });

  // Apply variables to template
  Map<String, String> applyVariables(Map<String, String> variables) {
    String processedSubject = subject;
    String processedBody = body;

    variables.forEach((key, value) {
      final placeholder = '{{$key}}';
      processedSubject = processedSubject.replaceAll(placeholder, value);
      processedBody = processedBody.replaceAll(placeholder, value);
    });

    return {
      'subject': processedSubject,
      'body': processedBody,
    };
  }
}

// Email service class
class EmailService {
  static final EmailService _instance = EmailService._internal();

  factory EmailService() => _instance;

  EmailService._internal();

  static EmailService get instance => _instance;

  // Configuration
  String? _smtpServer;
  int? _port;
  String? _username;
  String? _password;
  bool _ssl = true;
  String? _defaultSender;

  // Templates
  final Map<String, EmailTemplate> _templates = {};
  
  // Result stream for listeners
  final StreamController<EmailResult> _resultStreamController = 
      StreamController<EmailResult>.broadcast();

  Stream<EmailResult> get resultStream => _resultStreamController.stream;

  // Initialize with configuration
  void initialize({
    String smtpServer = 'smtp.gmail.com',
    int port = 587,
    String? username,
    String? password,
    bool ssl = true,
    String? defaultSender,
  }) {
    _smtpServer = smtpServer;
    _port = port;
    _username = username;
    _password = password;
    _ssl = ssl;
    _defaultSender = defaultSender ?? username;
    debugPrint('EmailService initialized');
  }

  // Save configuration (could persist to secure storage in a real implementation)
  Future<void> saveConfiguration({
    required String smtpServer,
    required int port,
    required String username,
    required String password,
    required bool ssl,
    String? defaultSender,
  }) async {
    _smtpServer = smtpServer;
    _port = port;
    _username = username;
    _password = password;
    _ssl = ssl;
    _defaultSender = defaultSender ?? username;
    debugPrint('EmailService configuration saved');
  }

  // Get SMTP server based on configuration
  SmtpServer? _getSmtpServer() {
    if (_smtpServer == null || _username == null || _password == null) {
      return null;
    }

    if (_smtpServer!.contains('gmail.com')) {
      return gmail(_username!, _password!);
    } else if (_smtpServer!.contains('outlook.com') || 
              _smtpServer!.contains('hotmail.com')) {
      return hotmail(_username!, _password!);
    } else if (_smtpServer!.contains('yahoo.com')) {
      return yahoo(_username!, _password!);
    } else {
      return SmtpServer(
        _smtpServer!,
        port: _port!,
        ssl: _ssl,
        username: _username!,
        password: _password!,
      );
    }
  }

  // Add an email template
  void addTemplate(EmailTemplate template) {
    _templates[template.name] = template;
    debugPrint('Template "${template.name}" added');
  }

  // Get a template by name
  EmailTemplate? getTemplate(String name) {
    return _templates[name];
  }

  // Send an email
  Future<EmailResult> sendEmail({
    required String to,
    required String subject,
    required String body,
    List<String> cc = const [],
    List<String> bcc = const [],
    List<String> attachmentPaths = const [],
    bool isHtml = false,
    String? from,
  }) async {
    // Check if service is configured
    if (_username == null || _password == null || _smtpServer == null) {
      return EmailResult(
        success: false,
        message: 'Email service not configured properly',
      );
    }

    // Validate email addresses
    if (!isValidEmail(to)) {
      return EmailResult(
        success: false,
        message: 'Invalid recipient email address: $to',
      );
    }

    try {
      final message = Message()
        ..from = Address(from ?? _username!, from ?? _defaultSender ?? _username!)
        ..recipients.add(to)
        ..subject = subject;

      if (cc.isNotEmpty) {
        message.ccRecipients.addAll(cc);
      }

      if (bcc.isNotEmpty) {
        message.bccRecipients.addAll(bcc);
      }

      if (isHtml) {
        message.html = body;
      } else {
        message.text = body;
      }

      // Add attachments if any
      if (attachmentPaths.isNotEmpty) {
        for (final path in attachmentPaths) {
          if (kIsWeb) {
            // Web doesn't support File attachments
            continue;
          }
          final attachment = FileAttachment(File(path));
          message.attachments.add(attachment);
        }
      }

      final smtpServer = _getSmtpServer();
      if (smtpServer == null) {
        return EmailResult(
          success: false,
          message: 'SMTP server configuration error',
        );
      }

      final sendReport = await send(message, smtpServer);

      final result = EmailResult(
        success: true,
        message: 'Email sent successfully: ${sendReport.toString()}',
      );
      _resultStreamController.add(result);
      return result;
    } catch (e) {
      final result = EmailResult(
        success: false,
        message: 'Failed to send email: ${e.toString()}',
        error: e,
      );
      _resultStreamController.add(result);
      return result;
    }
  }

  // Send an email using a template
  Future<EmailResult> sendTemplatedEmail({
    required String to,
    required String templateName,
    required Map<String, String> variables,
    List<String> cc = const [],
    List<String> bcc = const [],
    List<String> attachmentPaths = const [],
    String? from,
  }) async {
    final template = getTemplate(templateName);
    if (template == null) {
      return EmailResult(
        success: false,
        message: 'Template not found: $templateName',
      );
    }

    final processed = template.applyVariables(variables);

    return sendEmail(
      to: to,
      subject: processed['subject']!,
      body: processed['body']!,
      cc: cc,
      bcc: bcc,
      attachmentPaths: attachmentPaths,
      isHtml: template.isHtml,
      from: from,
    );
  }

  // Validate an email address
  static bool isValidEmail(String email) {
    return EmailValidator.validate(email);
  }

  // Dispose
  void dispose() {
    _resultStreamController.close();
  }
}
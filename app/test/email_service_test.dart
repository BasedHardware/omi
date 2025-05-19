import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/email/email_service.dart';

void main() {
  group('EmailService Tests', () {
    test('Email validation test', () {
      // Valid emails
      expect(EmailService.isValidEmail('test@example.com'), true);
      expect(EmailService.isValidEmail('user.name+tag@gmail.com'), true);
      expect(EmailService.isValidEmail('user-name@domain.co.uk'), true);
      
      // Invalid emails
      expect(EmailService.isValidEmail('invalid-email'), false);
      expect(EmailService.isValidEmail('missing@domain'), false);
      expect(EmailService.isValidEmail('@domain.com'), false);
    });
    
    test('Email templates test', () {
      final emailService = EmailService.instance;
      
      // Add a template
      final template = EmailTemplate(
        name: 'welcome',
        subject: 'Welcome {{name}}!',
        body: 'Hello {{name}}, welcome to our service! Your ID is {{userId}}.',
        isHtml: false,
      );
      
      emailService.addTemplate(template);
      
      // Get template
      final retrievedTemplate = emailService.getTemplate('welcome');
      expect(retrievedTemplate, isNotNull);
      expect(retrievedTemplate?.name, 'welcome');
      
      // Apply variables
      final variables = {
        'name': 'John Doe',
        'userId': '12345',
      };
      
      final processed = retrievedTemplate!.applyVariables(variables);
      expect(processed['subject'], 'Welcome John Doe!');
      expect(processed['body'], 'Hello John Doe, welcome to our service! Your ID is 12345.');
    });
  });
}
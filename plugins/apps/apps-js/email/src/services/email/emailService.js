const EmailGenerator = require('./emailGenerator');

/**
 * EmailService - A comprehensive service for email operations
 * with improved reliability, template handling, and error management
 */
class EmailService {
  constructor(options = {}) {
    this.generator = new EmailGenerator(options.apiKey, {
      model: options.model,
      maxTokens: options.maxTokens,
      temperature: options.temperature,
      timeout: options.timeout,
      retries: options.retries
    });
    
    // Templates configuration
    this.templates = {
      formal: {
        greeting: 'Dear {recipient_name},',
        farewell: 'Sincerely,',
        style: 'formal'
      },
      professional: {
        greeting: 'Hello {recipient_name},',
        farewell: 'Best regards,',
        style: 'professional'
      },
      friendly: {
        greeting: 'Hi {recipient_name},',
        farewell: 'Cheers,',
        style: 'friendly'
      },
      brief: {
        greeting: 'Hi {recipient_name},',
        farewell: 'Regards,',
        style: 'brief'
      }
    };
    
    // Performance metrics
    this.metrics = {
      totalEmails: 0,
      successful: 0,
      failed: 0,
      avgGenerationTime: 0
    };
  }

  /**
   * Draft email with improved formatting and content
   * @param {string} recipientEmail - Recipient email address
   * @param {string} subject - Email subject
   * @param {string} content - Email content (can be raw or pre-generated)
   * @param {Object} user - User information
   * @param {Object} options - Additional options
   * @returns {Promise<Object>} - Email draft details
   */
  async draftEmail(recipientEmail, subject, content, user, options = {}) {
    const startTime = Date.now();
    
    try {
      const { template = null, format = 'text' } = options;
      
      // Parse recipient name from email if not provided
      const recipientName = options.recipientName || this._extractNameFromEmail(recipientEmail);
      
      // Choose appropriate template based on specified tone
      const selectedTemplate = template ? 
        this.templates[template] || this.templates.professional : 
        this.templates.professional;
        
      // Format the content with the selected template
      const formattedContent = this._formatEmailWithTemplate(
        content,
        recipientName,
        user.name || user.email.split('@')[0],
        selectedTemplate
      );
      
      // Track metrics
      this.metrics.totalEmails++;
      this.metrics.successful++;
      const generationTime = Date.now() - startTime;
      this.metrics.avgGenerationTime = 
        (this.metrics.avgGenerationTime * (this.metrics.totalEmails - 1) + generationTime) / 
        this.metrics.totalEmails;
      
      return {
        to: recipientEmail,
        subject,
        body: formattedContent,
        from: user.email,
        fromName: user.name || user.email.split('@')[0],
        format,
        status: 'drafted'
      };
    } catch (error) {
      console.error('Error drafting email:', error);
      this.metrics.failed++;
      throw error;
    }
  }

  /**
   * Generate and draft an email in a single operation
   * @param {Object} params - Parameters for email generation and drafting
   * @returns {Promise<Object>} - Email draft result
   */
  async generateAndDraftEmail(params) {
    const {
      recipient,
      user,
      userRequest,
      subject = null,
      content = null,
      tone = 'professional'
    } = params;
    
    try {
      // If subject not provided, generate one
      let emailSubject = subject;
      if (!emailSubject) {
        emailSubject = await this.generator.generateEmailSubject({
          sender: {
            name: user.name,
            email: user.email
          },
          recipient: {
            name: recipient.name,
            email: recipient.email
          },
          userRequest
        });
      }
      
      // If content not provided, generate it
      let emailContent = content;
      if (!emailContent) {
        emailContent = await this.generator.generateEmailContent({
          sender: {
            name: user.name,
            email: user.email
          },
          recipient: {
            name: recipient.name,
            email: recipient.email,
            company: recipient.company || recipient.email.split('@')[1]
          },
          subject: emailSubject,
          tone,
          userRequest,
          purpose: params.purpose || 'communication'
        });
      }
      
      // Draft the email with the generated content
      return this.draftEmail(
        recipient.email,
        emailSubject,
        emailContent,
        user,
        {
          recipientName: recipient.name,
          template: this._determineTemplateFromTone(tone),
          format: params.format || 'text'
        }
      );
    } catch (error) {
      console.error('Error generating and drafting email:', error);
      throw error;
    }
  }

  /**
   * Analyze user's email request and find matching recipient
   * @param {string} text - User's request text
   * @param {Object} user - User information
   * @param {Function} getContactsFunction - Function to retrieve user's contacts
   * @returns {Promise<Object>} - Analysis result with recipient matches
   */
  async analyzeAndFindRecipient(text, user, getContactsFunction) {
    try {
      // First analyze the email request text
      const analysis = await this.generator.analyzeEmailIntent(text);
      
      // Get user's contacts
      const contacts = await getContactsFunction(user);
      
      // Extract specific recipient name from text
      const directRecipient = this.generator._extractNameFromText(text);
      const specificName = directRecipient !== 'unknown recipient' ? directRecipient : null;
      
      // Format contacts list for recipient matching
      const contactsList = contacts.map((c, i) => {
        const contactObj = typeof c === 'string' ? { email: c } : c;
        const name = contactObj.name || contactObj.email.split('@')[0].replace(/[._-]/g, ' ');
        const company = contactObj.email.split('@')[1]?.split('.')[0] || '';
        return `${i+1}. ${name} <${contactObj.email}>${company ? ` (${company})` : ''}`;
      }).join('\n');
      
      // Find best matching recipient
      const recipientName = specificName || analysis.recipient;
      const recipientMatch = await this.generator.findBestContact(recipientName, contactsList);
      
      return {
        analysis,
        specificName,
        recipientMatch,
        contactsList,
        allContacts: contacts
      };
    } catch (error) {
      console.error('Error analyzing and finding recipient:', error);
      throw error;
    }
  }

  // PRIVATE METHODS

  /**
   * Format email with template
   * @private
   */
  _formatEmailWithTemplate(content, recipientName, senderName, template) {
    // Initialize parts array
    const emailParts = [];
    
    // Add greeting if needed
    const hasGreeting = /^(Dear|Hello|Hi|Hey|Greetings)/i.test(content.trim().split('\n')[0]);
    if (!hasGreeting) {
      emailParts.push(template.greeting.replace('{recipient_name}', recipientName));
    }
    
    // Process body content
    let body = content.trim();
    if (hasGreeting) {
      const lines = body.split('\n');
      body = lines.slice(1).join('\n').trim();
    }
    
    // Remove any existing sign-off from body
    body = body.replace(/[\n\s]*(Regards|Sincerely|Cheers|Thanks|Thank you|Best|Warm regards|Yours truly),[\n\s]*\w+[\n\s]*$/i, '');
    
    // First, identify paragraphs by double line breaks or significant indentation
    const rawParagraphs = body.split(/\n{2,}|\n\s{2,}/);
    
    // Process each paragraph
    const paragraphs = rawParagraphs.map(para => {
      // Replace all single line breaks and multiple spaces with a single space
      return para
        .split(/\n/)
        .map(line => line.trim())
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim();
    }).filter(para => para.length > 0);
    
    // Add processed paragraphs to email parts
    emailParts.push(...paragraphs);
    
    // Handle sign-off
    const hasSignOff = /(Regards|Sincerely|Cheers|Thanks|Thank you|Best|Warm regards|Yours truly),?\s*\w+\s*$/i.test(content);
    if (!hasSignOff) {
      // Add farewell and sender name with proper spacing
      emailParts.push(template.farewell);
      emailParts.push(senderName);
    }
    
    // Join all parts with proper spacing
    const formattedEmail = emailParts
      .filter(part => part && part.trim().length > 0)
      .join('\n\n')
      .trim();
    
    // Ensure proper line endings
    return formattedEmail.replace(/\r\n/g, '\n');
  }

  /**
   * Extract name from email address
   * @private
   */
  _extractNameFromEmail(email) {
    if (!email) return 'there';
    
    // Get local part of the email
    const localPart = email.split('@')[0];
    
    // Format local part into a name
    return localPart
      .replace(/[._-]/g, ' ')
      .split(' ')
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  }

  /**
   * Determine appropriate template based on tone
   * @private
   */
  _determineTemplateFromTone(tone) {
    if (!tone) return 'professional';
    
    const lowercaseTone = tone.toLowerCase();
    
    if (lowercaseTone.includes('formal') || lowercaseTone.includes('business')) {
      return 'formal';
    } else if (lowercaseTone.includes('friendly') || lowercaseTone.includes('casual')) {
      return 'friendly';
    } else if (lowercaseTone.includes('professional')) {
      return 'professional';
    } else if (lowercaseTone.includes('brief') || lowercaseTone.includes('short')) {
      return 'brief';
    }
    
    return 'professional';
  }
}

module.exports = EmailService; 
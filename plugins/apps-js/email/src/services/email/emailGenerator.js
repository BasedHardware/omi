const OpenAI = require('openai');

/**
 * EmailGenerator - A service to generate professional, well-formatted emails
 * with improved prompt engineering and error handling
 */
class EmailGenerator {
  constructor(apiKey, options = {}) {
    this.openaiClient = new OpenAI({
      apiKey: apiKey || process.env.OPENAI_API_KEY
    });
    
    this.defaultOptions = {
      model: options.model || 'command',
      maxTokens: options.maxTokens || 500,
      temperature: options.temperature || 0.7,
      timeout: options.timeout || 5000,
      retries: options.retries || 3,
      retryDelay: options.retryDelay || 1000
    };
    
    // Template cache for performance optimization
    this.templateCache = new Map();
  }

  /**
   * Generate email content with advanced prompt engineering
   * @param {Object} params - Parameters for email generation
   * @returns {Promise<string>} - Generated email content
   */
  async generateEmailContent(params) {
    const {
      sender = {},
      recipient = {},
      subject = '',
      tone = 'professional',
      userRequest = '',
      purpose = ''
    } = params;

    const prompt = this._createEmailPrompt(sender, recipient, subject, tone, userRequest, purpose);
    
    try {
      return await this._generateWithRetry(prompt);
    } catch (error) {
      console.error('Error generating email content:', error);
      // Return fallback template if generation fails
      return this._getFallbackTemplate(sender, recipient, subject);
    }
  }

  /**
   * Generate email subject based on context
   * @param {Object} params - Parameters for subject generation
   * @returns {Promise<string>} - Generated subject line
   */
  async generateEmailSubject(params) {
    const {
      sender = {},
      recipient = {},
      userRequest = ''
    } = params;

    const prompt = `Generate a concise, professional email subject line based on the following information:

USER WANTED TO EMAIL: "${recipient.name || 'someone'}"
ACTUAL RECIPIENT: ${recipient.name || recipient.email?.split('@')[0] || 'Recipient'} <${recipient.email || 'recipient@example.com'}>
SENDER: ${sender.name || sender.email || 'User'}
ORIGINAL REQUEST: "${userRequest}"
CONTEXT: This appears to be a business communication.

The subject line should be:
1. Clear and specific - directly related to the content in the ORIGINAL REQUEST
2. Professional in tone
3. Between 3-8 words in length
4. Not contain any formatting or punctuation at the end

Return ONLY the subject line text without quotes or prefixes.`;

    try {
      const response = await this.openaiClient.chat.completions.create({
        model: this.defaultOptions.model,
        messages: [{role: "user", content: prompt}],
        max_tokens: 50,
        temperature: 0.4
      });
      
      return response.choices[0].message.content.trim();
    } catch (error) {
      console.error('Error generating email subject:', error);
      // Extract potential subject from original text or return default
      return this._extractSubjectFromText(userRequest) || 'Message from OmiSend';
    }
  }

  /**
   * Analyze email intent and extract structured data
   * @param {string} text - User's request text
   * @returns {Promise<Object>} - Structured data about the email request
   */
  async analyzeEmailIntent(text) {
    try {
      const prompt = `Analyze the following text to extract information for sending an email:

Text: "${text}"

This text is from a voice command where the user is asking to send an email. The input might be fragmented or incomplete.

Extract the following information, even if some details seem missing:
1. Who is the recipient of the email (just the name)
2. What is the subject or topic of the email
3. What is the content or body of the email
4. What is the purpose of the email (e.g., follow-up, request, information sharing, introduction)
5. What tone should be used (e.g., formal, friendly, professional, casual, brief)
6. Should the email be formatted as HTML or plain text

Provide your BEST GUESS on missing information, especially the recipient name.
If you're highly uncertain about the recipient, extract any name-like words or phrases that could be a person's name.

Format the response as a valid JSON object with these properties:
- recipient: The name of the recipient (string)
- subject: The subject of the email (string)
- content: The body content of the email (string)
- purpose: The purpose of the email (string)
- tone: The tone to use (string)
- format: "html" or "text" (string)

Make sure the JSON is valid and does not include any backticks or markdown formatting.`;

      const response = await this.openaiClient.chat.completions.create({
        model: this.defaultOptions.model,
        messages: [{role: "user", content: prompt}],
        max_tokens: 500,
        temperature: 0.3,
        // OpenAI doesn't have a direct 'format: json' in the same way Cohere does.
        // We will rely on prompt engineering for JSON output and parse it.
        // seed: 456 // Seed may not be available or work the same way
      });

      // Clean and parse JSON response
      return this._parseAnalysisResponse(response.choices[0].message.content.trim());
    } catch (error) {
      console.error('Error analyzing email with OpenAI:', error);
      
      // Fallback to basic extraction
      const extractedName = this._extractNameFromText(text);
      return {
        recipient: extractedName,
        subject: 'Message from OmiSend',
        content: '',
        purpose: 'communication',
        tone: 'professional',
        format: 'text'
      };
    }
  }

  /**
   * Find the best matching contact based on recipient hint
   * @param {string} recipientHint - Recipient name hint
   * @param {string} contactsList - Formatted list of contacts
   * @returns {Promise<Object>} - Best matching contact info
   */
  async findBestContact(recipientHint, contactsList) {
    try {
      const prompt = `I have a list of email contacts and need to find the best match for a recipient specified in a user's message.

USER'S SPECIFIED RECIPIENT: "${recipientHint}"

AVAILABLE CONTACTS:
${contactsList}

Task: Analyze the user's specified recipient and determine which contact from the list is the most likely match.
Consider the following factors:
- Name similarity (including nicknames, short forms, and spelling variations)
- Company/domain relevance
- Role/department context if provided
- Common aliases or abbreviations
- Phonetic similarities

You should:
1. Look for exact matches first, then partial matches
2. Consider contextual clues (like department, role, company mentions)
3. Consider name variations (e.g., "Bob" for "Robert", "Mike" for "Michael")
4. If the recipient hint is vague or unclear, select "no match" rather than guessing

Return the EXACT email address from the list that's the best match, or "no match" if there is no good match.
Be CONSERVATIVE in your matching - if you're not at least 70% confident, respond with "no match".

Format your answer as JSON with:
{
  "email": "recipient@example.com",
  "name": "Recipient Name",
  "confidence": 0.8,
  "reasoning": "Brief explanation of why this contact was chosen",
  "alternatives": ["alternative1@example.com", "alternative2@example.com"]
}

If no good match is found, return:
{
  "email": "no match",
  "name": "",
  "confidence": 0,
  "reasoning": "Explanation why no match was found",
  "alternatives": []
}`;

      // Implement timeout for OpenAI API calls
      const responsePromise = this.openaiClient.chat.completions.create({
        model: this.defaultOptions.model,
        messages: [{role: "user", content: prompt}],
        max_tokens: 500,
        temperature: 0.2,
        // seed: 123
      });

      const response = await Promise.race([
        responsePromise,
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('OpenAI API timeout')), this.defaultOptions.timeout)
        )
      ]);

      // Clean and parse JSON response
      return this._parseContactMatchResponse(response.choices[0].message.content.trim(), recipientHint);
    } catch (error) {
      console.error('Error finding best contact match with OpenAI:', error);
      return null;
    }
  }

  // PRIVATE METHODS

  /**
   * Create optimized prompt for email generation
   * @private
   */
  _createEmailPrompt(sender, recipient, subject, tone, userRequest, purpose) {
    // Improved prompt with clear structure and instructions
    return `You are a professional email assistant. Generate a well-structured, concise business email from ${sender.name || sender.email || 'User'} to ${recipient.name || 'Recipient'}.

Subject: ${subject}

INSTRUCTIONS:
- Write a concise professional email in 3-5 sentences
- Use a ${tone || 'professional and friendly'} tone
- Include a clear call to action if appropriate
- Structure must include greeting, body, and ONE signature line only
- NEVER include multiple sign-offs or duplicate signatures
- DO NOT repeat the sender's name or email twice
- The email should focus on: ${purpose || 'the subject matter'}

RECIPIENT INFORMATION:
- Name: ${recipient.name || recipient.email?.split('@')[0] || 'Recipient'}
- Email: ${recipient.email || 'recipient@example.com'}
- Company: ${recipient.company || recipient.email?.split('@')[1] || 'Company'}
${recipient.position ? `- Position: ${recipient.position}` : ''}

CONTEXT:
- Topic: ${subject || 'a business matter'}
- Purpose: ${purpose || 'To communicate effectively'}
- User request: "${userRequest}"

FORMAT:
- Start with appropriate greeting
- Write 3-5 clear, concise sentences in the body
- End with a single sign-off and name only
- Example format:
  "Hi [Name],
  
  [Body text here]
  
  Best regards,
  ${sender.name || sender.email?.split('@')[0] || 'User'}"
`;
  }

  /**
   * Generate with retry logic for reliability
   * @private
   */
  async _generateWithRetry(prompt) {
    let lastError;
    
    for (let attempt = 0; attempt < this.defaultOptions.retries; attempt++) {
      try {
        const response = await this.openaiClient.chat.completions.create({
          model: this.defaultOptions.model,
          messages: [{role: "user", content: prompt}],
          max_tokens: this.defaultOptions.maxTokens,
          temperature: this.defaultOptions.temperature,
          stop: ["RECIPIENT INFORMATION:", "CONTEXT:", "FORMAT:"] // Adjusted for OpenAI
        });
        
        return response.choices[0].message.content.trim();
      } catch (error) {
        console.error(`Generation attempt ${attempt + 1} failed:`, error);
        lastError = error;
        
        // Wait before retry with exponential backoff
        const delay = this.defaultOptions.retryDelay * Math.pow(2, attempt);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
    
    throw lastError;
  }

  /**
   * Get a fallback template if generation fails
   * @private
   */
  _getFallbackTemplate(sender, recipient, subject) {
    return `Hi ${recipient.name || recipient.email?.split('@')[0] || 'there'},

I'm reaching out regarding ${subject || 'our recent discussion'}. I wanted to follow up on this matter.

Could we discuss this further at your convenience?

Best regards,
${sender.name || sender.email?.split('@')[0] || 'User'}`;
  }

  /**
   * Extract a potential subject from the original text
   * @private
   */
  _extractSubjectFromText(text) {
    const subjectMatches = text.match(/(?:about|regarding|on|for)\s+([^.?!]+)/i);
    if (subjectMatches && subjectMatches[1] && subjectMatches[1].length > 3) {
      return subjectMatches[1].trim();
    }
    return null;
  }

  /**
   * Extract name from text using regex patterns
   * @private
   */
  _extractNameFromText(text) {
    // Try various patterns to extract a name
    const patterns = [
      /(?:to|for)\s+([A-Za-z\s]{2,20})(?:\s|$)/i,           // "to John Smith"
      /(?:email|mail|send|write)\s+([A-Za-z\s]{2,20})(?:\s|$)/i, // "email John Smith"
      /(?:tell|ask|contact)\s+([A-Za-z\s]{2,20})(?:\s|$)/i, // "tell John Smith"
      /([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})/                // Capitalized words (likely names)
    ];
    
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match && match[1] && match[1].length > 1) {
        return match[1].trim();
      }
    }
    
    // Default fallback - look for words that might be names (capitalized)
    const words = text.split(/\s+/);
    for (const word of words) {
      if (word.length > 1 && /^[A-Z][a-z]+$/.test(word)) {
        return word;
      }
    }
    
    return 'unknown recipient';
  }

  /**
   * Parse and clean the analysis response
   * @private
   */
  _parseAnalysisResponse(responseText) {
    try {
      // First attempt: try to extract JSON using regex for a more reliable extraction
      const jsonRegex = /\{[\s\S]*\}/;
      const jsonMatch = responseText.match(jsonRegex);
      
      if (jsonMatch) {
        // More thorough cleaning of JSON text
        const jsonText = jsonMatch[0]
          .trim()
          // Remove all control characters (including those in string literals)
          .replace(/[\u0000-\u001F\u007F-\u009F]/g, '')
          // Fix common JSON formatting issues
          .replace(/\\r\\n|\\n|\\r/g, ' ')
          .replace(/\\"/g, '"')
          .replace(/"{2,}/g, '"')
          .replace(/"{1}([^"]*),([^"]*)"{1}/g, '"$1,$2"');
          
        try {
          // Try parsing with the cleaned text
          const result = JSON.parse(jsonText);
          console.log('Successfully parsed cleaned OpenAI response');
          return result;
        } catch (parseError) {
          console.error('JSON parsing still failed after cleaning:', parseError);
          
          // For really problematic JSON, use regex extraction directly
          const extractField = (text, field) => {
            const regex = new RegExp(`["']${field}["']\\s*:\\s*["']([^"']*)["']`, 'i');
            const match = text.match(regex);
            return match ? match[1] : null;
          };
          
          const recipient = extractField(jsonText, 'recipient') || this._extractNameFromText(responseText);
          const subject = extractField(jsonText, 'subject') || 'Message from OmiSend';
          const content = extractField(jsonText, 'content') || '';
          const purpose = extractField(jsonText, 'purpose') || 'communication';
          const tone = extractField(jsonText, 'tone') || 'professional';
          const format = extractField(jsonText, 'format') || 'text';
          
          console.log('Extracted fields manually after JSON parse failure:', { recipient, subject });
          
          return { recipient, subject, content, purpose, tone, format };
        }
      } else {
        // Fallback - no JSON found
        return {
          recipient: this._extractNameFromText(responseText),
          subject: 'Message from OmiSend',
          content: '',
          purpose: 'communication',
          tone: 'professional',
          format: 'text'
        };
      }
    } catch (error) {
      console.error('Error processing OpenAI response:', error);
      
      // Fallback approach: Basic extraction
      return {
        recipient: this._extractNameFromText(responseText),
        subject: 'Message from OmiSend',
        content: '',
        purpose: 'communication',
        tone: 'professional',
        format: 'text'
      };
    }
  }

  /**
   * Parse and validate contact match response
   * @private
   */
  _parseContactMatchResponse(responseText, recipientHint) {
    try {
      // Sanitize JSON response
      const sanitizedText = responseText
        .replace(/[\u0000-\u001F\u007F-\u009F]/g, '') // Remove control characters
        .replace(/\\n/g, '\\\\n')  // Handle newlines
        .replace(/\\/g, '\\\\')    // Handle backslashes
        .replace(/\"/g, '\\\"');   // Handle quotes

      const result = JSON.parse(sanitizedText);
      console.log('OpenAI contact matching result:', result);
      
      if (result.email && result.email !== "no match") {
        // Validate the email is in the expected format
        if (!result.email.includes('@')) {
          console.warn('Invalid email format returned from OpenAI:', result.email);
          return null;
        }
        
        // Ensure confidence is a number between 0 and 1
        result.confidence = typeof result.confidence === 'number' ? 
          Math.min(Math.max(result.confidence, 0), 1) : 0.5;
          
        // Ensure alternatives is an array
        result.alternatives = Array.isArray(result.alternatives) ? 
          result.alternatives : [];
          
        return result;
      }
      
      return null;
    } catch (parseError) {
      console.error('Error parsing OpenAI JSON response:', parseError);
      
      // Try to extract email from text
      try {
        const emailMatch = responseText.match(/["']email["']\s*:\s*["']([^"']+@[^"']+)["']/i);
        if (emailMatch && emailMatch[1] && emailMatch[1].includes('@') && emailMatch[1] !== "no match") {
          return {
            email: emailMatch[1],
            name: recipientHint,
            confidence: 0.7,
            reasoning: "Extracted from malformed JSON response",
            alternatives: []
          };
        }
      } catch (extractError) {
        console.error('Error extracting email from response:', extractError);
      }
      
      return null;
    }
  }

  /**
   * Fallback method for contact match
   * @private
   */
  _fallbackContactMatch(recipientHint, reason) {
    return {
      email: "no match",
      name: "",
      confidence: 0,
      reasoning: reason,
      alternatives: []
    };
  }
}

module.exports = EmailGenerator; 
const OpenAI = require('openai');

// Helper function to build contextual information
function buildContextualInformation(context, user, recipient) {
  let contextStr = '';
  
  if (context.isExternal) {
    contextStr += '\n- Communication Type: External (different organizations)';
  } else {
    contextStr += '\n- Communication Type: Internal (same organization)';
  }
  
  if (context.subjectIntent) {
    contextStr += `\n- Primary Intent: ${context.subjectIntent}`;
  }
  
  if (context.requestsMeeting) {
    contextStr += '\n- Includes Meeting Request: Yes';
    if (context.containsDateOrTime) {
      contextStr += ' (with specific timing)';
    }
  }
  
  if (context.isUrgent) {
    contextStr += '\n- Priority: Urgent';
  }
  
  if (context.requestsResponse) {
    contextStr += '\n- Requires Response: Yes';
  }
  
  if (context.isFollowUp) {
    contextStr += '\n- Type: Follow-up communication';
  }
  
  return contextStr;
}

// Helper function to get style guidelines based on tone
function getStyleGuidelines(tone, template) {
  const guidelines = {
    formal: '- Use formal language with complete sentences\n- Avoid contractions (use "cannot" instead of "can\'t")\n- Include proper salutation and closing\n- Maintain professional distance\n- Use precise, clear language',
    
    professional: '- Use clear, straightforward language\n- Be concise but thorough\n- Include appropriate level of detail\n- Balance friendliness with professionalism\n- Use industry-standard terminology where appropriate',
    
    friendly: '- Use a warm, conversational tone\n- Include personal touches where appropriate\n- Use contractions to sound natural\n- Be personable while maintaining professionalism\n- Show enthusiasm where appropriate',
    
    brief: '- Use short sentences and minimal words\n- Get straight to the point\n- Use bullet points if needed\n- Focus only on essential information\n- Clear closing with next steps if needed',
    
    casual: '- Use relaxed, conversational language\n- Include friendly opening and closing\n- Use contractions and common expressions\n- Be personable and approachable\n- Still maintain basic professionalism'
  };
  
  return guidelines[tone?.toLowerCase()] || guidelines.professional;
}

// Helper function to determine appropriate email template based on tone
function determineEmailTemplate(tone) {
  if (!tone) return null;
  
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
  
  return null; // Use default formatting if no specific tone is detected
}

// Function to validate if an email command is coherent and complete
function validateEmailCommand(command) {
  if (!command || command.trim().length < 10) {
    return { valid: false, reason: "Command too short" };
  }

  // Check for fragmented or incomplete sentences
  const sentences = command.split(/[.!?]+/);
  if (sentences.some(s => s.trim().length > 0 && s.trim().length < 5)) {
    return { valid: false, reason: "Contains very short/fragmented sentences" };
  }

  // Check for incomplete command structure
  if (!command.toLowerCase().includes('to')) {
    return { valid: false, reason: "Missing 'to' preposition for recipient" };
  }

  // Check for nonsensical verbs before "email"
  const emailActionMatch = command.toLowerCase().match(/\b(please)?\s*([\w]+)\s+(an|a|the)?\s*email\b/i);
  if (emailActionMatch) {
    const verb = emailActionMatch[2].toLowerCase();
    const validVerbs = ['send', 'write', 'draft', 'compose', 'create', 'prepare'];
    if (!validVerbs.includes(verb)) {
      return { valid: false, reason: `Invalid verb '${verb}' before 'email'` };
    }
  }

  return { valid: true };
}

// Helper function to validate and fix any issues with the generated email body
function validateAndNormalizeEmailBody(body, user, recipient, subject = null) {
  // Check for duplicated content first
  body = checkAndRemoveDuplicatedContent(body);
  
  // Remove any repeated subject lines
  if (subject) {
    // Remove "Subject:" lines
    body = body.replace(/^(?:Subject|Re|Regarding|RE|FWD?|Forward):[^\n]*\n+/i, '');
    // Remove subject at the start of paragraphs  
    body = body.replace(/\n+(?:Subject|Re|Regarding|RE|FWD?|Forward):[^\n]*\n+/i, '\n\n');
    // Remove entire line if it's just the subject text
    body = body.replace(new RegExp(`^${subject.trim()}\\s*$`, 'gim'), '');
    // Remove if the first paragraph is just the subject
    body = body.replace(new RegExp(`\\n\\n${subject.trim()}\\s*\\n\\n`, 'gi'), '\n\n');
  }

  // Remove any existing duplicate greetings first
  const greetingRegex = /^(Dear|Hi|Hello|Good morning|Good afternoon|Good evening|Greetings)[^,\n]*,?\s*\n+/gmi;
  const greetingMatches = [...body.matchAll(greetingRegex)];
  
  if (greetingMatches.length > 1) {
    // Keep only the first greeting
    const firstGreeting = greetingMatches[0][0];
    // Remove all greetings
    body = body.replace(greetingRegex, '');
    // Add back only the first greeting
    body = firstGreeting + body;
  } else if (!hasValidGreeting(body)) {
    // Only add greeting if none exists
    const greeting = `Hi ${recipient.name?.split(' ')[0] || recipient.name || 'there'},\n\n`;
    body = greeting + body;
  }

  // Remove any existing duplicate signatures/closings
  const signatureRegex = /\n\s*(Kind Regards|Best Regards|Warm Regards|Yours Sincerely|Yours Truly|Best Wishes|Regards|Sincerely|Best|Thanks|Thank you|Cheers|Yours|Warmly|Cordially),?\s*\n\s*([A-Z][a-zA-Z\s.\-'']*)/gi;
  const sigMatches = [...body.matchAll(signatureRegex)];
  
  if (sigMatches.length > 1) {
    // Keep only the last signature (which should have the correct name)
    const lastSignature = sigMatches[sigMatches.length - 1][0];
    // Remove all signatures
    body = body.replace(signatureRegex, '');
    // Add back only the last valid signature with proper spacing
    body = body.trim() + '\n\n' + lastSignature.trim();
  } else if (!hasValidSignature(body, user.name)) {
    // Only add signature if none exists
    // Ensure double line break before signature
    body = body.trim() + '\n\n' + 'Best regards,' + '\n' + user.name;
    
    // Add email if it's missing from the signature and user email is available
    if (user.email && !body.includes(user.email)) {
      if (!body.toLowerCase().includes('email') && !body.includes('@')) {
        body += '\n' + `(${user.email})`;
      }
    }
  }

  // Normalize line breaks and remove multiple consecutive blank lines
  body = body
    .replace(/\r\n/g, '\n')  // Normalize to \n
    .replace(/\n{3,}/g, '\n\n')  // Replace 3+ consecutive line breaks with 2
    .trim();

  // Remove any placeholders [like this] or {like this}
  body = body.replace(/\[[^\]]+\]/g, '').replace(/\{[^}]+\}/g, '');

  return body;
}

// Helper function to check for and remove duplicated content
function checkAndRemoveDuplicatedContent(body) {
  if (!body) return body;
  
  try {
    // Split the content into lines for analysis
    const lines = body.split('\n');
    const contentLength = lines.length;
    
    // If content is too short, just return it
    if (contentLength < 10) return body;
    
    // Check for exact duplication (the most common case)
    const halfLength = Math.floor(contentLength / 2);
    
    // Check if the first half matches the second half
    let isDuplicated = true;
    for (let i = 0; i < halfLength; i++) {
      if (i + halfLength < lines.length && lines[i] !== lines[i + halfLength]) {
        isDuplicated = false;
        break;
      }
    }
    
    // If exact duplication is found, return just the first half
    if (isDuplicated) {
      return lines.slice(0, halfLength).join('\n');
    }
    
    // Check for partial duplication using signature as a marker
    const signaturePatterns = [
      /Regards,\s*$/i,
      /Best regards,\s*$/i,
      /Sincerely,\s*$/i,
      /Best,\s*$/i,
      /Thanks,\s*$/i,
      /Thank you,\s*$/i,
      /Cheers,\s*$/i
    ];
    
    for (const pattern of signaturePatterns) {
      for (let i = Math.floor(contentLength / 3); i < contentLength - 5; i++) {
        if (pattern.test(lines[i])) {
          // Found a potential signature - check if the content after this repeats
          const afterSignatureStartIdx = i + 2;
          if (afterSignatureStartIdx < lines.length) {
            // Check if there's duplicate content after the signature
            const beforeSignature = lines.slice(0, i + 1).join('\n');
            
            return beforeSignature;
          }
        }
      }
    }
    
    return body;
  } catch (error) {
    console.error('Error checking for duplicated content:', error);
    return body;
  }
}

// Check if the email has a valid greeting
function hasValidGreeting(body) {
  return /^(Dear|Hi|Hello|Good morning|Good afternoon|Good evening|Greetings)[^,\n]*,?(\n|\s|$)/mi.test(body);
}

// Check if the email has a valid signature
function hasValidSignature(body, userName) {
  const escapedUserName = userName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // Escape special characters
  const sigRegex = new RegExp(`(Kind Regards|Best Regards|Warm Regards|Yours Sincerely|Yours Truly|Best Wishes|Regards|Sincerely|Best|Thanks|Thank you|Cheers|Yours|Warmly|Cordially),?\\s*\\n\\s*${escapedUserName}`, 'i');
  return sigRegex.test(body);
}

// Generate a fallback email for cases where the command is incoherent or OpenAI response is invalid
function generateFallbackEmailBody(user, subject, recipient, tone) {
  const greeting = `Hi ${recipient.name?.split(' ')[0] || recipient.name || 'there'},`;
  
  let body = `${greeting}\n\nI'm reaching out regarding "${subject}".\n\n`;
  
  if (tone === 'formal' || tone === 'professional') {
    body += 'I would appreciate the opportunity to discuss this matter further at your convenience.\n\n';
  } else {
    body += 'I wanted to connect with you about this. Let me know your thoughts.\n\n';
  }
  
  body += `Best regards,\n${user.name}`;
  
  if (user.email) {
    body += `\n(${user.email})`;
  }
  
  return body;
}
function generateFallbackEmailContent(user, subject, recipientContext, emailTone) {
    return generateFallbackEmailBody(user, subject, recipientContext, emailTone);
  }

// Advanced email body generation with enhanced personalization and context awareness
async function generateEmailBodyContent(originalUserCommand, user, subject, recipientContext, emailTone) {

    console.log(`[${user.id}] Generating email body content for command################: "${originalUserCommand}"`);
  // Check if the original command is coherent and complete enough to process
  const isCoherentCommand = validateEmailCommand(originalUserCommand);
  if (!isCoherentCommand.valid) {
    console.warn(`[${user.id}] Detected incoherent email command: "${originalUserCommand}". Reason: ${isCoherentCommand.reason}`);
    // Use a sensible fallback for incoherent commands
    return generateFallbackEmailContent(user, subject, recipientContext, emailTone);
  }

  try {
    const contextualInfo = buildContextualInformation(recipientContext, user, recipientContext.name);
    const styleGuidelines = getStyleGuidelines(emailTone, determineEmailTemplate(emailTone));

    // Extract recipient first name for personalized greeting
    const recipientFirstName = recipientContext.name ? 
                              recipientContext.name.split(' ')[0] : 
                              'there';

    const prompt = `You are an AI assistant helping to compose a professional email based on a user's voice command. 
Please create a well-structured, coherent email body based on the following details:

User's original command: "${originalUserCommand}"

Subject line: "${subject}"

Recipient: ${recipientFirstName} ${recipientContext.context ? `(Context: ${recipientContext.context})` : ''}

Style and tone: ${styleGuidelines}

Guidelines for email composition:
- Create a complete, professional email body with proper paragraph formatting.
- Start with an appropriate greeting to "${recipientFirstName}" (e.g., "Hi ${recipientFirstName}," or "Dear ${recipientFirstName},").
- Write 2-3 concise paragraphs that respond to the user's command.
- Be direct and get straight to the point. Avoid unnecessary text or explanations.
- Make each paragraph 2-3 sentences maximum.
- If the user's command is unclear, focus on the subject line "${subject}".
- Close with a single, professional closing phrase and the sender's name: "${user.name}"
- IMPORTANT: DO NOT repeat the subject line in the email body content. The subject is already set separately.

EMAIL COMPOSITION REQUIREMENTS:
1. Format:
   - Clear greeting (Hi/Hello/Dear ${recipientFirstName},)
   - 2-3 concise paragraphs with 2-3 sentences each 
   - Single closing phrase (Regards, Best regards, etc.)
   - Sender's name: "${user.name}"
   - NO extra signatures, NO timestamps, NO titles

2. Avoid:
   - ANY placeholder text in brackets [like this]
   - Complex or wordy sentences
   - Multiple closings or signatures
   - Repetitive information (especially do not repeat the subject line)
   - Generic filler text
   - Excessive formality or unnecessary details
   - Text after the signature
   - Starting with "Subject:" or "Re:"

Write the email as if it's ready to send, with proper spacing between paragraphs.`;

    // Make API call with optimized parameters for email generation
    const openaiClient = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY
    });

    const response = await openaiClient.chat.completions.create({
      model: 'gpt-3.5-turbo', 
      messages: [{role: "user", content: prompt}],
      max_tokens: 600, // Reduced for more concise emails
      temperature: 0.7,
      seed: 789
    });

    // Process and clean up the response
    let emailBody = response.choices[0].message.content.trim();
    
    // Clean up the generated email body
    emailBody = emailBody
      // Remove markdown formatting
      .replace(/^```email\s+|```$/gm, '')
      // Remove HTML comments
      .replace(/<!--[\s\S]*?-->/g, '')
      // Remove any random {{braces}} or [[brackets]] that might be artifacts
      .replace(/\{\{.*?\}\}|\[\[.*?\]\]|\[.*?\]/g, '')
      // Remove "Subject:" lines that might be included
      .replace(/^(?:Subject|Re|Regarding|RE|FWD?|Forward):[^\n]*\n+/i, '')
      // Remove "Subject:" at the start of paragraphs
      .replace(/\n+(?:Subject|Re|Regarding|RE|FWD?|Forward):[^\n]*\n+/i, '\n\n')
      // Remove entire line if it's just the subject text
      .replace(new RegExp(`^${subject.trim()}\\s*$`, 'gim'), '')
      // Ensure greeting format is correct - double newline after greeting
      .replace(/^(Dear|Hi|Hello|Good morning|Good afternoon|Good evening|Greetings)[^,\n]*,?\s*(\n*)/gmi, '$1,\n\n')
      // First normalize all line breaks
      .replace(/\r\n|\r|\n/g, '\n')
      // Remove any lines that are just whitespace
      .replace(/^\s*$\n/gm, '')
      // Ensure proper paragraph spacing - exactly two newlines between paragraphs
      .replace(/\n{3,}/g, '\n\n')
      // Handle the signature block with proper spacing
      .replace(/(\n*)(\s*(?:Kind Regards|Best Regards|Warm Regards|Regards|Yours Sincerely|Yours Truly|Best Wishes|Sincerely|Best|Thanks|Thank you|Cheers|Yours|Warmly|Cordially),?)\s*\n*\s*([A-Z][a-zA-Z\s.\-'']*)/gi, 
        '\n\n$2\n$3')
      // Clean up any trailing whitespace
      .trim();

    // Ensure there's a signature with the sender's name
    if (!hasValidSignature(emailBody, user.name)) {
      const closingPhrase = emailTone === 'formal' ? 'Yours sincerely,' : 
                           emailTone === 'friendly' ? 'Best wishes,' : 'Best regards,';
      emailBody = `${emailBody.trim()}\n\n${closingPhrase}\n${user.name}`;
    }
    
    // Ensure there's a greeting
    if (!hasValidGreeting(emailBody)) {
      emailBody = `Hi ${recipientFirstName},\n\n${emailBody}`;
    }
    
    // Final cleanup to ensure consistent formatting
    emailBody = emailBody
      // Ensure exactly one blank line after greeting
      .replace(/^(Dear|Hi|Hello|Good morning|Good afternoon|Good evening|Greetings)[^,\n]*,\s*\n+/gmi, '$1,\n\n')
      // Ensure exactly one blank line before signature
      .replace(/(\n+)((?:Kind Regards|Best Regards|Warm Regards|Regards|Yours Sincerely|Yours Truly|Best Wishes|Sincerely|Best|Thanks|Thank you|Cheers|Yours|Warmly|Cordially),\s*\n+[A-Z][a-zA-Z\s.\-'']*$)/gi, '\n\n$2')
      // Remove any trailing whitespace
      .trim();

    return emailBody;
  } catch (error) {
    console.error("Error generating email body with OpenAI:", error);
    return generateFallbackEmailContent(user, subject, recipientContext, emailTone);
  }
}

module.exports = {
  buildContextualInformation,
  getStyleGuidelines,
  determineEmailTemplate,
  validateEmailCommand,
  validateAndNormalizeEmailBody,
  checkAndRemoveDuplicatedContent,
  hasValidGreeting,
  hasValidSignature,
  generateFallbackEmailBody,
  generateFallbackEmailContent,
  generateEmailBodyContent
};

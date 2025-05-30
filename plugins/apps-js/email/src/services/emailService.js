const sendOmiNotification = require('../utils/omiUtils');
const { 
  extractNameFromText,
  findMatchingEmails
} = require('../utils/nameUtils');
const {
  buildContextualInformation,
  getStyleGuidelines,
  determineEmailTemplate,
  validateEmailCommand,
  validateAndNormalizeEmailBody,
  hasValidGreeting,
  hasValidSignature,
  generateFallbackEmailBody,
  generateFallbackEmailContent,
  generateEmailBodyContent
} = require('../models/aiEmailSender');
const { 
  draftEmail, 
  getEmailContacts 
} = require('../utils/emailUtils');
const { getAuthenticatedUser, supabase } = require('./authService');
const { generateSubjectWithOpenAI, findBestContactMatch, openaiClient } = require('./intentService');
const { isConnected } = require('../utils/redisUtils');
const { 
  loadSessionState, 
  saveSessionState 
} = require('./sessionService');
const {
  EMAIL_COMMAND_PATTERN,
  CONFIRMATION_PATTERNS,
  CONFIDENCE_THRESHOLD,
  PERFORMANCE_MONITORING_ENABLED
} = require('../config/constants');

/**
 * Helper function to extract a name from text with improved intelligence
 */
function localExtractNameFromText(text) {
  if (!text) return "recipient";
  
  // Clean the input text
  const cleanedText = text.replace(/['"]/g, '').trim();
  
  // Check for self-reference patterns first - return null if found
  const selfReferencePatterns = [
    /\b(?:to\s+)?(?:me|myself|my\s+account|my\s+email)\b/i,
    /\bsend\s+(?:a\s+|an\s+)?email\s+to\s+me\b/i,
    /\bmail\s+(?:to\s+)?me\b/i,
    /\bemail\s+myself\b/i
  ];
  
  if (selfReferencePatterns.some(pattern => pattern.test(cleanedText))) {
    return null; // Indicate self-reference
  }
  
  // Advanced patterns for recipient detection with better precision
  const patterns = [
    // Email patterns - recognize email addresses (highest confidence)
    { regex: /(?:to|for|email|send|contact)\s+([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+)/i, confidence: 1.0 },
    
    // Direct addressing with titles (high confidence)
    { regex: /(?:to|for|with|email\s+to|send\s+to|write\s+to|contact)\s+(?:mr\.?|mrs\.?|ms\.?|dr\.?|miss|mister|misses|doctor|prof\.?|professor)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)/i, confidence: 0.9 },
    
    // Standard addressing patterns - More precise extraction
    { regex: /(?:to|for|email\s+to|send\s+to|write\s+to|contact)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})(?:\s+about|\s+regarding|\s*$)/i, confidence: 0.8 },
    
    // Simple name after preposition
    { regex: /(?:to|for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)(?:\s|$)/i, confidence: 0.7 },
    
    // Email command followed by name
    { regex: /\b(?:email|mail)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)(?:\s+about|\s+regarding|\s|$)/i, confidence: 0.6 }
  ];
  
  // Try each pattern in order of decreasing confidence
  for (const pattern of patterns) {
    const match = cleanedText.match(pattern.regex);
    if (match && match[1]) {
      let name = match[1].trim();
      
      // Clean up common suffixes that shouldn't be part of the name
      name = name.replace(/\s+(?:about|regarding|that|the|for|with|at|in|on).*$/i, '');
      
      // Don't return very short names that might be noise, unless it's an email
      if (name.length > 2 || pattern.confidence === 1.0) {
        return name;
      }
    }
  }
  
  // Fallback: Look for any capitalized words that might be names, but be more selective
  const words = cleanedText.split(/\s+/);
  const nameIndicators = ['to', 'for', 'with', 'contact', 'email', 'send', 'write'];
  
  for (let i = 0; i < words.length - 1; i++) {
    if (nameIndicators.includes(words[i].toLowerCase())) {
      // Extract only the next 1-2 words if they look like names
      let nameParts = [];
      for (let j = i + 1; j < Math.min(i + 3, words.length); j++) {
        const word = words[j];
        // Stop at common stop words
        if (/^(?:about|regarding|that|the|for|with|at|in|on|and|or|but)$/i.test(word)) {
          break;
        }
        // Check if the word looks like a name (starts with capital letter)
        if (/^[A-Z][a-z]+$/.test(word)) {
          nameParts.push(word);
        } else {
          break; // Stop if we hit a non-name-like word
        }
      }
      
      if (nameParts.length > 0) {
        return nameParts.join(' ');
      }
    }
  }
  
  return "recipient";
}

/**
 * Analyze email with tone using OpenAI
 */
async function analyzeEmailWithTone(text, user, recipientHint, contactsListString) {
  try {
    console.log(`Analyzing email with potential recipient hint: ${recipientHint || 'none'}`);
    
    // Check for self-reference patterns first
    const selfReferencePatterns = [
      /\b(?:to\s+)?(?:me|myself|my\s+account|my\s+email)\b/i,
      /\bsend\s+(?:a\s+|an\s+)?email\s+to\s+me\b/i,
      /\bmail\s+(?:to\s+)?me\b/i,
      /\bemail\s+myself\b/i
    ];
    
    const isSelfReference = selfReferencePatterns.some(pattern => pattern.test(text));
    
    // Extract key information from the text
    const commandLower = text.toLowerCase();
    const hasClearRecipient = recipientHint && recipientHint !== 'unknown recipient' && recipientHint !== null;
    
    // Determine tone from command text
    let emailTone = 'professional'; // default
    if (/\b(?:formal|officially|professional|proper)\b/.test(commandLower)) {
      emailTone = 'formal';
    } else if (/\b(?:friendly|casual|nice|warm|personal)\b/.test(commandLower)) {
      emailTone = 'friendly';
    } else if (/\b(?:brief|short|quick|concise)\b/.test(commandLower)) {
      emailTone = 'brief';
    } else if (/\b(?:casual|relaxed|chill|informal)\b/.test(commandLower)) {
      emailTone = 'casual';
    }
    
    // First try to generate subject using OpenAI
    const userId = user.id || user.user_id || 'unknown';
    let extractedSubject = await generateSubjectWithOpenAI(text, userId);
    
    // If OpenAI fails, fall back to the original regex and rule-based method
    if (!extractedSubject) {
      console.log(`[${userId}] OpenAI subject generation failed, falling back to pattern matching`);
      
      // Extract subject from command text using pattern matching
      const subjectPatterns = [
        /(?:about|regarding|subject|title|topic|matter of)\s+"([^"]+)"/i,
        /(?:about|regarding|subject|title|topic|matter of)\s+'([^']+)'/i,
        /(?:about|regarding|subject|title|topic|matter of)\s+([^,.!?;:]+)/i,
      ];
      
      for (const pattern of subjectPatterns) {
        const match = text.match(pattern);
        if (match && match[1]) {
          extractedSubject = match[1].trim();
          break;
        }
      }
      
      // Generate a subject based on content if not explicitly mentioned
      if (!extractedSubject) {
        // Generate default subject based on content analysis
        extractedSubject = generateDefaultSubject(text, commandLower);
      }
    }
    
    // Clean up the subject
    extractedSubject = cleanupSubject(extractedSubject);
    
    // Determine recipient information
    let recipientInfo = null;
    let recipientConfidence = 0.5; // default mid confidence
    let suggestedRecipientEmail = 'defer_to_matching_logic';
    
    if (isSelfReference) {
      // User is referring to themselves
      recipientInfo = 'self';
      recipientConfidence = 1.0;
      suggestedRecipientEmail = user.email;
    } else if (contactsListString && hasClearRecipient) {
      // If we have a contact list and a hint, try to find the recipient directly
      const contacts = contactsListString.split('\n');
      const recipientHintLower = recipientHint.toLowerCase();
      
      // Try to find an exact match for the recipient
      for (const contact of contacts) {
        const parts = contact.match(/(.*?)\s*<([^>]+)>/);
        if (parts) {
          const [_, name, email] = parts;
          if (name.toLowerCase().includes(recipientHintLower) || 
              email.toLowerCase().includes(recipientHintLower)) {
            suggestedRecipientEmail = email;
            recipientConfidence = 0.9;
            break;
          }
        }
      }
      recipientInfo = recipientHint;
    }
    
    // Build the analysis result
    const result = {
      recipient: recipientInfo,
      subject: extractedSubject,
      tone: emailTone,
      format: commandLower.includes('html') ? 'html' : 'text',
      suggested_recipient_email: suggestedRecipientEmail,
      recipient_confidence: recipientConfidence
    };
    
    console.log("Email analysis complete:", result);
    return result;
    
  } catch (error) {
    console.error('Error analyzing email with tone:', error);
    throw error;
  }
}

/**
 * Generate default subject based on content analysis
 */
function generateDefaultSubject(text, commandLower) {
  // First, clean the command text of common command phrases
  const cleanedContent = text
    .replace(/(?:hey|hi|hello)\s+(?:email|e-mail|mail)/i, '')
    .replace(/(?:can you|please|would you|could you)\s+(?:send|draft|compose|write)\s+(?:an?|the)?\s*(?:email|message|mail)(?:\s+to\s+[^,.!?;:]+)?/i, '')
    .replace(/(?:send|draft|compose|write)\s+(?:an?|the)?\s*(?:email|message|mail)(?:\s+to\s+[^,.!?;:]+)?/i, '')
    .replace(/(?:\s+to\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b/i, '')
    .replace(/\b(?:et|at|hey|hey,|hi|hi,)\s+/i, '')
    .trim();
  
  // Extract key topics from the cleaned command
  const topics = cleanedContent.trim();
    
  // Use AI to generate a professional subject if text is suitable
  if (topics.length > 5) {
    // Extract the key purpose of the email
    const purposeMatches = [
      commandLower.match(/\b(?:discuss|regarding|about|update on|status of|progress on|meeting|schedule|appointment|invitation|confirm|request|approve|review|feedback|question|inquiry|information|collaborate|assistance|proposal|quotation|invoice|payment|follow[\s-]up|reminder|job|interview|application)\b/i),
      commandLower.match(/\b(?:project|task|assignment|deadline|document|report|plan|presentation|analysis|contract|agreement|policy|promotion|issue|problem|solution|opportunity|changes|updates|feature|product|service|launch|event|webinar|conference)\b/i)
    ];
    
    let purposeTerm = '';
    for (const match of purposeMatches) {
      if (match && match[0]) {
        purposeTerm = match[0].trim();
        break;
      }
    }
    
    // Get the first sentence or meaningful chunk as the subject base
    const sentences = topics.split(/[.!?;]/);
    const firstSentence = sentences[0].trim();
    
    // Create a concise, professional subject
    if (firstSentence.length < 60) {
      let result = firstSentence;
      
      // Add purpose term if it exists and isn't already in the subject
      if (purposeTerm && !result.toLowerCase().includes(purposeTerm.toLowerCase())) {
        // Check if subject already begins with a formal business prefix
        if (!/^(?:re:|regarding:|about:|update:)/i.test(result)) {
          const prefix = purposeTerm.charAt(0).toUpperCase() + purposeTerm.slice(1);
          result = `${prefix}: ${result}`;
        }
      }
      return result;
    } else {
      // For longer text, create a more summarized subject
      const keywordMatches = topics.match(/\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?|[a-z]+(?:ing|ment|tion|sion|ance|ence|ity|ship|age))\b/g);
      const keywords = keywordMatches ? [...new Set(keywordMatches)].slice(0, 3) : [];
      
      if (keywords.length > 0) {
        // Use extracted keywords for subject
        let result = keywords.join(' ');
        
        // Add business prefix if we have a purpose term
        if (purposeTerm) {
          const prefix = purposeTerm.charAt(0).toUpperCase() + purposeTerm.slice(1);
          result = `${prefix}: ${result}`;
        } else {
          // Use a generic business prefix
          result = `Regarding: ${result}`;
        }
        return result;
      } else {
        // Fallback - take first 50 chars
        return topics.substring(0, 50);
      }
    }
  } else {
    // Analyze for intent to generate a fallback subject
    return generateFallbackSubjectByIntent(commandLower);
  }
}

/**
 * Generate fallback subject based on intent analysis
 */
function generateFallbackSubjectByIntent(commandLower) {
  const taskMatches = [
    commandLower.match(/\b(?:ask|tell|inform|discuss|talk about|mention|bring up|update|status|progress|news|info|information)\s+(?:on|about|regarding)?\s+([^,.!?;:]+)/i),
    commandLower.match(/\b(?:task|assignment|project|work|report|meeting|call|agenda)\s+(?:for|on|about)?\s+([^,.!?;:]+)/i),
    commandLower.match(/\b(?:schedule|appointment|interview|session|consultation)\s+(?:for|on|with)?\s+([^,.!?;:]+)/i)
  ];
  
  let subjectTerm = '';
  for (const match of taskMatches) {
    if (match && match[1]) {
      subjectTerm = match[1].trim();
      break;
    }
  }
  
  if (subjectTerm) {
    const prefix = /\b(?:meeting|call|agenda|appointment|interview)\b/i.test(commandLower) ? 
                 "Scheduling" : 
                 /\b(?:update|status|progress|report)\b/i.test(commandLower) ?
                 "Update on" : "Regarding";
    
    return `${prefix} ${subjectTerm}`;
  } else {
    // Intelligent contextual fallbacks based on email purpose
    if (/\b(?:meet|meeting|schedule|calendar|availability|time|date)\b/i.test(commandLower)) {
      return "Meeting Request";
    } else if (/\b(?:update|progress|status|report|news)\b/i.test(commandLower)) {
      return "Project Update";
    } else if (/\b(?:question|help|assist|support|guidance)\b/i.test(commandLower)) {
      return "Request for Assistance";
    } else if (/\b(?:follow|remind|pending|waiting)\b/i.test(commandLower)) {
      return "Follow-up";
    } else if (/\b(?:job|position|role|opportunity|career|apply|hire|interview)\b/i.test(commandLower)) {
      return "Job Opportunity Discussion";
    } else {
      return "Professional Correspondence";
    }
  }
}

/**
 * Clean up subject line
 */
function cleanupSubject(extractedSubject) {
  // Clean up the subject - remove common voice command artifacts
  const subjectCleanupPatterns = [
    /^(?:hey|hi|okay|ok)\s+(?:email|e-mail|mail)\s*/i,
    /^(?:can you|please|would you|could you)\s+(?:just)?\s*/i,
    /^(?:i want to|i need to|i'd like to|i would like to)\s*/i, 
    /^(?:e\s+load|load)\s*/i,
    /^(?:draft|write|compose|send)\s+(?:an?|the)?\s*(?:email|message|mail)(?:\s+to)?\s*/i,
    /^(?:to|for)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s*/i,
    /^(?:asking|telling)\s+(?:him|her|them)\s+(?:about|that|to)\s*/i
  ];
  
  for (const pattern of subjectCleanupPatterns) {
    extractedSubject = extractedSubject.replace(pattern, '');
  }
  
  // Final cleanup and formatting
  extractedSubject = extractedSubject.trim();
  if (extractedSubject.length === 0) {
    extractedSubject = "Professional Correspondence";
  } else {
    // Proper capitalization - capitalize first letter of each word for professional subjects
    extractedSubject = extractedSubject.replace(/\b\w/g, c => c.toUpperCase());
    
    // Remove any remaining separator characters at the beginning
    extractedSubject = extractedSubject.replace(/^[,.!?;:\-_]+\s*/, '');
    
    // Truncate if too long, but try to break at a word boundary
    if (extractedSubject.length > 60) {
      const truncated = extractedSubject.substring(0, 57);
      const lastSpaceIndex = truncated.lastIndexOf(' ');
      
      if (lastSpaceIndex > 40) { // Only break at word boundary if we're not losing too much content
        extractedSubject = truncated.substring(0, lastSpaceIndex) + '...';
      } else {
        extractedSubject = truncated + '...';
      }
    }
  }
  
  return extractedSubject;
}

/**
 * Generate professional email content using OpenAI
 * @param {string} originalCommand - The original voice command
 * @param {string} subject - Email subject
 * @param {object} recipient - Recipient information {name, email}
 * @param {object} sender - Sender information {name, email}
 * @param {string} tone - Email tone (professional, friendly, formal, brief)
 * @param {string} userId - User ID for logging
 * @returns {Promise<string>} - Generated email content
 */
async function generateEmailContentWithOpenAI(originalCommand, subject, recipient, sender, tone = 'professional', userId) {
  try {
    console.log(`[${userId}] Generating email content with OpenAI for subject: "${subject}"`);
    
    // Clean the original command to extract the core message
    const cleanedMessage = originalCommand
      // Remove trigger phrases and common voice artifacts
      .replace(/^.*?(?:hey\s+email|email)\s*/i, '')
      .replace(/^(?:है\s*){1,}\s*/i, '')
      .replace(/(?:can you please|please|could you|would you)\s+(?:draft|write|compose|send)\s+(?:a|an|the)?\s*(?:mail|email)\s+(?:to\s+)?/i, '')
      .replace(/^(?:draft|write|compose|send)\s+(?:a|an|the)?\s*(?:mail|email)\s+(?:to\s+)?/i, '')
      .replace(/\b(?:say the fan|to say the fan)\s*/i, '')
      .replace(/\?\s*regarding/i, '. Regarding')
      .replace(/\?\s*ask/i, '. Please')
      .trim();

    // Check if this is a self-email (user sending to themselves)
    const isSelfEmail = sender.email === recipient.email || 
                       sender.email.toLowerCase() === recipient.email.toLowerCase();

    // Determine tone-specific guidance
    const toneGuidance = {
      professional: "Write in a professional, business-appropriate tone. Be clear, concise, and respectful.",
      friendly: "Write in a warm, friendly tone while maintaining professionalism. Be approachable and personable.",
      formal: "Write in a formal, official tone. Use proper business language and maintain formality throughout.",
      brief: "Write in a concise, brief manner. Get straight to the point while remaining professional."
    };

    let prompt;
    
    if (isSelfEmail) {
      // Special handling for self-emails (reminders, notes, drafts)
      prompt = `You are an expert email writer. Generate a self-email (reminder/note to oneself) based on the following information:

RECIPIENT: ${sender.name} (sending to self)
SENDER: ${sender.name}
SUBJECT: ${subject}
TONE: ${tone} - ${toneGuidance[tone] || toneGuidance.professional}
ORIGINAL REQUEST: ${cleanedMessage}

INSTRUCTIONS:
1. Write a complete email body as a personal reminder or note
2. Start with a friendly greeting like "Hi ${sender.name}," or "Dear ${sender.name},"
3. Include the main message based on the original request
4. Write it as if the user is leaving themselves a reminder or note
5. End with an appropriate closing and the sender's name: ${sender.name}
6. Make the content natural and helpful as a self-reminder
7. Use the actual names provided, never use placeholders like [Name]

Generate ONLY the email body content (no headers, no formatting markup):`;
    } else {
      // Regular email to another person
      prompt = `You are an expert email writer. Generate a professional email body based on the following information:

RECIPIENT: ${recipient.name} (${recipient.email})
SENDER: ${sender.name}
SUBJECT: ${subject}
TONE: ${tone} - ${toneGuidance[tone] || toneGuidance.professional}
ORIGINAL REQUEST: ${cleanedMessage}

INSTRUCTIONS:
1. Write a complete, professional email body (do not include subject line, to/from headers)
2. Start with an appropriate greeting using the recipient's name: ${recipient.name}
3. Include the main message based on the original request
4. End with an appropriate closing and the sender's name: ${sender.name}
5. Make the content natural and professional
6. Ensure the email flows well and addresses the purpose clearly
7. If the original request mentions deadlines, specific actions, or questions, include them appropriately
8. Use the actual names provided, never use placeholders like [Name] or [Recipient's Name]

Generate ONLY the email body content (no headers, no formatting markup):`;
    }

    const response = await openaiClient.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [
        {
          role: 'system',
          content: 'You are a professional email writing assistant. Generate clear, well-structured, and professional email content based on user requests. NEVER use placeholder text like [Name] or [Recipient\'s Name]. Always use the actual names provided in the prompt.'
        },
        {
          role: 'user',
          content: prompt
        }
      ],
      max_tokens: 500,
      temperature: 0.7,
    });

    const generatedContent = response.choices[0].message.content.trim();
    
    // Clean up any potential formatting artifacts
    let cleanedContent = generatedContent
      .replace(/^Email Body:\s*/i, '')
      .replace(/^Body:\s*/i, '')
      .replace(/^\*{1,}\s*/, '')
      .replace(/\*{1,}\s*$/, '')
      .trim();

    // Additional cleanup to ensure no placeholders remain
    cleanedContent = cleanedContent
      .replace(/\[Recipient'?s?\s+Name\]/gi, recipient.name)
      .replace(/\[Your\s+Name\]/gi, sender.name)
      .replace(/\[Name\]/gi, isSelfEmail ? sender.name : recipient.name)
      .replace(/\[Sender'?s?\s+Name\]/gi, sender.name);

    console.log(`[${userId}] Generated email content with OpenAI successfully`);
    return cleanedContent;

  } catch (error) {
    console.error(`[${userId}] Error generating email content with OpenAI:`, error);
    
    // Clean the original command for fallback
    const cleanedMessage = originalCommand
      .replace(/^.*?(?:hey\s+email|email)\s*/i, '')
      .replace(/^(?:है\s*){1,}\s*/i, '')
      .replace(/(?:can you please|please|could you|would you)\s+(?:draft|write|compose|send)\s+(?:a|an|the)?\s*(?:mail|email)\s+(?:to\s+)?/i, '')
      .replace(/^(?:draft|write|compose|send)\s+(?:a|an|the)?\s*(?:mail|email)\s+(?:to\s+)?/i, '')
      .trim();
    
    // Check if this is a self-email for fallback
    const isSelfEmail = sender.email === recipient.email || 
                       sender.email.toLowerCase() === recipient.email.toLowerCase();
    
    // Fallback to a simple template if OpenAI fails
    const fallbackContent = isSelfEmail ? 
      `Hi ${sender.name},

This is a reminder about: ${cleanedMessage}

Best regards,
${sender.name}` :
      `Hi ${recipient.name},

I hope this email finds you well.

${cleanedMessage}

Best regards,
${sender.name}`;
    
    console.log(`[${userId}] Using fallback email content due to OpenAI error`);
    return fallbackContent;
  }
}

/**
 * Process email command using comprehensive AI analysis
 * Handles any language, format, or sentence structure
 */
async function processEmailCommand(text, userId, responseHandler = null) {
  console.log(`[${userId}] Processing email command with AI:`, text);
  const startTime = process.hrtime();
  
  try {
    // Get the authenticated user
    const user = await getAuthenticatedUser(userId);
    
    // Get all email contacts
    console.log(`[${userId}] Using user ${user.name} (${user.id || user.user_id}) to retrieve contacts`);
    const allContacts = await getEmailContacts(user);
    
    // Create contacts list string for AI analysis
    const contactsListString = allContacts && allContacts.length > 0 
      ? allContacts.map(contact => {
          if (contact.email) {
            return `${contact.name || contact.email} <${contact.email}>`;
          }
          return contact.name || 'Unknown';
        }).join('\n')
      : 'No contacts available';
    
    // Use comprehensive AI analysis
    const aiAnalysis = await analyzeTextWithAI(text, user, contactsListString);
    
    // Check if this is even an email command
    if (!aiAnalysis.isEmailCommand || aiAnalysis.confidence < 0.3) {
      console.log(`[${userId}] AI determined this is not an email command (confidence: ${aiAnalysis.confidence})`);
      return {
        success: false,
        message: "I didn't detect a command to send an email. Please try again with a clear email request.",
        aiAnalysis: aiAnalysis
      };
    }
    
    console.log(`[${userId}] AI detected email command with ${aiAnalysis.confidence} confidence in ${aiAnalysis.language}`);
    
    // Handle different recipient types based on AI analysis
    let finalRecipient = null;
    
    if (aiAnalysis.recipient.type === "self") {
      // User wants to send email to themselves
      console.log(`[${userId}] AI detected self-reference`);
      finalRecipient = {
        email: user.email,
        name: user.name || user.email.split('@')[0]
      };
      
    } else if (aiAnalysis.recipient.email && aiAnalysis.recipient.email.includes('@')) {
      // PRIORITY: If AI detected any email address, use it directly regardless of type
      console.log(`[${userId}] AI detected email address (priority): ${aiAnalysis.recipient.email}`);
      finalRecipient = {
        email: aiAnalysis.recipient.email,
        name: aiAnalysis.recipient.name || aiAnalysis.recipient.email.split('@')[0]
      };
      
    } else if (aiAnalysis.recipient.type === "contact" && aiAnalysis.recipient.name) {
      // Only try contact matching if no email was detected
      console.log(`[${userId}] AI detected contact name (no email detected): ${aiAnalysis.recipient.name}`);
      
      if (allContacts && allContacts.length > 0) {
        const contactMatch = await findBestContactMatch(aiAnalysis.recipient.name, contactsListString);
        
        if (contactMatch && contactMatch.email && contactMatch.email !== "no match") {
          // Be much stricter with confidence thresholds
          if (contactMatch.confidence >= 0.8) {
            console.log(`[${userId}] High confidence contact match: ${contactMatch.name} <${contactMatch.email}>`);
            finalRecipient = {
              email: contactMatch.email,
              name: contactMatch.name
            };
          } else if (contactMatch.confidence >= 0.6) {
            // Medium confidence - ask for confirmation
            console.log(`[${userId}] Medium confidence match, asking for confirmation`);
            try {
              await sendOmiNotification(userId, `🤔 I found "${contactMatch.name}" (${contactMatch.email}) as a possible match for "${aiAnalysis.recipient.name}". Is this correct? Say "yes" to confirm or "no" to try again.`);
            } catch (notificationError) {
              console.error(`[${userId}] Failed to send confirmation notification:`, notificationError);
            }
            
            return {
              success: false,
              message: `🤔 I found "${contactMatch.name}" (${contactMatch.email}) as a possible match for "${aiAnalysis.recipient.name}". Is this correct?`,
              needsConfirmation: true,
              suggestedRecipient: contactMatch,
              aiAnalysis: aiAnalysis
            };
          } else {
            // Low confidence - treat as no match
            console.log(`[${userId}] Low confidence match (${contactMatch.confidence}), treating as no match`);
            contactMatch.email = "no match"; // Force no match treatment
          }
        }
        
        if (!contactMatch || contactMatch.email === "no match") {
          // No matching contact found
          console.log(`[${userId}] No matching contact found for: ${aiAnalysis.recipient.name}`);
          const suggestions = await findSimilarContacts(aiAnalysis.recipient.name, allContacts);
          
          let suggestionMessage = `❌ I couldn't find "${aiAnalysis.recipient.name}" in your contacts.`;
          if (suggestions.length > 0) {
            const suggestionList = suggestions.slice(0, 3).map(s => `"${s.name || s.email.split('@')[0]}"`).join(', ');
            suggestionMessage += ` Did you mean: ${suggestionList}?`;
          } else {
            suggestionMessage += ` Please provide the full email address or check the spelling.`;
          }
          
          try {
            await sendOmiNotification(userId, suggestionMessage);
          } catch (notificationError) {
            console.error(`[${userId}] Failed to send suggestion notification:`, notificationError);
          }
          
          return {
            success: false,
            message: suggestionMessage,
            needsRecipient: true,
            suggestions: suggestions,
            aiAnalysis: aiAnalysis
          };
        }
      } else {
        return {
          success: false,
          message: "I couldn't find any contacts in your email history. Please specify the full email address of the recipient.",
          aiAnalysis: aiAnalysis
        };
      }
      
    } else {
      // No recipient detected or unclear
      console.log(`[${userId}] AI detected unclear or missing recipient`);
      
      try {
        await sendOmiNotification(userId, "❓ Who would you like to send this email to? Please say the recipient's name or email address.");
      } catch (notificationError) {
        console.error(`[${userId}] Failed to send clarification notification:`, notificationError);
      }
      
      return {
        success: false,
        message: "❓ I need to know who to send this email to. Please specify the recipient's name or email address.",
        needsRecipient: true,
        aiAnalysis: aiAnalysis
      };
    }

    // Generate email content using AI analysis and OpenAI
    const subject = aiAnalysis.subject || "Professional Email";
    const tone = aiAnalysis.tone || "professional";
    
    console.log(`[${userId}] Generating email content for recipient: ${finalRecipient.name} with subject: ${subject}`);
    
    const emailBody = await generateEmailContentWithOpenAI(
      aiAnalysis.content || text, 
      subject, 
      finalRecipient, 
      { name: user.name, email: user.email }, 
      tone, 
      userId
    );

    // Send the email
    console.log(`[${userId}] Sending email to ${finalRecipient.email}`);
    
    try {
      const emailResult = await draftEmail(finalRecipient.email, subject, emailBody, user);
      
      if (emailResult && emailResult.messageId) {
        console.log(`[${userId}] Email sent successfully with ID: ${emailResult.messageId}`);
        
        // Send success notification
        try {
          await sendOmiNotification(userId, `✅ Email sent to ${finalRecipient.name} with subject "${subject}".`);
          console.log(`[${userId}] Sent success notification via Omi`);
        } catch (notificationError) {
          console.error(`[${userId}] Failed to send Omi notification:`, notificationError);
        }
        
        // Calculate total processing time
        const [seconds, nanoseconds] = process.hrtime(startTime);
        const totalTime = seconds * 1000 + nanoseconds / 1000000;
        console.log(`[${userId}] Email processed in ${totalTime.toFixed(2)}ms`);

        return {
          success: true,
          message: `✅ Email sent to ${finalRecipient.name} with subject "${subject}".`,
          recipient: finalRecipient.email,
          subject: subject,
          messageId: emailResult.messageId,
          aiAnalysis: aiAnalysis
        };
      } else {
        throw new Error('Email sending failed - no message ID returned');
      }
    } catch (emailError) {
      console.error(`[${userId}] Error sending email:`, emailError);
      
      // Send error notification
      try {
        await sendOmiNotification(userId, `❌ Failed to send email to ${finalRecipient.name}. Please try again.`);
      } catch (notificationError) {
        console.error(`[${userId}] Failed to send error notification:`, notificationError);
      }
      
      return {
        success: false,
        message: `❌ Failed to send email to ${finalRecipient.name}. Please try again.`,
        aiAnalysis: aiAnalysis
      };
    }

  } catch (error) {
    console.error(`[${userId}] Error processing email command:`, error);
    return {
      success: false,
      message: `❌ Something went wrong. Please try again with a clearer message.`
    };
  }
}

/**
 * Find similar contacts when exact matching fails
 * @param {string} searchName - The name to search for
 * @param {Array} contacts - Array of contact objects
 * @returns {Array} - Array of similar contacts
 */
async function findSimilarContacts(searchName, contacts) {
  if (!searchName || !contacts || contacts.length === 0) {
    return [];
  }
  
  const searchLower = searchName.toLowerCase();
  const suggestions = [];
  
  // Calculate similarity scores for all contacts
  for (const contact of contacts) {
    if (!contact.name && !contact.email) continue;
    
    const contactName = (contact.name || contact.email.split('@')[0]).toLowerCase();
    const contactEmail = contact.email ? contact.email.toLowerCase() : '';
    
    let score = 0;
    
    // Exact match (perfect score)
    if (contactName === searchLower) {
      score = 1.0;
    } else {
      // Exact substring match (high score)
      if (contactName.includes(searchLower) || searchLower.includes(contactName)) {
        score += 0.8;
      }
      
      // Email domain or username match
      if (contactEmail.includes(searchLower) || searchLower.includes(contactEmail.split('@')[0])) {
        score += 0.6;
      }
      
      // Word-by-word matching
      const searchWords = searchLower.split(/\s+/);
      const contactWords = contactName.split(/\s+/);
      
      let wordMatches = 0;
      for (const searchWord of searchWords) {
        for (const contactWord of contactWords) {
          if (searchWord.length > 1 && contactWord.length > 1) {
            if (contactWord.includes(searchWord) || searchWord.includes(contactWord)) {
              wordMatches++;
              score += 0.4;
            }
          }
        }
      }
      
      // Levenshtein distance for typos (most important for short names)
      if (searchLower.length > 1 && contactName.length > 1) {
        const firstNameContact = contactWords[0] || contactName;
        const distance = calculateSimpleDistance(searchLower, firstNameContact);
        const maxLength = Math.max(searchLower.length, firstNameContact.length);
        const similarity = 1 - (distance / maxLength);
        
        if (similarity > 0.6) { // 60% similarity or better
          score += similarity * 0.7; // Weight by similarity
        }
        
        // Special case for very similar short names (e.g., "Jon" vs "John")
        if (searchLower.length <= 4 && firstNameContact.length <= 6) {
          if (distance <= 1) { // Only 1 character difference
            score += 0.8;
          }
        }
      }
      
      // Phonetic similarity for common name variations
      const phoneticMatches = checkPhoneticSimilarity(searchLower, contactName);
      if (phoneticMatches) {
        score += 0.6;
      }
    }
    
    if (score > 0.3) { // Minimum similarity threshold
      suggestions.push({
        ...contact,
        similarity: score
      });
    }
  }
  
  // Sort by similarity and return top matches
  return suggestions
    .sort((a, b) => b.similarity - a.similarity)
    .slice(0, 5); // Return top 5 suggestions
}

/**
 * Check phonetic similarity for common name variations
 * @param {string} search - Search term
 * @param {string} name - Contact name
 * @returns {boolean} - True if phonetically similar
 */
function checkPhoneticSimilarity(search, name) {
  const phoneticPairs = [
    ['jon', 'john'],
    ['sara', 'sarah'],
    ['afan', 'affan'],
    ['mike', 'michael'],
    ['jen', 'jennifer'],
    ['bob', 'robert'],
    ['bill', 'william'],
    ['dick', 'richard'],
    ['dave', 'david'],
    ['jim', 'james'],
    ['tony', 'anthony'],
    ['chris', 'christopher'],
    ['matt', 'matthew'],
    ['dan', 'daniel'],
    ['tom', 'thomas']
  ];
  
  for (const [short, long] of phoneticPairs) {
    if ((search === short && name.includes(long)) || 
        (search === long && name.includes(short)) ||
        (search.includes(short) && name.includes(long)) ||
        (search.includes(long) && name.includes(short))) {
      return true;
    }
  }
  
  return false;
}

/**
 * Calculate simple string distance (simplified Levenshtein)
 * @param {string} str1 - First string
 * @param {string} str2 - Second string
 * @returns {number} - Distance between strings
 */
function calculateSimpleDistance(str1, str2) {
  const track = Array(str2.length + 1).fill(null).map(() =>
    Array(str1.length + 1).fill(null));
  
  for (let i = 0; i <= str1.length; i += 1) {
    track[0][i] = i;
  }
  for (let j = 0; j <= str2.length; j += 1) {
    track[j][0] = j;
  }
  for (let j = 1; j <= str2.length; j += 1) {
    for (let i = 1; i <= str1.length; i += 1) {
      const indicator = str1[i - 1] === str2[j - 1] ? 0 : 1;
      track[j][i] = Math.min(
        track[j][i - 1] + 1, // deletion
        track[j - 1][i] + 1, // insertion
        track[j - 1][i - 1] + indicator // substitution
      );
    }
  }
  return track[str2.length][str1.length];
}

/**
 * Check if email command has no recipient mentioned
 * @param {string} text - Email command text
 * @returns {boolean} - True if no recipient is mentioned
 */
function hasNoRecipientMentioned(text) {
  if (!text) return true;
  
  const cleanText = text.toLowerCase();
  
  // First, check for explicit recipient indicators
  const hasExplicitRecipient = [
    // Self-reference patterns
    /\b(?:to|for)\s+(?:me|myself|my\s+account|my\s+email)\b/i,
    /\bsend\s+(?:a\s+|an\s+)?email\s+to\s+me\b/i,
    /\bemail\s+(?:me|myself)\b/i,
    
    // Email addresses
    /[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+/i,
    
    // Names after prepositions
    /\b(?:to|for)\s+[A-Z][a-zA-Z\s]{1,}/i,
    /\b(?:email|mail|send\s+to|write\s+to)\s+[A-Z][a-zA-Z\s]{1,}/i,
    
    // More specific patterns
    /\bsend\s+(?:email|mail)\s+to\s+\w+/i,
    /\bemail\s+\w+\s+about/i,
    /\bwrite\s+to\s+\w+/i,
    /\bcontact\s+\w+/i
  ].some(pattern => pattern.test(text));
  
  if (hasExplicitRecipient) {
    return false;
  }
  
  // Check for generic email commands without recipients
  const genericEmailPatterns = [
    /^(?:hey\s+)?(?:email|mail)?\s*(?:draft|write|compose|create|send)\s+(?:a|an|the)?\s*(?:email|mail|message)?\s*(?:about|regarding|for)?\s*[^?]*$/i,
    /^(?:hey\s+)?(?:email|mail)?\s*(?:send|create)\s+(?:a|an|the)?\s*(?:email|mail|message)\s*$/i
  ];
  
  return genericEmailPatterns.some(pattern => pattern.test(cleanText));
}

/**
 * AI-powered comprehensive text analysis for email commands
 * Handles any language, format, or sentence structure
 * @param {string} text - Raw input text from voice/webhook
 * @param {object} user - User object with email and name
 * @param {string} contactsListString - Available contacts for matching
 * @returns {Promise<object>} - Comprehensive analysis result
 */
async function analyzeTextWithAI(text, user, contactsListString = '') {
  try {
    console.log(`[${user.id || user.user_id}] Analyzing text with AI: "${text}"`);
    
    const prompt = `You are an intelligent email assistant that can understand commands in any language and format, especially voice-to-text patterns. Analyze the following text and extract email-related information.

TEXT TO ANALYZE: "${text}"

USER INFO:
- Name: ${user.name || 'User'}
- Email: ${user.email || 'unknown'}

AVAILABLE CONTACTS:
${contactsListString || 'No contacts available'}

VOICE-TO-TEXT EMAIL PATTERNS (HIGHEST PRIORITY):
- "at the rate" = "@" (NEVER treat "rate" as domain name)
- "at rate" = "@", "at d rate" = "@", "at da rate" = "@"
- "dot com/org/net/edu/gov" = ".com/.org/.net/.edu/.gov"  
- "duck dot com" = "duck.com"
- "dove dot com" = "dove.com"
- "invisible wizard 0 0 at the rate email dot com" = "invinciblewizard00@email.com"
- "l Yagami at the rate duck dot com" = "l.yagami@duck.com"
- "john at email dot com" = "john@email.com"
- "user123 at the rate domain dot com" = "user123@domain.com" (NOT user123@rate.com)
- "john dot smith at email dot com" = "john.smith@email.com" (preserve dots in usernames)
- "john_smith at email dot com" = "john_smith@email.com" (preserve underscores)
- "mary-johnson at yahoo dot com" = "mary-johnson@yahoo.com" (preserve hyphens)
- "user at rate email dot com" = "user@email.com" (ignore "rate" as filler word)

EMAIL CONSTRUCTION RULES:
1. USERNAME: Keep ALL words before "at" as username, join with dots if multiple words
2. DOMAIN: Take words after "at" (ignoring "rate", "the rate", "d rate") until "dot"
3. TLD: Everything after "dot" becomes file extension
4. PRESERVE: dots, underscores, hyphens, numbers in usernames
5. IGNORE: filler words like "rate", "the", "d", "da" between "at" and domain name

CRITICAL EMAIL PARSING RULES:
- "at d rate yahoo dot com" = "at yahoo dot com" (remove "d rate")
- "at the rate company dot org" = "at company dot org" (remove "the rate")  
- "at rate business dot net" = "at business dot net" (remove "rate")
- "at d rate service dot gov" = "at service dot gov" (remove "d rate")
- NEVER include "rate" as part of domain name
- ALWAYS skip filler words between "at" and actual domain name

ABSOLUTE PRIORITY RULES FOR RECIPIENT DETECTION:
1. **EMAIL ADDRESS DETECTED** (HIGHEST PRIORITY)
   - If ANY email pattern is found (like "name at the rate domain dot com"), recipient type = "email"
   - Convert to proper email format and use as recipient
   - NEVER use contacts list when email pattern is detected
   - Example: "send to john at email dot com" → recipient: "john@email.com", type: "email"
   - CRITICAL: Ignore contacts even if name matches - use the spoken email address

2. **EXPLICIT SELF-REFERENCE** (SECOND PRIORITY)
   - ONLY if NO email address detected AND text contains "to me", "email me", "send me", "myself"
   - Look for phrases: "send mail to me", "email to me", "send email to me", "email me"
   - recipient type = "self", email = user's email
   - Example: "send email to me about project" → recipient: user, type: "self"
   - CRITICAL: "send mail to me asking Affan" → type: "self" (NOT Affan - Affan is in content)

3. **CONTACT NAME** (THIRD PRIORITY)  
   - ONLY if NO email AND NO "to me" detected
   - Look for names in contacts list
   - recipient type = "contact"
   - Example: "send email to John" → recipient: found contact, type: "contact"

4. **UNCLEAR/MISSING** (LAST RESORT)
   - Only if none of the above apply
   - recipient type = "unknown"

CRITICAL EXAMPLES:
- "send to invisible wizard at email dot com" → EMAIL DETECTED → recipient: invinciblewizard@email.com, type: "email"
- "send email to me asking about John" → SELF DETECTED (contains "to me") → recipient: user, type: "self" 
- "send mail to me asking Affan to send receipt" → SELF DETECTED (contains "to me") → recipient: user, type: "self"
- "Gmail send email to me reminding to call John" → SELF DETECTED (contains "to me") → recipient: user, type: "self"
- "send email to John about meeting" → CONTACT DETECTED (no email, no "to me") → recipient: John from contacts, type: "contact"
- "email person at d rate yahoo dot com" → EMAIL DETECTED → recipient: person@yahoo.com, type: "email" (NOT person@d.com)
- "contact admin at d rate service dot gov" → EMAIL DETECTED → recipient: admin@service.gov, type: "email" (NOT admin@d.gov)
- "send to john.smith123 at the rate company dot org" → EMAIL DETECTED → recipient: john.smith123@company.org, type: "email" (NOT @ratecompany.org)
- "email user_name at rate business dot net" → EMAIL DETECTED → recipient: user_name@business.net, type: "email" (NOT @ratebusiness.net)

TASK: Analyze the text and provide a JSON response with the following structure:

{
  "isEmailCommand": boolean,
  "confidence": number (0-1),
  "language": "detected language code",
  "intent": "send_email|draft_email|no_email|unclear",
  "recipient": {
    "type": "email|self|contact|unknown|none",
    "name": "extracted name or null",
    "email": "PROPERLY FORMATTED EMAIL ADDRESS or null",
    "confidence": number (0-1)
  },
  "subject": "generated subject or null",
  "content": "extracted message content or null",
  "tone": "professional|friendly|formal|brief|casual",
  "requiresClarification": boolean,
  "clarificationNeeded": "recipient|subject|content|none",
  "suggestedActions": ["array of suggested next steps"],
  "reasoning": "explanation of analysis including which priority rule was used"
}

CRITICAL INSTRUCTIONS:
1. **ALWAYS CHECK FOR EMAIL PATTERNS FIRST** - Look for "name at rate domain dot com" patterns
2. **Convert voice patterns to proper emails**: "invisible wizard 0 0 at rate email dot com" → "invinciblewizard00@email.com"
3. **Only use "self" if NO email detected AND explicit "to me" found**
4. **Only use "contact" if NO email AND NO "to me" detected**
5. **Include which priority rule was used in your reasoning**
6. **Handle mixed languages, informal speech, and voice-to-text artifacts**
7. **Be very specific about email address detection - don't miss voice-to-text patterns**
8. **CRITICAL: If text contains "to me" anywhere, recipient type MUST be "self" unless email pattern found**

Respond ONLY with valid JSON:`;

    const response = await openaiClient.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [
        {
          role: 'system',
          content: 'You are an expert multilingual email assistant. You understand voice commands in any language and can extract email-related information from natural speech patterns, even with errors or mixed languages. Always respond with valid JSON only.'
        },
        {
          role: 'user',
          content: prompt
        }
      ],
      max_tokens: 800,
      temperature: 0.3, // Lower temperature for more consistent parsing
    });

    // Clean the response to handle markdown-wrapped JSON
    let cleanResponse = response.choices[0].message.content.trim();
    
    // Remove markdown code block wrappers if present
    if (cleanResponse.startsWith('```json') || cleanResponse.startsWith('```')) {
      cleanResponse = cleanResponse.replace(/^```(?:json)?\s*/, '').replace(/```\s*$/, '').trim();
    }
    
    // Remove any leading/trailing whitespace and quotes
    cleanResponse = cleanResponse.replace(/^["']|["']$/g, '');

    const aiAnalysis = JSON.parse(cleanResponse);
    console.log(`[${user.id || user.user_id}] AI Analysis result:`, aiAnalysis);
    
    return aiAnalysis;

  } catch (error) {
    console.error(`[${user.id || user.user_id}] Error in AI text analysis:`, error);
    
    // Fallback to basic analysis if AI fails
    return {
      isEmailCommand: EMAIL_COMMAND_PATTERN.test(text),
      confidence: 0.5,
      language: "unknown",
      intent: EMAIL_COMMAND_PATTERN.test(text) ? "send_email" : "unclear",
      recipient: {
        type: "unknown",
        name: null,
        email: null,
        confidence: 0.3
      },
      subject: "Email Communication",
      content: text,
      tone: "professional",
      requiresClarification: true,
      clarificationNeeded: "recipient",
      suggestedActions: ["Ask for recipient clarification"],
      reasoning: "AI analysis failed, using fallback"
    };
  }
}

module.exports = {
  processEmailCommand,
  analyzeEmailWithTone,
  localExtractNameFromText,
  generateEmailContentWithOpenAI,
  findSimilarContacts,
  calculateSimpleDistance,
  hasNoRecipientMentioned,
  checkPhoneticSimilarity,
  analyzeTextWithAI
}; 
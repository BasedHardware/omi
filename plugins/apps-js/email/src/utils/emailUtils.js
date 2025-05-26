const { google } = require('googleapis');
const { getGoogleClient } = require('./googleAuth');
const User = require('../models/User');
const { Buffer } = require('buffer');
const { storeEmailContact } = require('./contactUtils');
require('dotenv').config();

// Added imports for getEmailContacts
const { createClient } = require('@supabase/supabase-js');

// Initialize Supabase client (assuming environment variables are accessible)
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;

let supabase;
if (supabaseUrl && supabaseKey) {
  supabase = createClient(supabaseUrl, supabaseKey, {
    auth: {
      persistSession: false,
    }
  });
} else {
  console.error('Missing Supabase credentials for emailUtils.js. Please check your .env file.');
  // Potentially throw an error or handle appropriately if Supabase is critical for this module
}

// Configuration constant for getEmailContacts
const EMAIL_CACHE_EXPIRY = 60 * 60; // 1 hour in seconds

// Initialize OpenAI client
const OpenAI = require('openai');
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

// Helper function to create email raw content
async function createEmail({ to, from, subject, text }) {
  const emailLines = [
    `From: ${from}`,
    `To: ${to}`,
    `Subject: ${subject}`,
    '',
    text
  ];

  const emailContent = emailLines.join('\r\n');
  const base64EncodedEmail = Buffer.from(emailContent).toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

  return base64EncodedEmail;
}

function calculateNameSimilarity(name1, name2) {
  const n1 = name1.toLowerCase().replace(/[^a-z0-9]/g, '');
  const n2 = name2.toLowerCase().replace(/[^a-z0-9]/g, '');
  return n2.includes(n1) || n1.includes(n2);
}

// Function to detect and remove duplicated content in email bodies
function removeDuplicatedContent(content) {
  if (!content) return content;
  
  try {
    // Split the content into lines for analysis
    const lines = content.split('\n');
    const contentLength = lines.length;
    
    // If content is too short, just return it
    if (contentLength < 10) return content;
    
    // Check for exact duplication (the most common case)
    const halfLength = Math.floor(contentLength / 2);
    
    // Check if the first half matches the second half
    let isDuplicated = true;
    for (let i = 0; i < halfLength; i++) {
      if (lines[i] !== lines[i + halfLength]) {
        isDuplicated = false;
        break;
      }
    }
    
    // If exact duplication is found, return just the first half
    if (isDuplicated) {
      return lines.slice(0, halfLength).join('\n');
    }
    
    // Check for partial duplication or similar content blocks
    // This handles cases where there might be slight differences
    // or where the duplication isn't exactly half
    
    // Find the longest signature line that might indicate the end of a content block
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
          const contentBeforeSignature = lines.slice(0, i + 3).join('\n');
          const contentAfterSignature = lines.slice(i + 3).join('\n');
          
          // If the content after the signature is similar to the beginning,
          // it's likely a duplication
          if (contentAfterSignature.length > 0 && 
              contentBeforeSignature.includes(contentAfterSignature.substring(0, 20)) ||
              contentAfterSignature.includes(contentBeforeSignature.substring(0, 20))) {
            return contentBeforeSignature;
          }
        }
      }
    }
    
    // If no duplication is detected, return the original content
    return content;
  } catch (error) {
    console.error('Error removing duplicated content:', error);
    return content; // Return original content if removal fails
  }
}

async function draftEmail(to, subject, content, user, options = {}) {
  try {
    console.log('Drafting email to:', to);

    if (!user) {
      throw new Error('User object is required');
    }

    const normalizedUser = {
      ...user,
      user_id: user.id || user.user_id,
      _id: user.id || user._id || user.user_id,
      name: user.name || user.email?.split('@')[0],
      email: user.email
    };

    if (!normalizedUser.user_id && !normalizedUser._id) {
      console.error('Invalid user object:', normalizedUser);
      throw new Error('Invalid user object: missing user_id or _id');
    }

    let recipientEmail = to;
    if (typeof recipientEmail === 'object' && recipientEmail.email) {
      recipientEmail = recipientEmail.email;
    }

    if (!recipientEmail || !recipientEmail.includes('@')) {
      throw new Error('Invalid email address: ' + recipientEmail);
    }

    let auth;
    if (normalizedUser.token) {
      // Use the same authentication method as email fetching
      auth = await getGoogleClient(normalizedUser);
    } else if (normalizedUser._id) {
      console.log('Using MongoDB user for authentication');
      const User = require('../models/User');
      const mongoUser = await User.findById(normalizedUser._id);
      if (!mongoUser) {
        throw new Error('User not found in MongoDB');
      }
      auth = await getGoogleClient(mongoUser);
    } else {
      throw new Error('Invalid user object: missing user_id or _id');
    }

    const { google } = require('googleapis');
    const gmail = google.gmail({ version: 'v1', auth });

    const userProfile = await gmail.users.getProfile({
      userId: 'me'
    });

    const senderEmail = userProfile.data.emailAddress;
    const senderName = normalizedUser.name || senderEmail.split('@')[0];

    // --- Start: Enhanced Content Processing ---
    let emailContent = content || 'No content provided';

    // 1. Normalize all possible Unicode line endings to LF only
    emailContent = emailContent.replace(/\r\n|\r|\u0085|\u2028|\u2029/g, '\n');

    // 2. Collapse multiple consecutive newlines into a maximum of two (for explicit paragraph breaks)
    emailContent = emailContent.replace(/\n{3,}/g, '\n\n');

    // 3. Remove single newlines *within* what appears to be a logical paragraph, replacing with a space.
    // This is crucial to prevent unintended hard wraps in plain text.
    emailContent = emailContent.split('\n\n').map(paragraph =>
      paragraph.replace(/\n/g, ' ') // Replace single newlines with space
               .replace(/ +/g, ' ')  // Collapse multiple spaces within the paragraph
               .trim()               // Trim whitespace from paragraph ends
    ).join('\n\n'); // Re-join paragraphs with double newlines

    // 4. Trim leading/trailing whitespace from the whole content
    emailContent = emailContent.trim();
    // --- End: Enhanced Content Processing ---

    // Apply email template if specified
    if (options.template) {
      try {
        emailContent = applyEmailTemplate(options.template, {
          content: emailContent,
          senderName,
          senderEmail,
          recipientEmail,
          subject
        });
      } catch (templateError) {
        console.error('Error applying email template:', templateError);
      }
    }

    // Always assume we want to send a multipart email with HTML and plain text alternatives
    // This provides the best compatibility across clients.
    const isActuallyHtmlInput = emailContent.includes('<html>') ||
                                emailContent.includes('<body>') ||
                                emailContent.includes('<div>') ||
                                emailContent.includes('<p>') ||
                                emailContent.includes('<li>') ||
                                emailContent.includes('<br>');

    let plainTextVersion;
    let htmlVersion;

    if (isActuallyHtmlInput) {
        // If the input already looks like HTML, use it directly for HTML version.
        htmlVersion = emailContent;
        // Generate plain text by stripping HTML
        try {
            const { convert } = require('html-to-text'); // npm install html-to-text
            plainTextVersion = convert(emailContent, {
                wordwrap: 78, // Good for plain text emails
                selectors: [{ selector: 'a', options: { ignoreHref: true } }, { selector: 'img', format: 'skip' }],
            });
            // Final cleanup for plain text
            plainTextVersion = plainTextVersion.replace(/\r\n|\r|\u0085|\u2028|\u2029/g, '\n')
                                               .replace(/\n{3,}/g, '\n\n')
                                               .split('\n\n').map(p => p.replace(/\n/g, ' ').trim()).join('\n\n')
                                               .trim();
        } catch (e) {
            console.warn('html-to-text conversion failed, falling back to regex strip:', e);
            plainTextVersion = emailContent.replace(/<[^>]*>?/gm, '')
                                           .replace(/&nbsp;/g, ' ')
                                           .replace(/ +/g, ' ')
                                           .replace(/\n{3,}/g, '\n\n')
                                           .trim();
            plainTextVersion = plainTextVersion.split('\n\n').map(p => p.replace(/\n/g, ' ').trim()).join('\n\n');
        }

    } else {
        // If the input is plain text (after our sanitization), generate both versions:
        plainTextVersion = emailContent; // The sanitized emailContent is already ideal for plain text

        // Convert plain text to HTML paragraphs for proper rendering
        htmlVersion = `<p>${emailContent.split('\n\n').map(paragraph =>
            paragraph.replace(/\n/g, '<br>') // Convert single newlines to <br> for soft wraps
        ).join('</p><p>')}</p>`; // Join paragraphs with closing/opening <p> tags

        // Ensure the HTML version is valid even if it ends up empty
        if (htmlVersion === '<p></p>') {
            htmlVersion = ''; // Or some other fallback HTML structure
        }
    }

    const boundary = `boundary_${Date.now().toString(16)}`;

    // Build the raw email string for multipart/alternative
    const emailRaw = [
      `MIME-Version: 1.0`,
      `Subject: ${subject}`,
      `To: ${recipientEmail}`,
      `From: ${senderName} <${senderEmail}>`,
      `Content-Type: multipart/alternative; boundary="${boundary}"`,
      ``, // Empty line separating headers from body parts

      `--${boundary}`,
      `Content-Type: text/plain; charset="UTF-8"`,
      `Content-Transfer-Encoding: quoted-printable`,
      ``, // Empty line separating headers from content
      `${plainTextVersion.replace(/[\u0080-\uFFFF]/g, char => '=' + char.charCodeAt(0).toString(16).toUpperCase())}`,
      ``, // Empty line separating content from next boundary

      `--${boundary}`,
      `Content-Type: text/html; charset="UTF-8"`,
      `Content-Transfer-Encoding: quoted-printable`,
      ``, // Empty line separating headers from content
      `${htmlVersion.replace(/[\u0080-\uFFFF]/g, char => '=' + char.charCodeAt(0).toString(16).toUpperCase())}`,
      ``, // Empty line separating content from next boundary

      `--${boundary}--` // Final boundary
    ].join('\r\n');

    // Debugging output of the final raw email before encoding
    console.log('--- Debug: Final Raw Email Before Base64 Encoding ---');
    console.log(emailRaw);
    console.log('--- End Debug ---');

    const base64EncodedEmail = Buffer.from(emailRaw).toString('base64')
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');

    console.log('--- Debug: base64EncodedEmail ---');
    console.log(base64EncodedEmail);
    console.log('--- End Debug ---');

    const response = await gmail.users.messages.send({
      userId: 'me',
      requestBody: {
        raw: base64EncodedEmail
      }
    });

    console.log('Email sent:', response.data.id);

    try {
      const recipientName = recipientEmail.includes('<') ?
        recipientEmail.split('<')[0].trim() :
        recipientEmail.split('@')[0].replace(/[._-]/g, ' ');

      await storeEmailContact(
        normalizedUser.user_id,
        recipientEmail,
        recipientName
      );

    } catch (storeError) {
      console.error('Error storing email contact:', storeError);
    }

    return {
      success: true,
      messageId: response.data.id,
      threadId: response.data.threadId
    };
  } catch (error) {
    console.error('Error sending email:', error);
    
    // Handle authentication errors specifically
    if (error.status === 401 || error.code === 401 || error.message?.includes('Invalid Credentials')) {
      const authError = new Error('AUTHENTICATION_REQUIRED');
      authError.details = {
        message: 'Google OAuth authentication has expired and refresh failed. Please re-authenticate.',
        action: 'Visit /api/auth/login/{your_user_id} to re-authenticate with Google',
        error_type: 'oauth_refresh_failed',
        original_error: error.message
      };
      throw authError;
    }
    
    // Handle reverification errors
    if (error.message === 'REVERIFICATION_REQUIRED') {
      const reAuthError = new Error('REVERIFICATION_REQUIRED');
      reAuthError.details = {
        message: 'Google OAuth requires reverification (6 months since last authentication).',
        action: 'Visit /api/auth/login/{your_user_id} to re-authenticate with Google',
        error_type: 'oauth_reverification',
        original_error: error.message
      };
      throw reAuthError;
    }
    
    throw error;
  }
}

// Helper function to apply email templates
function applyEmailTemplate(template, data) {
  // Basic email templates
  const templates = {
    'formal': `{{content}}`,
    'friendly': `{{content}}`,
    'professional': `{{content}}`,
    'brief': `{{content}}`
  };

  // Get template string or use the template parameter as a custom template
  const templateString = templates[template] || template;
  
  // Replace placeholders with actual data
  return templateString.replace(/\{\{(\w+)\}\}/g, (match, key) => {
    return data[key] || match;
  });
}

async function logUserEmailContacts(user) {
  const GMAIL_API_TIMEOUT = 25000; // Increased to 25 seconds
  const MAX_MESSAGES_TO_SCAN = 200; // Scan fewer messages for faster initial load

  return Promise.race([
    (async () => {
      try {
        const auth = await getGoogleClient(user);
        const gmail = google.gmail({ version: 'v1', auth });

        console.log(`[${user.user_id || user._id}] Fetching ${MAX_MESSAGES_TO_SCAN} messages from SENT and INBOX for contacts.`);
        const [sentResponse, inboxResponse] = await Promise.all([
          gmail.users.messages.list({
            userId: 'me',
            labelIds: ['SENT'],
            maxResults: MAX_MESSAGES_TO_SCAN 
          }),
          gmail.users.messages.list({
            userId: 'me',
            labelIds: ['INBOX'],
            maxResults: MAX_MESSAGES_TO_SCAN
          })
        ]);

        const messages = [
          ...(sentResponse.data.messages || []),
          ...(inboxResponse.data.messages || [])
        ];

        if (messages.length === 0) {
          console.log(`[${user.user_id || user._id}] No messages found to scan for contacts.`);
          return [];
        }
        
        console.log(`[${user.user_id || user._id}] Found ${messages.length} messages to scan.`);

        const contactsToUpsert = new Map(); // Use a Map to store email -> {name, context, count, first_used, last_used}

        const batchSize = 10;
        for (let i = 0; i < messages.length; i += batchSize) {
          const batch = messages.slice(i, i + batchSize);
          const messageDetailsPromises = batch.map(message =>
            gmail.users.messages.get({
              userId: 'me',
              id: message.id,
              format: 'metadata',
              metadataHeaders: ['From', 'To', 'Cc'] // Removed Bcc for minor speed up, can be added back if needed
            }).catch(err => {
              console.warn(`[${user.user_id || user._id}] Error fetching details for message ${message.id}:`, err.message);
              return null; // Continue if one message fails
            })
          );
          
          const messageDetailsResults = await Promise.all(messageDetailsPromises);

          messageDetailsResults.forEach(details => {
            if (!details || !details.data || !details.data.payload) return;
            const headers = details.data.payload.headers;
            ['From', 'To', 'Cc'].forEach(headerName => {
              const header = headers.find(h => h.name === headerName);
              if (header?.value) {
                const emailRegex = /([\w.-]+@[\w.-]+\.[\w.-]+)/gi; // Simpler regex for email
                const nameEmailRegex = /(?:\"?([^<\"]+)\"?\\s*)?<([\w.-]+@[\w.-]+\.[\w.-]+)>/g; // Extracts name and email

                let match;
                while((match = nameEmailRegex.exec(header.value)) !== null) {
                    const email = match[2].toLowerCase();
                    const name = match[1] ? match[1].replace(/\"/g, '').trim() : email.split('@')[0].replace(/[._-]/g, ' ');

                    if (email && email !== user.email && email !== (user.profileData && user.profileData.emailAddress) ) { // Ensure it's not user's own email
                        if (!contactsToUpsert.has(email)) {
                            contactsToUpsert.set(email, { 
                                name: name, 
                                email: email,
                                context: email.split('@')[1], // Domain as context
                                usage_count: 0, // Will be incremented correctly
                                first_used: new Date().toISOString(), 
                                last_used: new Date().toISOString()
                            });
                        }
                        const contact = contactsToUpsert.get(email);
                        contact.usage_count = (contact.usage_count || 0) + 1; // Should be handled by DB upsert better
                        contact.last_used = new Date().toISOString(); 
                        if (!contact.name && name) contact.name = name; // Update name if initially missing
                    }
                }
                // Fallback for emails not in "Name <email>" format
                const simpleEmailMatches = header.value.match(emailRegex);
                if (simpleEmailMatches) {
                    simpleEmailMatches.forEach(emailOnly => {
                        const email = emailOnly.toLowerCase();
                         if (email && email !== user.email && email !== (user.profileData && user.profileData.emailAddress) && !contactsToUpsert.has(email)) {
                             contactsToUpsert.set(email, {
                                name: email.split('@')[0].replace(/[._-]/g, ' '),
                                email: email,
                                context: email.split('@')[1],
                                usage_count: 1,
                                first_used: new Date().toISOString(),
                                last_used: new Date().toISOString()
                             });
                         } else if (contactsToUpsert.has(email)) {
                            const contact = contactsToUpsert.get(email);
                            contact.usage_count = (contact.usage_count || 0) + 1;
                            contact.last_used = new Date().toISOString();
                         }
                    });
                }
              }
            });
          });
          if (i + batchSize < messages.length) {
            await new Promise(resolve => setTimeout(resolve, 200)); // Slightly increased delay
          }
        }
        
        const finalContacts = Array.from(contactsToUpsert.values());
        console.log(`[${user.user_id || user._id}] Processed ${finalContacts.length} unique contacts from Gmail.`);

        if (finalContacts.length > 0 && supabase) {
            const recordsToUpsert = finalContacts.map(c => ({
                user_id: user.user_id,
                email: c.email,
                name: c.name,
                context: c.context,
                // Supabase will handle incrementing usage_count, and setting first_used/last_used on conflict
            }));

            // Upsert contacts into Supabase
            // `onConflict` will update last_used and increment usage_count. `ignoreDuplicates: false` is default.
            // A custom RPC might be better for atomic increment of usage_count and conditional update of name.
            // For now, we'll insert and rely on application logic or a simpler upsert.
            // Let's simplify the upsert: insert new ones, update existing ones in a separate step or rely on getEmailContacts to merge.
            // The primary goal here is to get the list. Storing/updating usage can be refined.
            
            // Simplified: just get the list. The calling function getEmailContacts will handle caching and DB storage.
        }
        
        return finalContacts.map(c => ({ email: c.email, name: c.name, context: c.context })); // Return a simpler array for caching

      } catch (error) {
        console.error(`[${user.user_id || user._id}] Error in logUserEmailContacts main logic:`, error.message);
        if (error.code === 401 || (error.errors && error.errors.some(e => e.reason === 'authError'))) {
            console.error(`[${user.user_id || user._id}] Authentication error while fetching contacts. User might need to re-auth.`);
            // Propagate a specific error or empty array
            throw new Error('Gmail authentication failed while fetching contacts.');
        }
        return []; // Return empty on other errors
      }
    })(),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`logUserEmailContacts timed out after ${GMAIL_API_TIMEOUT}ms`)), GMAIL_API_TIMEOUT)
    )
  ]);
}

async function analyzeEmailIntent(text, availableEmails = []) {
  try {
    // First check if this is a start email/mail command
    const startMatch = text.match(/\b(start|send|write|compose)\s+(email|mail|message)\s+to\s+([^\n.]+)/i);
    
    if (startMatch) {
      const recipientName = startMatch[3].toLowerCase().trim();
      
      // Find matching emails using fuzzy matching
      const matches = availableEmails.map(email => {
        const emailLower = email.toLowerCase();
        const namePart = emailLower.split('@')[0];
        const domain = emailLower.split('@')[1];
        
        // Calculate match score
        let score = 0;
        if (emailLower.includes(recipientName)) score += 0.5;
        if (namePart === recipientName) score += 1;
        if (emailLower.startsWith(`${recipientName}@`)) score += 0.8;
        
        return {
          email,
          name: namePart,
          score
        };
      }).filter(match => match.score > 0)
        .sort((a, b) => b.score - a.score);

      // If we have matches, return them
      if (matches.length > 0) {
        return {
          intent: 'show_matches',
          confidence: matches[0].score,
          analysis: {
            recipient: recipientName,
            subject: text.replace(startMatch[0], '').trim() || 'Email from OMI',
            content: text,
            urgency: determineUrgency(text),
            matched_emails: matches.map(m => m.email),
            exact_match: matches[0].score > 0.9 ? matches[0].email : null,
            matches: matches.map(m => ({
              email: m.email,
              name: m.name,
              confidence: m.score
            }))
          }
        };
      }
    }

    // If no matches found or not a start command, analyze with OpenAI
    const prompt = `Analyze this email-related voice command and determine the intent and details.
    Command: "${text}"
    
    Return a JSON object in this format (and ONLY this format):
    {
      "intent": "initiate_email",
      "recipient": "name or identifier of intended recipient",
      "subject": "inferred email subject",
      "content": "main content or message to send",
      "urgency": "normal|urgent|low",
      "tone": "professional|casual|friendly"
    }`;

    const response = await openai.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [
        { role: 'user', content: prompt }
      ],
      max_tokens: 200,
      temperature: 0.1,
    });

    try {
      const cleanedResponse = response.data.choices[0].message.content.trim()
        .replace(/[\u0000-\u001F\u007F-\u009F]/g, '');
      const analysis = JSON.parse(cleanedResponse);
      
      return {
        intent: analysis.intent,
        confidence: 0.9,
        analysis: {
          recipient: analysis.recipient,
          subject: analysis.subject,
          content: analysis.content,
          urgency: analysis.urgency,
          tone: analysis.tone,
          matched_emails: [],
          matches: []
        }
      };
    } catch (error) {
      console.error('Failed to parse email intent analysis:', error);
      return null;
    }
  } catch (error) {
    console.error('Error analyzing email intent:', error);
    return null;
  }
}

function determineUrgency(text) {
  const urgentPatterns = /\b(urgent|asap|emergency|immediate|right now|quickly)\b/i;
  const lowPriorityPatterns = /\b(when you can|no rush|low priority|whenever)\b/i;
  
  if (urgentPatterns.test(text)) return 'urgent';
  if (lowPriorityPatterns.test(text)) return 'low';
  return 'normal';
}

// MOVED AND ADAPTED FUNCTION
async function getEmailContacts(user) {
  if (!user || !user.token || !user.email || !user.id) { // Added user.id check for safety
    console.error('[GET_CONTACTS] Invalid user object provided. Missing id, email, or token.', user);
    return [];
  }

  try {
    // Try to get from Supabase first
    // This part remains, assuming the DB can have contacts from various sources or prior syncs.
    // If strict "only sent via this function call" is needed, this DB check might need a 'source' filter.
    if (supabase) { // Check if supabase is initialized
        const { data: dbContacts, error: dbError } = await supabase
        .from('email_contacts')
        .select('email, name, usage_count, last_used')
        .eq('user_id', user.id)
        .order('usage_count', { ascending: false });

        if (!dbError && dbContacts && dbContacts.length > 0) {
        console.log(`[GET_CONTACTS] Found ${dbContacts.length} contacts in Supabase for user ${user.id}. Returning these.`);
        return dbContacts;
        }
        if (dbError) {
            console.warn(`[GET_CONTACTS] Error querying Supabase for contacts (user ${user.id}):`, dbError.message);
        }
    } else {
        console.warn("[GET_CONTACTS] Supabase client not initialized in emailUtils. Cannot check DB for contacts.");
    }


    // If no contacts in database (or Supabase check failed/skipped), fetch from Gmail SENT items
    console.log(`[GET_CONTACTS] No suitable contacts in DB for user ${user.id}. Fetching from Gmail SENT items.`);
    
    // Use the same getGoogleClient function for consistency
    const auth = await getGoogleClient(user);
    const gmail = google.gmail({ version: 'v1', auth });
    
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
    const queryDate = Math.floor(sixMonthsAgo.getTime() / 1000);
    
    console.log(`[GET_CONTACTS] Fetching SENT emails for user ${user.email} (ID: ${user.id}) after ${sixMonthsAgo.toISOString()}`);

    const response = await gmail.users.messages.list({
      userId: 'me',
      q: `in:sent after:${queryDate}`, // MODIFIED: Filter for 'in:sent'
      maxResults: 250 // Fetch up to 250 recent sent messages
    });

    if (!response.data.messages || response.data.messages.length === 0) {
      console.log(`[GET_CONTACTS] No SENT messages found in Gmail (last 6 months) for user ${user.email} (ID: ${user.id})`);
      return [];
    }

    console.log(`[GET_CONTACTS] Found ${response.data.messages.length} SENT Gmail messages to process for user ${user.email} (ID: ${user.id})`);
    const contactsMap = new Map(); // email_lowercase -> { name, email, first_occurrence, last_occurrence, count }

    for (const message of response.data.messages) {
      try {
        const messageDetails = await gmail.users.messages.get({
          userId: 'me',
          id: message.id,
          format: 'metadata',
          metadataHeaders: ['To', 'Cc', 'Bcc', 'Date'] // Focus on recipient headers and Date
        });

        const headers = messageDetails.data.payload.headers;
        const dateHeader = headers.find(h => h.name === 'Date' || h.name === 'date');
        const messageDate = dateHeader ? new Date(dateHeader.value).toISOString() : new Date().toISOString();

        ['To', 'Cc', 'Bcc'].forEach(headerName => { // MODIFIED: Iterate recipient headers
          const header = headers.find(h => h.name === headerName);
          if (header && header.value) {
            const recipients = header.value.split(',');
            recipients.forEach(recipientEntry => {
              const nameEmailRegex = /"?([^"<]+)"?\s*<?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})>?/;
              const match = recipientEntry.match(nameEmailRegex);

              if (match) {
                let name = match[1] ? match[1].trim().replace(/^"|"$/g, '') : '';
                const email = match[2];
                
                if (email && email.toLowerCase() !== user.email.toLowerCase()) { // Exclude user's own email
                  const normalizedEmail = email.toLowerCase();
                  
                  if (!name) { // If no name part, derive from email local part
                    name = normalizedEmail.split('@')[0].replace(/[._\-+]/g, ' ').replace(/\s+/g, ' ').trim();
                    name = name.split(' ').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
                  }
                  
                  let contactData = contactsMap.get(normalizedEmail);
                  if (!contactData) {
                    contactData = {
                      name: name,
                      email: email, // Store original cased email
                      first_used: messageDate, // Renamed for clarity
                      last_used: messageDate,  // Renamed for clarity
                      usage_count: 0           // Renamed for clarity
                    };
                  }

                  contactData.usage_count += 1;
                  if (new Date(messageDate) < new Date(contactData.first_used)) {
                    contactData.first_used = messageDate;
                  }
                  if (new Date(messageDate) > new Date(contactData.last_used)) {
                    contactData.last_used = messageDate;
                  }
                  // Update name if new one is better (longer or different from derived default)
                  if (name && name.length > contactData.name.length && name.toLowerCase() !== normalizedEmail.split('@')[0]) {
                     contactData.name = name;
                  } else if (name && contactData.name.toLowerCase().startsWith(normalizedEmail.split('@')[0]) && name.toLowerCase() !== normalizedEmail.split('@')[0]){
                     // Prefer a parsed name if the current one is just a derived one
                     contactData.name = name;
                  }
                  contactsMap.set(normalizedEmail, contactData);
                }
              }
            });
          }
        });
      } catch (msgError) {
        console.error(`[GET_CONTACTS] Error processing message ID ${message.id} for user ${user.email} (ID: ${user.id}):`, msgError.message);
      }
    }

    const derivedContacts = Array.from(contactsMap.values());
    console.log(`[GET_CONTACTS] Extracted ${derivedContacts.length} unique contacts from SENT Gmail for user ${user.email} (ID: ${user.id})`);

    // Save/Update these SENT-derived contacts to Supabase
    if (derivedContacts.length > 0 && supabase) {
      const contactsToUpsert = derivedContacts.map(c => ({
        user_id: user.id,
        email: c.email.toLowerCase(), // Ensure email is stored in lowercase for consistent matching
        name: c.name,
        usage_count: c.usage_count,
        first_used: c.first_used,
        last_used: c.last_used
        // Consider adding a 'source' field like 'gmail_sent_fetch'
      }));

      try {
        const { error: upsertError } = await supabase.from('email_contacts').upsert(
          contactsToUpsert,
          { 
            onConflict: 'user_id,email', // Assumes (user_id, email) is your unique constraint
            // Decide how to handle conflicts, e.g., update name, sum usage_count, update last_used
            // For simplicity, this will update matching rows or insert new ones.
            // A more sophisticated upsert might require an RPC for atomic increments if usage_count is critical.
          }
        );
        if (upsertError) {
          console.error(`[GET_CONTACTS] Error upserting SENT-derived contacts to Supabase (user ${user.id}):`, upsertError.message);
        } else {
          console.log(`[GET_CONTACTS] Successfully upserted ${contactsToUpsert.length} SENT-derived contacts to Supabase for user ${user.id}`);
        }
      } catch (e) {
          console.error(`[GET_CONTACTS] Exception during Supabase upsert for SENT-derived contacts (user ${user.id}):`, e);
      }
    }
    return derivedContacts;

  } catch (error) {
    console.error(`[GET_CONTACTS] General error fetching contacts for user ${user.email} (ID: ${user.id}):`, error.message);
    if (error.code === 401 || (error.errors && error.errors.some(e => e.reason === 'invalidCredentials' || e.reason === 'authError')) || error.message.toLowerCase().includes('token has been expired or revoked')) {
      console.warn(`[GET_CONTACTS] Gmail token potentially invalid for user ${user.email}. They may need to re-authenticate.`);
    }
    return [];
  }
}

module.exports = {
  createEmail,
  draftEmail,
  applyEmailTemplate,
  logUserEmailContacts,
  analyzeEmailIntent,
  getEmailContacts,
  removeDuplicatedContent,
}; 
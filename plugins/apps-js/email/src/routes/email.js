const express = require('express');
const { catchAsync, ErrorFactory, withTimeout } = require('../utils/errorHandler');
const EmailService = require('../services/email/emailService');
const auth = require('../middleware/auth');
const { getGoogleClient } = require('../utils/googleAuth');
const { google } = require('googleapis');
const User = require('../models/User');
const { enhancedEmailSearch } = require('../models/enhancedEmailSearch');
const webhookController = require('../controllers/webhookController');
const router = express.Router();
const emailService = new EmailService({
  apiKey: process.env.OPENAI_API_KEY,
  model: 'command',
  maxTokens: 500,
  temperature: 0.7,
  timeout: 8000,
  retries: 3
});



// Webhook endpoint
router.post('/webhook', webhookController.handleWebhook);

/**
 * @route POST /api/email/draft
 * @desc Generate and draft an email
 * @access Private
 */
router.post('/draft', catchAsync(async (req, res) => {
  const { 
    recipientEmail,
    recipientName,
    subject,
    content,
    userId,
    userRequest,
    tone = 'professional',
    format = 'text'
  } = req.body;
  
  if (!recipientEmail) {
    throw ErrorFactory.badRequest('Recipient email is required', 'missing_parameter');
  }
  
  if (!userId) {
    throw ErrorFactory.badRequest('User ID is required', 'missing_parameter');
  }
  
  // Either content or userRequest must be provided
  if (!content && !userRequest) {
    throw ErrorFactory.badRequest('Either content or userRequest is required', 'missing_parameter');
  }
  
  // Get authenticated user
  const getAuthenticatedUser = req.app.locals.getAuthenticatedUser;
  
  if (!getAuthenticatedUser) {
    throw ErrorFactory.internal('Email service functions not available');
  }
  
  const user = await withTimeout(
    getAuthenticatedUser(userId),
    5000,
    'User authentication timed out'
  );
  
  let emailDraft;
  
  if (content) {
    // Use provided content
    emailDraft = await emailService.draftEmail(
      recipientEmail,
      subject || 'Message from OmiSend',
      content,
      user,
      {
        recipientName,
        template: emailService._determineTemplateFromTone(tone),
        format
      }
    );
  } else {
    // Generate content based on user request
    emailDraft = await emailService.generateAndDraftEmail({
      recipient: {
        name: recipientName || emailService._extractNameFromEmail(recipientEmail),
        email: recipientEmail
      },
      user,
      userRequest,
      subject,
      tone,
      format
    });
  }
  
  res.status(200).json({
    status: 'success',
    data: emailDraft
  });
}));

/**
 * @route POST /api/email/send
 * @desc Send a drafted email
 * @access Private
 */
router.post('/send', catchAsync(async (req, res) => {
  const { 
    recipientEmail,
    subject,
    content,
    userId,
    format = 'text'
  } = req.body;
  
  if (!recipientEmail || !subject || !content || !userId) {
    throw ErrorFactory.badRequest('Recipient email, subject, content, and userId are required', 'missing_parameter');
  }
  
  // Get authenticated user and send function
  const getAuthenticatedUser = req.app.locals.getAuthenticatedUser;
  const sendEmail = req.app.locals.sendEmail;
  
  if (!getAuthenticatedUser || !sendEmail) {
    throw ErrorFactory.internal('Email service functions not available');
  }
  
  // Get authenticated user
  const user = await withTimeout(
    getAuthenticatedUser(userId),
    5000,
    'User authentication timed out'
  );
  
  // Send the email
  const result = await withTimeout(
    sendEmail(recipientEmail, subject, content, user, { format }),
    10000,
    'Email sending timed out'
  );
  
  res.status(200).json({
    status: 'success',
    message: 'Email sent successfully',
    data: result
  });
}));

/**
 * @route GET /api/email/metrics
 * @desc Get email service metrics
 * @access Private (Admin)
 */
router.get('/metrics', catchAsync(async (req, res) => {
  // Simple admin authentication
  const { authorization } = req.headers;
  
  if (!authorization || authorization !== `Bearer ${process.env.ADMIN_API_KEY}`) {
    throw ErrorFactory.unauthorized('Admin access required');
  }
  
  res.status(200).json({
    status: 'success',
    data: {
      metrics: emailService.metrics,
      uptime: process.uptime(),
      timestamp: new Date().toISOString()
    }
  });
}));

// Get emails from Gmail
router.get('/gmail/messages', auth, async (req, res) => {
  try {
    const { q = '', maxResults = 20, pageToken } = req.query;
    
    // Get the user to access their tokens
    const user = await User.findById(req.user.id);
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Get authenticated Gmail client
    const auth = await getGoogleClient(user);
    const gmail = google.gmail({ version: 'v1', auth });

    // List messages with optional query
    const response = await gmail.users.messages.list({
      userId: 'me',
      q: q,
      maxResults: parseInt(maxResults),
      pageToken: pageToken
    });

    // Get detailed information for each message
    const messages = await Promise.all(
      response.data.messages.map(async (message) => {
        const details = await gmail.users.messages.get({
          userId: 'me',
          id: message.id,
          format: 'full'
        });
        
        // Extract headers
        const headers = details.data.payload.headers;
        const subject = headers.find(h => h.name === 'Subject')?.value || '';
        const from = headers.find(h => h.name === 'From')?.value || '';
        const to = headers.find(h => h.name === 'To')?.value || '';
        const date = headers.find(h => h.name === 'Date')?.value || '';

        // Extract body
        let body = '';
        if (details.data.payload.parts) {
          // Handle multipart messages
          const textPart = details.data.payload.parts.find(
            part => part.mimeType === 'text/plain'
          );
          if (textPart && textPart.body.data) {
            body = Buffer.from(textPart.body.data, 'base64').toString();
          }
        } else if (details.data.payload.body.data) {
          // Handle single part messages
          body = Buffer.from(details.data.payload.body.data, 'base64').toString();
        }

        return {
          id: message.id,
          threadId: message.threadId,
          subject,
          from,
          to,
          date,
          body,
          snippet: details.data.snippet,
          labelIds: details.data.labelIds
        };
      })
    );

    res.json({
      messages,
      nextPageToken: response.data.nextPageToken,
      resultSizeEstimate: response.data.resultSizeEstimate
    });

  } catch (error) {
    console.error('Error fetching Gmail messages:', error);
    res.status(500).json({ error: 'Failed to fetch messages', details: error.message });
  }
});

// Get specific email from Gmail
router.get('/gmail/messages/:messageId', auth, async (req, res) => {
  try {
    const { messageId } = req.params;
    
    // Get the user to access their tokens
    const user = await User.findById(req.user.id);
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Get authenticated Gmail client
    const auth = await getGoogleClient(user);
    const gmail = google.gmail({ version: 'v1', auth });

    // Get message details
    const details = await gmail.users.messages.get({
      userId: 'me',
      id: messageId,
      format: 'full'
    });

    // Extract headers
    const headers = details.data.payload.headers;
    const subject = headers.find(h => h.name === 'Subject')?.value || '';
    const from = headers.find(h => h.name === 'From')?.value || '';
    const to = headers.find(h => h.name === 'To')?.value || '';
    const date = headers.find(h => h.name === 'Date')?.value || '';

    // Extract body
    let body = '';
    if (details.data.payload.parts) {
      // Handle multipart messages
      const textPart = details.data.payload.parts.find(
        part => part.mimeType === 'text/plain'
      );
      if (textPart && textPart.body.data) {
        body = Buffer.from(textPart.body.data, 'base64').toString();
      }
    } else if (details.data.payload.body.data) {
      // Handle single part messages
      body = Buffer.from(details.data.payload.body.data, 'base64').toString();
    }

    res.json({
      id: details.data.id,
      threadId: details.data.threadId,
      subject,
      from,
      to,
      date,
      body,
      snippet: details.data.snippet,
      labelIds: details.data.labelIds
    });

  } catch (error) {
    console.error('Error fetching Gmail message:', error);
    res.status(500).json({ error: 'Failed to fetch message', details: error.message });
  }
});

// Get all sent messages contacts
router.get('/gmail/sent/contacts/all', auth, async (req, res) => {
  try {
    const { batchSize = 100 } = req.query;
    
    // Get the user to access their tokens
    const user = await User.findById(req.user.id);
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Get authenticated Gmail client
    const auth = await getGoogleClient(user);
    const gmail = google.gmail({ version: 'v1', auth });

    // Use Map to store unique contacts
    const contactsMap = new Map();
    let pageToken = null;
    let hasMore = true;
    let totalProcessed = 0;

    while (hasMore) {
      // List sent messages
      const response = await gmail.users.messages.list({
        userId: 'me',
        q: 'from:me',
        maxResults: parseInt(batchSize),
        pageToken: pageToken
      });

      if (!response.data.messages) {
        break;
      }

      // Get "To" headers from each message
      await Promise.all(
        response.data.messages.map(async (message) => {
          const details = await gmail.users.messages.get({
            userId: 'me',
            id: message.id,
            format: 'metadata',
            metadataHeaders: ['To']
          });
          
          // Extract To header
          const headers = details.data.payload.headers;
          const to = headers.find(h => h.name === 'To')?.value || '';

          // Parse recipients
          const recipients = to.split(',').map(recipient => {
            const matches = recipient.match(/([^<]+)?<?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>?/);
            if (matches) {
              const [, name = '', email] = matches;
              return {
                name: name.trim(),
                email: email.trim().toLowerCase()
              };
            }
            return {
              name: '',
              email: recipient.trim().toLowerCase()
            };
          });

          // Add to contactsMap
          recipients.forEach(recipient => {
            if (recipient.email) {
              const existing = contactsMap.get(recipient.email);
              if (!existing || (recipient.name && !existing.name)) {
                contactsMap.set(recipient.email, recipient);
              }
            }
          });
        })
      );

      totalProcessed += response.data.messages.length;
      pageToken = response.data.nextPageToken;
      hasMore = !!pageToken;

      // Send progress update
      res.write(JSON.stringify({
        status: 'processing',
        processed: totalProcessed,
        currentContacts: contactsMap.size
      }) + '\n');
    }

    // Convert Map to array and sort by email
    const contacts = Array.from(contactsMap.values()).sort((a, b) => 
      a.email.localeCompare(b.email)
    );

    res.write(JSON.stringify({
      status: 'complete',
      contacts,
      total: contacts.length,
      messagesProcessed: totalProcessed
    }));
    res.end();

  } catch (error) {
    console.error('Error fetching all contacts:', error);
    res.status(500).json({ error: 'Failed to fetch all contacts', details: error.message });
  }
});

// Search contacts for email suggestions
router.get('/gmail/contacts/search', auth, async (req, res) => {
  try {
    const { query } = req.query;
    if (!query) {
      return res.status(400).json({ error: 'Search query is required' });
    }

    // Get the user to access their tokens
    const user = await User.findById(req.user.id);
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Get authenticated Gmail client
    const auth = await getGoogleClient(user);
    const gmail = google.gmail({ version: 'v1', auth });

    // Use Map to store unique contacts
    const contactsMap = new Map();
    let pageToken = null;
    let hasMore = true;

    while (hasMore) {
      // List sent messages
      const response = await gmail.users.messages.list({
        userId: 'me',
        q: 'from:me',
        maxResults: 100,
        pageToken: pageToken
      });

      if (!response.data.messages) {
        break;
      }

      // Get "To" headers from each message
      await Promise.all(
        response.data.messages.map(async (message) => {
          const details = await gmail.users.messages.get({
            userId: 'me',
            id: message.id,
            format: 'metadata',
            metadataHeaders: ['To']
          });
          
          // Extract To header
          const headers = details.data.payload.headers;
          const to = headers.find(h => h.name === 'To')?.value || '';

          // Parse recipients
          const recipients = to.split(',').map(recipient => {
            const matches = recipient.match(/([^<]+)?<?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>?/);
            if (matches) {
              const [, name = '', email] = matches;
              return {
                name: name.trim().toLowerCase(), // Normalize names for searching
                email: email.trim().toLowerCase() // Normalize emails for searching
              };
            }
            return {
              name: '',
              email: recipient.trim().toLowerCase()
            };
          });

          // Add to contactsMap
          recipients.forEach(recipient => {
            if (recipient.email) {
              contactsMap.set(recipient.email, recipient);
            }
          });
        })
      );

      pageToken = response.data.nextPageToken;
      hasMore = !!pageToken;
    }

    // Convert Map to array
    const allContacts = Array.from(contactsMap.values());

    // Search through contacts
    const searchTerms = query.toLowerCase().split(' ').filter(term => term.length > 0);
    const matches = allContacts.filter(contact => {
      return searchTerms.some(term => 
        contact.name.includes(term) || 
        contact.email.includes(term)
      );
    });

    // Sort matches by relevance (exact matches first, then partial matches)
    matches.sort((a, b) => {
      const aExactMatch = searchTerms.some(term => 
        a.name === term || a.email.includes(term)
      );
      const bExactMatch = searchTerms.some(term => 
        b.name === term || b.email.includes(term)
      );

      if (aExactMatch && !bExactMatch) return -1;
      if (!aExactMatch && bExactMatch) return 1;
      return a.email.localeCompare(b.email);
    });

    // Return only email addresses
    const emailSuggestions = matches.map(contact => contact.email);

    res.json({
      query,
      suggestions: emailSuggestions
    });

  } catch (error) {
    console.error('Error searching contacts:', error);
    res.status(500).json({ error: 'Failed to search contacts', details: error.message });
  }
});

// Enhanced email search route
router.post('/search', auth, async (req, res) => {
  try {
    const { query } = req.body;
    
    if (!query || query.trim() === '') {
      return res.status(400).json({ 
        success: false, 
        message: "Please provide a search query." 
      });
    }
    
    // Get user from request (set by auth middleware)
    const user = req.user;
    
    console.log(`Enhanced email search request from user ${user.id} with query: "${query}"`);
    
    // Call the enhanced search function
    const searchResults = await enhancedEmailSearch(user, query);
    
    return res.json(searchResults);
  } catch (error) {
    console.error('Error in enhanced email search route:', error);
    return res.status(500).json({
      success: false,
      message: "An error occurred while searching emails.",
      error: error.message
    });
  }
});

module.exports = router; 
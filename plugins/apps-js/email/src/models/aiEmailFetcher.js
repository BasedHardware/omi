const OpenAI = require('openai');
const { google } = require('googleapis');
const { getGoogleClient } = require('../utils/googleAuth');
const { fetchUserById } = require('../utils/supabaseUtils');

// Function to fetch emails based on context
async function fetchEmailsByContext(user, context) {
  try {
    if (!context || context.trim().length === 0) {
      console.warn(`[${user.id}] fetchEmailsByContext called with empty context.`);
      return { success: false, message: "I couldn't understand which emails to fetch." };
    }
    
    console.log(`[${user.id}] Analyzing fetch request: "${context.substring(0, 100)}..."`);
    
    // First try enhanced search if query looks complex
    const isComplexQuery = context.length > 20 || 
                          context.includes("about") || 
                          context.includes("related to") ||
                          context.includes("similar to") ||
                          context.includes("find emails") ||
                          context.includes("search for");
                          
    if (isComplexQuery) {
      const enhancedResult = await tryEnhancedSearch(user, context);
      if (enhancedResult) {
        return enhancedResult;
      }
    }
    
    // If enhanced search wasn't used or failed, continue with standard search
    // Add detailed debugging of user object
    console.log(`[DEBUG] User object in fetchEmailsByContext:`, {
      id: user.id,
      user_id: user.user_id,
      _id: user._id,
      email: user.email,
      hasToken: !!user.token,
      hasRefreshToken: !!user.refresh_token,
      tokenExpiry: user.token_expiry
    });
    
    // Create OpenAI client with the API key
    const openaiClient = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY,
    });
    
    // 1. Extract search parameters using OpenAI
    const searchParams = await extractSearchParameters(context, user.id, openaiClient);
    
    // 2. Build Gmail API query
    const gmailQuery = buildGmailQuery(searchParams);
    
    if (!gmailQuery.trim()) {
      return { 
        success: false, 
        message: "I couldn't determine what emails you're looking for. Please specify a sender, subject, or other search terms." 
      };
    }
    
    console.log(`[${user.id}] Fetching emails with query: "${gmailQuery}"`);
    
    // 3. Ensure we have a fully authenticated user with tokens
    try {
      // First check if this user object might be from server.js's getAuthenticatedUser
      if (!user.token) {
        console.log(`[${user.id}] User object missing token, trying to fetch from db`);
        try {
          // Fetch the complete user record from the database
          const authenticatedUser = await fetchUserById(user.id || user.user_id);
          if (!authenticatedUser) {
            return { 
              success: false, 
              message: "You need to authenticate with Gmail first. Please try again after connecting your account." 
            };
          }
          
          // Replace the user object with the fully authenticated one
          user = authenticatedUser;
          console.log(`[${user.id}] Retrieved authenticated user from database`);
        } catch (dbError) {
          console.error(`[${user.id}] Error fetching user from database:`, dbError);
          return { 
            success: false, 
            message: "Authentication failed. Please reconnect your Gmail account." 
          };
        }
      }
      
      if (!user.token) {
        console.error(`[${user.id}] Failed to get valid token for user`);
        return { 
          success: false, 
          message: "Your Gmail authentication is missing or expired. Please reconnect your account." 
        };
      }
      
      // Normalize the user object for consistency
      const normalizedUser = {
        ...user,
        user_id: user.id || user.user_id,
        _id: user.id || user._id || user.user_id,
        name: user.name || user.email?.split('@')[0],
        email: user.email
      };
      
      console.log(`[${user.id}] Using token for Gmail API. Token exists: ${!!normalizedUser.token}, Refresh token exists: ${!!normalizedUser.refresh_token}`);
      
      // 4. Search for emails using centralized authentication with 6-month reverification
      const auth = await getGoogleClient(normalizedUser);
      const gmail = google.gmail({ version: 'v1', auth });
      
      // Call Gmail API to search for emails
      const searchResponse = await gmail.users.messages.list({
        userId: 'me',
        q: gmailQuery,
        maxResults: searchParams.limit
      });
      
      if (!searchResponse.data.messages || searchResponse.data.messages.length === 0) {
        return { 
          success: true, 
          message: `I couldn't find any emails matching your search for ${searchParams.from ? 'emails from ' + searchParams.from : 'your query'}.` 
        };
      }
      
      // 5. Get the full message content
      const messageId = searchResponse.data.messages[0].id;
      const messageResponse = await gmail.users.messages.get({
        userId: 'me',
        id: messageId,
        format: 'full'
      });
      
      // Process the email data
      const messageData = messageResponse.data;
      
      // Extract headers
      const headers = messageData.payload.headers;
      const fromHeader = headers.find(h => h.name.toLowerCase() === 'from');
      const subjectHeader = headers.find(h => h.name.toLowerCase() === 'subject');
      const dateHeader = headers.find(h => h.name.toLowerCase() === 'date');
      const toHeader = headers.find(h => h.name.toLowerCase() === 'to');
      
      // Extract body
      let body = '';
      
      if (messageData.payload.parts) {
        // Multipart message
        for (const part of messageData.payload.parts) {
          if (part.mimeType === 'text/plain' && part.body.data) {
            body = Buffer.from(part.body.data, 'base64').toString('utf8');
            break;
          }
        }
      } else if (messageData.payload.body && messageData.payload.body.data) {
        // Single part message
        body = Buffer.from(messageData.payload.body.data, 'base64').toString('utf8');
      }
      
      // Format email nicely
      let formattedEmail = {
        from: fromHeader ? fromHeader.value : 'Unknown Sender',
        to: toHeader ? toHeader.value : 'You',
        subject: subjectHeader ? subjectHeader.value : 'No Subject',
        date: dateHeader ? new Date(dateHeader.value).toLocaleString() : 'Unknown Date',
        body: body || 'No readable content found in this email.',
        messageId
      };
      
      // Create a nicely formatted message for display
      formattedEmail.displayText = `
From: ${formattedEmail.from}
To: ${formattedEmail.to}
Subject: ${formattedEmail.subject}
Date: ${formattedEmail.date}

${formattedEmail.body}
`.trim();
      
      // Create a message that includes search details
      let searchDetails = [];
      if (searchParams.from) searchDetails.push(`from ${searchParams.from}`);
      if (searchParams.subject) searchDetails.push(`with subject "${searchParams.subject}"`);
      if (searchParams.timeFrame) searchDetails.push(`from ${searchParams.timeFrame}`);
      
      const searchDetailText = searchDetails.length > 0 
        ? `matching your search criteria (${searchDetails.join(', ')})` 
        : 'that matches your search';
        
      // Clean up the body text to remove HTML tags if present
      let cleanBody = formattedEmail.body;
      
      // If the body contains HTML tags, clean it up more thoroughly
      if (cleanBody.includes('<div') || cleanBody.includes('<p') || cleanBody.includes('<span')) {
        // Replace common HTML entities
        cleanBody = cleanBody
          .replace(/&nbsp;/g, ' ')
          .replace(/&amp;/g, '&')
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>')
          .replace(/&quot;/g, '"');
          
        // Replace line breaks and paragraph tags with newlines
        cleanBody = cleanBody
          .replace(/<br\s*\/?>/gi, '\n')
          .replace(/<\/p>/gi, '\n')
          .replace(/<\/div>/gi, '\n');
          
        // Remove all remaining HTML tags
        cleanBody = cleanBody.replace(/<[^>]*>?/gm, '');
        
        // Fix multiple consecutive newlines
        cleanBody = cleanBody.replace(/\n{3,}/g, '\n\n');
      }
      
      // Prepare email details for response
      const emailContent = `Subject: ${formattedEmail.subject}\n\nFrom: ${formattedEmail.from}\nDate: ${formattedEmail.date}\n\n${cleanBody.trim()}`;
      
      // Return consistent response format that matches the webhook expectations
      return {
        success: true,
        message: emailContent,
        email: formattedEmail
      };
    } catch (error) {
      console.error(`[${user.id}] Gmail API error:`, error);
      return { 
        success: false, 
        message: "I encountered an error while trying to fetch your emails. Please try again later."
      };
    }
  } catch (error) {
    console.error('Error fetching emails by context:', error);
    return { 
      success: false, 
      message: "I encountered an error while trying to fetch your emails. Please try again later."
    };
  }
}

/**
 * Extract search parameters from user query using OpenAI
 */
async function extractSearchParameters(context, userId, openaiClient) {
  const searchPrompt = `
Analyze the following user's email search request and extract key search parameters.

User Request: "${context}"

Extract the following parameters from the request:
1. From: The sender's name or email address the user wants to find emails from
2. Subject: Any subject terms or phrases mentioned
3. TimeFrame: Any time frame mentioned (e.g., "recent", "last week", "today")
4. Limit: How many emails to fetch (default to 1 if not specified)
5. IsLatest: Whether the user is specifically asking for the most recent email (true/false)

Output ONLY a JSON object in the following format:
{
  "from": "sender name or email" | null,
  "subject": "subject terms" | null,
  "timeFrame": "time specification" | null,
  "limit": number,
  "isLatest": boolean,
  "rawQuery": "simplified search query"
}

If a parameter is not present in the request, use null for string values, 1 for limit, and false for boolean values.
  `.trim();
  
  // Fallback: return empty or default params
  let rawOpenAIResponseText = 'Unknown OpenAI response'; // Declare here to be accessible in catch
  try {
    const searchResponse = await openaiClient.chat.completions.create({ 
      model: "gpt-3.5-turbo", 
      messages: [{role: "user", content: searchPrompt}], 
      max_tokens: 150,
      temperature: 0.2,
    });
    
    rawOpenAIResponseText = searchResponse.choices[0].message.content; // Assign here
    const jsonMatch = rawOpenAIResponseText.match(/\{([\s\S]*)\}/); 
    if (jsonMatch) {
      try {
        const searchParams = JSON.parse(jsonMatch[0]);
        console.log(`[${userId}] Extracted search parameters:`, searchParams);
        return searchParams;
      } catch (e) {
        console.error(`[${userId}] Error parsing search parameters:`, e);
      }
    } else {
      console.warn(`[${userId}] Could not extract search parameters, using defaults`);
    }
  } catch (e) {
    console.error(`[${userId}] Error getting search parameters from OpenAI:`, e);
    console.error('Raw OpenAI response text:', rawOpenAIResponseText); // Now accessible
    return {
      from: null,
      subject: null,
      timeFrame: null,
      keywords: [],
      limit: 1,
      error: `Error getting search parameters from OpenAI: ${e.message}`
    };
  }
}

/**
 * Build Gmail API query from search parameters
 */
function buildGmailQuery(searchParams) {
  let gmailQuery = '';
  
  if (searchParams.from) {
    gmailQuery += `from:(${searchParams.from}) `;
  }
  
  if (searchParams.subject) {
    gmailQuery += `subject:(${searchParams.subject}) `;
  }
  
  if (searchParams.timeFrame) {
    // Convert timeFrame to appropriate Gmail query
    if (searchParams.timeFrame.includes('recent') || searchParams.timeFrame.includes('latest')) {
      // No additional filter needed as we'll sort by date
    } else if (searchParams.timeFrame.includes('today')) {
      gmailQuery += 'newer_than:1d ';
    } else if (searchParams.timeFrame.includes('week')) {
      gmailQuery += 'newer_than:7d ';
    } else if (searchParams.timeFrame.includes('month')) {
      gmailQuery += 'newer_than:30d ';
    }
  }
  
  // Use raw query if all else fails
  if (!gmailQuery.trim() && searchParams.rawQuery) {
    gmailQuery = searchParams.rawQuery;
  }
  
  // If still empty, make a basic query for latest email
  if (!gmailQuery.trim() && searchParams.isLatest) {
    gmailQuery = 'in:inbox';
  }
  
  return gmailQuery.trim();
}

// Try enhanced search if available
async function tryEnhancedSearch(user, context) {
  try {
    // Dynamic import to avoid circular reference
    const { enhancedEmailSearch } = require('./enhancedEmailSearch');
    if (typeof enhancedEmailSearch === 'function') {
      console.log(`[${user.id}] Using enhanced search capabilities for: "${context}"`);
      
      // Check if this might be a search for an unusual domain or email address
      const emailMatch = context.match(/\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{1,})\b/);
      const domainMatch = context.match(/(?:from|at|by)\s+(?:[^\s@]+\.)+([a-zA-Z]{1,})\b/i);
      
      // If we detected an unusual email pattern, enhance the query to ensure it's properly handled
      if (emailMatch || domainMatch) {
        const enhancedContext = context;
        
        // Log that we found a potential unusual domain/email
        if (emailMatch) {
          console.log(`[${user.id}] Detected potential email address in query: ${emailMatch[0]}`);
        }
        if (domainMatch) {
          console.log(`[${user.id}] Detected potential unusual domain in query: ${domainMatch[0]}`);
        }
        
        // Use the enhanced search with special attention to unusual domains
        const searchOptions = {
          prioritizeDomainMatching: true,
          expandedSearch: true
        };
        
        return await enhancedEmailSearch(user, enhancedContext, searchOptions);
      }
      
      // Standard enhanced search for other queries
      return await enhancedEmailSearch(user, context);
    }
    
    // If not available or error, continue with regular search
    return null;
  } catch (error) {
    console.error(`[${user.id}] Enhanced search failed, falling back to standard search:`, error);
    return null;
  }
}

module.exports = {
  fetchEmailsByContext,
  tryEnhancedSearch
};

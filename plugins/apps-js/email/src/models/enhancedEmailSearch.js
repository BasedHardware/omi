/**
 * Enhanced Email Search Module
 * 
 * Combines Gmail API and OpenAI for intelligent email search capabilities including:
 * 1. Natural Language Query Translation
 * 2. Semantic Search with Embeddings
 * 3. Content Summarization and Relevance Ranking
 */

const OpenAI = require('openai');
const { google } = require('googleapis');
const { getGoogleClient } = require('../utils/googleAuth');
require('dotenv').config();

// Initialize OpenAI client
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

/**
 * Main function to search emails with enhanced capabilities
 * 
 * @param {Object} user - The authenticated user object
 * @param {String} naturalLanguageQuery - The search query in natural language
 * @param {Object} options - Additional options for the search
 * @returns {Object} - The search results
 */
async function enhancedEmailSearch(user, naturalLanguageQuery, options = {}) {
  try {
    console.log(`[${user.id}] Starting enhanced email search for query: "${naturalLanguageQuery}"`);
    
    // Handle search options
    const prioritizeDomainMatching = options.prioritizeDomainMatching || false;
    const expandedSearch = options.expandedSearch || false;
    
    if (prioritizeDomainMatching) {
      console.log(`[${user.id}] Domain matching prioritization is enabled`);
    }
    
    if (expandedSearch) {
      console.log(`[${user.id}] Expanded search is enabled`);
    }
    
    // 1. Natural Language Query Translation
    const { gmailQuery, extractedParameters } = await translateNaturalLanguageToGmailQuery(naturalLanguageQuery);
    console.log(`[${user.id}] Translated query: "${gmailQuery}"`);
    console.log(`[${user.id}] Extracted parameters:`, extractedParameters);

    // 2. Search emails using Gmail API
    let searchResult = await searchGmail(gmailQuery, user, extractedParameters.limit || 10);
    
    // Track if we're using primary or fallback search
    let searchMethod = "primary";
    let searchQueries = [gmailQuery];
    
    // 3. Try fallback strategies if no results were found or expanded search is requested
    if (!searchResult.messages || searchResult.messages.length === 0 || expandedSearch) {
      console.log(`[${user.id}] ${searchResult.messages?.length ? 'Expanded' : 'Primary'} search ${searchResult.messages?.length ? 'requested' : 'returned no results'}, attempting fallbacks`);
      
      // Fallback strategies to try
      const fallbackQueries = [];
      
      // Fallback 1: Try searching by sender name only if email search fails
      if (extractedParameters.sender && extractedParameters.sender.name) {
        const nameOnlyQuery = `from:"${extractedParameters.sender.name}"`;
        fallbackQueries.push(nameOnlyQuery);
      }
      
      // Fallback 2: Try searching by domain parts if sender has domain
      if (extractedParameters.sender && extractedParameters.sender.domain) {
        const domainParts = extractedParameters.sender.domain.split('.');
        if (domainParts.length > 0) {
          const domainBaseQuery = `from:${domainParts[0]}`;
          fallbackQueries.push(domainBaseQuery);
        }
      }
      
      // Fallback 3: Try wildcard search with email username if available
      if (extractedParameters.sender && extractedParameters.sender.email) {
        const username = extractedParameters.sender.email.split('@')[0];
        if (username && username.length > 2) { // Only if username is meaningful
          const wildcardQuery = `from:*${username}*`;
          fallbackQueries.push(wildcardQuery);
        }
      }
      
      // Fallback 4: Try a more general query using the extracted subject or content
      if (extractedParameters.subject) {
        fallbackQueries.push(`subject:${extractedParameters.subject}`);
      }
      
      if (extractedParameters.content) {
        if (Array.isArray(extractedParameters.content)) {
          fallbackQueries.push(extractedParameters.content.join(' OR '));
        } else {
          fallbackQueries.push(extractedParameters.content);
        }
      }
      
      // Fallback 5: For unusual domains, try more aggressive matching
      if (prioritizeDomainMatching && extractedParameters.sender && extractedParameters.sender.email) {
        // Extract parts from the email address
        const email = extractedParameters.sender.email;
        const [username, domain] = email.split('@');
        
        if (domain) {
          // Try each domain part separately
          const domainParts = domain.split('.');
          for (const part of domainParts) {
            if (part.length > 1) { // Skip very short parts
              fallbackQueries.push(`from:*${part}*`); // Wildcard search for domain part
            }
          }
          
          // If domain has unusual TLD (less than 3 chars), try extra searches
          const tld = domainParts[domainParts.length - 1];
          if (tld && tld.length < 3) {
            // Search without specifying TLD
            const domainWithoutTld = domainParts.slice(0, -1).join('.');
            fallbackQueries.push(`from:*${domainWithoutTld}*`);
          }
        }
      }
      
      // Try each fallback query until we find results
      for (const fallbackQuery of fallbackQueries) {
        console.log(`[${user.id}] Trying fallback search: "${fallbackQuery}"`);
        searchQueries.push(fallbackQuery);
        
        const fallbackResult = await searchGmail(fallbackQuery, user, extractedParameters.limit || 10);
        if (fallbackResult.messages && fallbackResult.messages.length > 0) {
          // If we already had results but want expanded search, merge the results
          if (searchResult.messages && searchResult.messages.length > 0 && expandedSearch) {
            // Create a Set to track unique IDs
            const messageIds = new Set(searchResult.messages.map(m => m.id));
            
            // Add new messages that weren't in the original results
            for (const message of fallbackResult.messages) {
              if (!messageIds.has(message.id)) {
                searchResult.messages.push(message);
                messageIds.add(message.id);
              }
            }
            
            // Update metadata
            searchResult.resultSizeEstimate = searchResult.messages.length;
            searchMethod = "expanded";
            console.log(`[${user.id}] Expanded search successful with query: "${fallbackQuery}". Total results: ${searchResult.messages.length}`);
          } else {
            // Otherwise just use the fallback results
            searchResult = fallbackResult;
            searchMethod = "fallback";
            console.log(`[${user.id}] Fallback search successful with query: "${fallbackQuery}"`);
            if (!expandedSearch) break; // Only break if we're not collecting expanded results
          }
        }
      }
    }
    
    // If still no results after all fallbacks
    if (!searchResult.messages || searchResult.messages.length === 0) {
      return {
        success: true,
        message: "No emails found matching your search criteria.",
        query: gmailQuery,
        fallbackQueriesAttempted: searchQueries.length - 1,
        extractedParameters
      };
    }

    // Limit the number of messages for expanded search to avoid performance issues
    if (searchResult.messages.length > 20) {
      searchResult.messages = searchResult.messages.slice(0, 20);
    }

    // 4. Fetch full content of emails
    const emails = await Promise.all(
      searchResult.messages.slice(0, extractedParameters.limit || 10).map(async (message) => {
        try {
          return await getEmailContent(message.id, user);
        } catch (error) {
          console.error(`[${user.id}] Error fetching email ${message.id}:`, error);
          return null;
        }
      })
    );

    // Filter out any nulls from emails that failed to load
    const validEmails = emails.filter(email => email !== null);
    
    if (validEmails.length === 0) {
      return {
        success: false,
        message: "I found some emails but couldn't retrieve their content. Please try again.",
      };
    }

    // 5. Semantic search and relevance ranking with enhanced scoring for unusual domains
    let rankedEmails = await rankEmailsBySimilarity(validEmails, naturalLanguageQuery);
    
    // 6. Special domain handling: If searching for an unusual domain, boost those matches
    if ((extractedParameters.sender && extractedParameters.sender.domain) || prioritizeDomainMatching) {
      const targetDomain = extractedParameters.sender && extractedParameters.sender.domain ? 
                        extractedParameters.sender.domain.toLowerCase() : null;
      const targetUsername = extractedParameters.sender && extractedParameters.sender.email ? 
                          extractedParameters.sender.email.split('@')[0].toLowerCase() : null;
      
      // Re-rank emails to boost exact domain matches
      rankedEmails = rankedEmails.map(email => {
        const fromAddr = email.from.toLowerCase();
        let domainBoost = 0;
        
        // Apply higher boost if domain matching is prioritized
        const boostMultiplier = prioritizeDomainMatching ? 1.5 : 1.0;
        
        // Check for exact or partial domain match
        if (targetDomain && fromAddr.includes(targetDomain)) {
          domainBoost += 0.3 * boostMultiplier; // Significant boost for domain match
        } else if (targetDomain) {
          // Check for partial domain match (e.g. "galaxy" in "galaxy.ai")
          const domainParts = targetDomain.split('.');
          if (domainParts.some(part => fromAddr.includes(part) && part.length > 2)) {
            domainBoost += 0.15 * boostMultiplier; // Smaller boost for partial match
          }
        }
        
        // Check for username match in sender
        if (targetUsername && fromAddr.includes(targetUsername)) {
          domainBoost += 0.2 * boostMultiplier;
        }
        
        // Additional check for unusual domains with email pattern detection
        const emailMatches = fromAddr.match(/[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{1,})/);
        if (emailMatches && prioritizeDomainMatching) {
          const fromDomain = emailMatches[1].toLowerCase();
          
          // Check if this is a non-standard TLD (less than 3 chars)
          const domainParts = fromDomain.split('.');
          const tld = domainParts[domainParts.length - 1];
          
          if (tld && tld.length < 3 && targetDomain && targetDomain.endsWith(tld)) {
            // Boost emails with the same unusual TLD
            domainBoost += 0.25 * boostMultiplier;
          }
          
          // If searching for an email with a single-char TLD (.a), highly prioritize matches
          if (tld && tld.length === 1 && targetDomain && targetDomain.endsWith(`.${tld}`)) {
            domainBoost += 0.35 * boostMultiplier;
          }
        }
        
        // Only apply boost if there's a match
        if (domainBoost > 0) {
          return {
            ...email,
            relevanceScore: Math.min(1.0, email.relevanceScore + domainBoost),
            boostedScore: true
          };
        }
        
        return email;
      });
      
      // Re-sort after applying boosts
      rankedEmails.sort((a, b) => b.relevanceScore - a.relevanceScore);
    }
    
    // 7. Summarize top results
    const summarizedResults = await summarizeSearchResults(rankedEmails.slice(0, 3), naturalLanguageQuery);
    
    // 8. Format response
    const topResults = summarizedResults.map(email => ({
      id: email.messageId,
      from: email.from,
      subject: email.subject,
      date: email.date,
      summary: email.summary,
      relevanceScore: email.relevanceScore,
      boosted: email.boostedScore || false
    }));

    // Create email list for display
    const emailListText = topResults.map((email, index) => 
      `${index + 1}. From: ${email.from}\n   Subject: ${email.subject}\n   Date: ${email.date}\n   Summary: ${email.summary}`
    ).join('\n\n');

    // Create response message with search method info
    let searchMethodInfo = "";
    if (searchMethod === "fallback") {
      searchMethodInfo = " (using expanded search)";
    } else if (searchMethod === "expanded") {
      searchMethodInfo = " (using combined search results)";
    }
      
    const responseMessage = `Here are the most relevant emails matching your search for "${naturalLanguageQuery}"${searchMethodInfo}:\n\n${emailListText}`;

    return {
      success: true,
      message: responseMessage,
      results: topResults,
      query: gmailQuery,
      searchMethod,
      queriesAttempted: searchQueries,
      totalFound: searchResult.messages.length,
      displayedResults: topResults.length
    };
  } catch (error) {
    console.error('Error in enhancedEmailSearch:', error);
    return {
      success: false,
      message: "I encountered an error while searching your emails. Please try again later.",
      error: error.message
    };
  }
}

/**
 * Translates natural language query to Gmail API query format
 * 
 * @param {String} naturalLanguageQuery - The natural language search query
 * @returns {Object} - The Gmail API query and extracted parameters
 */
async function translateNaturalLanguageToGmailQuery(naturalLanguageQuery) {
  try {
    const prompt = `
Translate the following natural language email search query into a structured Gmail search query.

User Query: "${naturalLanguageQuery}"

Extract the following parameters:
1. Sender: Who sent the email (if specified)
   - Extract both name and email address if available
   - For unusual domain names or TLDs, ensure they're captured correctly 
   - Consider partial domain matches (e.g., "galaxy" should match "galaxy.ai")
2. Recipient: Who received the email (if specified)
3. Subject: Subject terms or phrases
4. Content: Content terms or phrases
5. Date: Any date or time specifications
6. Labels: Any mentioned labels or categories
7. Attachments: Whether attachments are mentioned
8. Limit: How many emails to return (default: 10)

Then, convert these parameters into a Gmail search query format using Gmail's search operators:
- from: (for sender, use quotes for exact matching of unusual domains)
- to: (for recipient)
- subject: (for subject terms)
- after: or before: (for dates, in YYYY/MM/DD format)
- has:attachment (if attachments were mentioned)
- label: (for labels)
- Plain terms for content search

For email addresses, try these variations in the "gmailQuery" field if a specific domain is mentioned:
1. Exact match: from:humans@mail.galaxy.a
2. Name match: from:Humans
3. Domain match: from:galaxy

Output ONLY a JSON object in this format:
{
  "gmailQuery": "the formatted Gmail search query",
  "extractedParameters": {
    "sender": {
      "name": "extracted sender name or null",
      "email": "extracted sender email or null",
      "domain": "extracted sender domain or null"
    },
    "recipient": "extracted recipient or null",
    "subject": "extracted subject terms or null",
    "content": "extracted content terms or null",
    "date": {
      "after": "date in YYYY/MM/DD format or null",
      "before": "date in YYYY/MM/DD format or null"
    },
    "hasAttachment": true/false,
    "labels": ["label1", "label2"] or [],
    "limit": number
  }
}
`;

    const response = await openai.chat.completions.create({
      model: "gpt-3.5-turbo",
      messages: [{role: "user", content: prompt}],
      max_tokens: 500,
      temperature: 0.2,
    });

    const content = response.choices[0].message.content;
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    
    if (!jsonMatch) {
      console.error("Failed to extract JSON from OpenAI response:", content);
      // Fallback with basic query
      return {
        gmailQuery: naturalLanguageQuery.replace(/\s+/g, ' OR '),
        extractedParameters: { 
          sender: { name: null, email: null, domain: null },
          limit: 10 
        }
      };
    }

    try {
      const result = JSON.parse(jsonMatch[0]);
      
      // Handle legacy format conversion (for backward compatibility)
      if (typeof result.extractedParameters.sender === 'string') {
        const senderStr = result.extractedParameters.sender;
        result.extractedParameters.sender = {
          name: null,
          email: senderStr,
          domain: senderStr ? senderStr.split('@')[1] : null
        };
      }
      
      // If the sender field is missing but mentioned in the query, try to extract it
      if (!result.extractedParameters.sender || 
          (!result.extractedParameters.sender.email && !result.extractedParameters.sender.name)) {
        const emailMatch = naturalLanguageQuery.match(/\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{1,})\b/);
        if (emailMatch) {
          const email = emailMatch[0];
          const domain = email.split('@')[1];
          if (!result.extractedParameters.sender) {
            result.extractedParameters.sender = { name: null, email, domain };
          } else {
            result.extractedParameters.sender.email = email;
            result.extractedParameters.sender.domain = domain;
          }
          
          // Update the Gmail query if it doesn't already contain from: operator
          if (!result.gmailQuery.includes('from:')) {
            result.gmailQuery = `from:"${email}" ${result.gmailQuery}`.trim();
          }
        }
      }
      
      // Create expanded query for better matching with unusual domains
      if (result.extractedParameters.sender && result.extractedParameters.sender.email) {
        const originalQuery = result.gmailQuery;
        const email = result.extractedParameters.sender.email;
        const domain = result.extractedParameters.sender.domain;
        const username = email.split('@')[0];
        
        let expandedQuery = originalQuery;
        
        // If only the exact email is used, create a more flexible query
        if (originalQuery.trim() === `from:${email}`) {
          // Try variations to improve matching
          const domainParts = domain ? domain.split('.') : [];
          const domainBase = domainParts.length > 0 ? domainParts[0] : null;
          
          const variations = [];
          
          // Add the exact match first
          variations.push(`from:"${email}"`);
          
          // Add username match
          if (username) variations.push(`from:"${username}"`);
          
          // Add domain match
          if (domainBase) variations.push(`from:${domainBase}`);
          
          // Combine variations
          expandedQuery = variations.join(' OR ');
        }
        
        result.gmailQuery = expandedQuery;
      }
      
      return result;
    } catch (error) {
      console.error("Error parsing JSON from OpenAI response:", error);
      return {
        gmailQuery: naturalLanguageQuery.replace(/\s+/g, ' OR '),
        extractedParameters: { 
          sender: { name: null, email: null, domain: null },
          limit: 10 
        }
      };
    }
  } catch (error) {
    console.error('Error translating natural language to Gmail query:', error);
    // Fallback with basic query
    return {
      gmailQuery: naturalLanguageQuery.replace(/\s+/g, ' OR '),
      extractedParameters: { 
        sender: { name: null, email: null, domain: null },
        limit: 10 
      }
    };
  }
}

/**
 * Search Gmail using the API with the formatted query
 * 
 * @param {String} query - Gmail API formatted query
 * @param {Object} user - User object with authentication details
 * @param {Number} limit - Number of results to return
 * @returns {Object} - Search results
 */
async function searchGmail(query, user, limit = 10) {
  try {
    // Use centralized authentication with 6-month reverification logic
    const auth = await getGoogleClient(user);
    const gmail = google.gmail({ version: 'v1', auth });
    
    // Call Gmail API
    const response = await gmail.users.messages.list({
      userId: 'me',
      q: query,
      maxResults: limit
    });
    
    return response.data;
  } catch (error) {
    console.error(`Gmail API search error:`, error);
    throw new Error('Failed to search Gmail: ' + error.message);
  }
}

/**
 * Get full email content for a message ID
 * 
 * @param {String} messageId - The Gmail message ID
 * @param {Object} user - User object with authentication details
 * @returns {Object} - Formatted email content
 */
async function getEmailContent(messageId, user) {
  try {
    // Use centralized authentication with 6-month reverification logic
    const auth = await getGoogleClient(user);
    const gmail = google.gmail({ version: 'v1', auth });
    
    // Call Gmail API
    const response = await gmail.users.messages.get({
      userId: 'me',
      id: messageId,
      format: 'full'
    });
    
    const messageData = response.data;
    
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
      messageId,
      threadId: messageData.threadId,
      labelIds: messageData.labelIds || []
    };
    
    return formattedEmail;
  } catch (error) {
    console.error(`Gmail API message fetch error:`, error);
    throw new Error('Failed to fetch email content: ' + error.message);
  }
}

/**
 * Generate embeddings for email content or query
 * 
 * @param {String} text - The text to generate embeddings for
 * @param {String} [type='content'] - Type of embedding (content or query)
 * @returns {Array} - The embedding vector
 */
async function generateEmbedding(text, type = 'content') {
  // Truncate text to avoid token limits
  let truncatedText = text;
  const MAX_TOKENS = 8000; // OpenAI's limit for embeddings

  if (type === 'content') {
    // Extract subject and from if available
    const subjectMatch = text.match(/Subject: (.*?)(\n|$)/);
    const fromMatch = text.match(/From: (.*?)(\n|$)/);
    
    const subject = subjectMatch ? subjectMatch[1] : '';
    const from = fromMatch ? fromMatch[1] : '';
    
    // Calculate content length after reserving tokens for metadata
    const reservedChars = (subject.length + from.length + 30) * 4; // 30 for labels
    const contentMaxChars = (MAX_TOKENS * 4) - reservedChars;
    
    // Extract body content without headers
    let bodyContent = text;
    const headerEndIndex = text.indexOf('\n\n');
    if (headerEndIndex > 0) {
      bodyContent = text.substring(headerEndIndex + 2);
    }
    
    // Keep beginning and end of content
    if (bodyContent.length > contentMaxChars) {
      const beginPortion = Math.floor(contentMaxChars * 0.7); // 70% from beginning
      const endPortion = contentMaxChars - beginPortion;       // 30% from end
      
      const beginText = bodyContent.substring(0, beginPortion);
      const endText = bodyContent.substring(bodyContent.length - endPortion);
      
      // Reconstruct truncated text
      truncatedText = `Subject: ${subject}\nFrom: ${from}\n\n${beginText}\n[...content truncated...]\n${endText}`;
    }
  } else {
    // For queries, simply truncate to first MAX_TOKENS
    truncatedText = text.substring(0, MAX_TOKENS * 4);
  }

  try {
    const response = await openai.embeddings.create({
      model: "text-embedding-ada-002",
      input: truncatedText,
    });

    return response.data[0].embedding;
  } catch (error) {
    console.error('Error generating embedding:', error);
    throw error;
  }
}

/**
 * Calculate cosine similarity between two vectors
 * 
 * @param {Array} vec1 - First vector
 * @param {Array} vec2 - Second vector
 * @returns {Number} - Similarity score between 0 and 1
 */
function cosineSimilarity(vec1, vec2) {
  let dotProduct = 0;
  let mag1 = 0;
  let mag2 = 0;

  for (let i = 0; i < vec1.length; i++) {
    dotProduct += vec1[i] * vec2[i];
    mag1 += vec1[i] * vec1[i];
    mag2 += vec2[i] * vec2[i];
  }

  mag1 = Math.sqrt(mag1);
  mag2 = Math.sqrt(mag2);

  return dotProduct / (mag1 * mag2);
}

/**
 * Rank emails by semantic similarity to the query
 * 
 * @param {Array} emails - List of emails to rank
 * @param {String} query - The search query
 * @returns {Array} - Ranked emails with relevance scores
 */
async function rankEmailsBySimilarity(emails, query) {
  try {
    // Generate query embedding
    const queryEmbedding = await generateEmbedding(query, 'query');

    // Generate email embeddings and calculate similarity
    const emailSimilarities = await Promise.all(emails.map(async (email) => {
      try {
        // Create a representative text from the email for embedding
        const emailText = `Subject: ${email.subject}\n\nFrom: ${email.from}\n\n${email.body}`;
        
        // Generate embedding
        const emailEmbedding = await generateEmbedding(emailText, 'content');
        
        // Calculate similarity
        const similarity = cosineSimilarity(queryEmbedding, emailEmbedding);
        
        return {
          ...email,
          relevanceScore: similarity
        };
      } catch (error) {
        console.error(`Error processing email for similarity:`, error);
        return {
          ...email,
          relevanceScore: 0
        };
      }
    }));

    // Sort by relevance score in descending order
    return emailSimilarities.sort((a, b) => b.relevanceScore - a.relevanceScore);
  } catch (error) {
    console.error('Error ranking emails by similarity:', error);
    // Return original emails without ranking if error
    return emails.map(email => ({
      ...email,
      relevanceScore: 0
    }));
  }
}

/**
 * Summarize search results with specific focus on relevance to query
 * 
 * @param {Array} emails - List of emails to summarize
 * @param {String} query - The search query
 * @returns {Array} - Emails with added summaries
 */
async function summarizeSearchResults(emails, query) {
  return Promise.all(emails.map(async (email) => {
    try {
      const prompt = `
Summarize the following email with specific attention to how it relates to this search query: "${query}"

From: ${email.from}
Subject: ${email.subject}
Date: ${email.date}

${email.body.substring(0, 2000)}

Generate a concise summary (30-50 words) that highlights the most relevant aspects of this email in relation to the search query.
`;

      const response = await openai.chat.completions.create({
        model: "gpt-3.5-turbo",
        messages: [{role: "user", content: prompt}],
        max_tokens: 100,
        temperature: 0.3,
      });

      return {
        ...email,
        summary: response.choices[0].message.content.trim()
      };
    } catch (error) {
      console.error('Error generating summary for email:', error);
      return {
        ...email,
        summary: "Error generating summary for this email."
      };
    }
  }));
}

module.exports = {
  enhancedEmailSearch,
  translateNaturalLanguageToGmailQuery,
  rankEmailsBySimilarity,
  summarizeSearchResults
};
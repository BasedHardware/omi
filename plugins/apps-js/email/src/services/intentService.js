const OpenAI = require('openai');
const { INTENT_CACHE_TTL } = require('../config/constants');

// Initialize OpenAI client
const openaiClient = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY || 'YOUR_OPENAI_API_KEY'
});

// Add a cache for intent detection results
const intentDetectionCache = new Map();

/**
 * Detect intent using OpenAI with caching
 * @param {string} commandText - The command text to analyze
 * @param {string} userId - The user ID for logging
 * @param {OpenAI} [openaiClientInstance] - Optional OpenAI client instance
 * @returns {object} Intent detection result
 */
async function detectIntentWithOpenAI(commandText, userId, openaiClientInstance = openaiClient) {
  if (!commandText || commandText.trim().length === 0) {
    console.warn(`[${userId}] detectIntentWithOpenAI called with empty commandText.`);
    return { intent: 'unknown', reasoning: 'Empty input text.' };
  }
  
  // Create a cache key based on the text (truncate to prevent excessively long keys)
  const cacheKey = commandText.trim().substring(0, 100);
  
  // Check if we already have a cached result for this text
  const cachedResult = intentDetectionCache.get(cacheKey);
  if (cachedResult) {
    console.log(`[${userId}] Using cached intent detection result for: "${cacheKey.substring(0, 30)}..."`);
    return cachedResult;
  }

  console.log(`[${userId}] detectIntentWithOpenAI: Calling OpenAI with text: "${commandText.substring(0, 100)}..."`);
  
  const prompt = `
Analyze the following user's voice command transcript to determine the primary intent. The intent can be one of three types: "send_email", "fetch_email", or "search_email".

User Transcript: "${commandText}"

Definitions:
- "send_email": The user wants to compose, draft, reply to, or send an email. Keywords might include "send email", "draft an email to", "reply to this", "compose a message", "tell them that", "write to".
- "fetch_email": The user wants to retrieve, read, check, or get specific recent emails. Keywords might include "read my emails", "check my inbox", "what's the latest email".
- "search_email": The user wants to search for emails with specific criteria, using complex or semantic queries. Keywords might include "find emails about", "search for messages mentioning", "look for emails similar to", "find all correspondence related to", "search my emails for".

Output ONLY a JSON object in the following format, with no extra text before or after the JSON:
{
  "intent": "send_email" | "fetch_email" | "unknown",
  "reasoning": "Brief explanation of why this intent was chosen. If unknown, explain why."
}

If the intent is clearly to send or draft an email, set intent to "send_email".
If the intent is clearly to fetch, read, or search for emails, set intent to "fetch_email".
If the intent is ambiguous or neither of the above, set intent to "unknown".
Consider the dominant action implied by the transcript.
  `.trim();

  try {
    const response = await openaiClientInstance.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [{role: "user", content: prompt}],
      max_tokens: 150,
      temperature: 0.2,
    });

    let generatedText = response.choices[0].message.content.trim();
    const jsonMatch = generatedText.match(/\{([\s\S]*)\}/);

    if (jsonMatch) {
      generatedText = jsonMatch[0];
      try {
        const parsed = JSON.parse(generatedText);
        if (parsed.intent && ['send_email', 'fetch_email', 'search_email', 'unknown'].includes(parsed.intent)) {
          console.log(`[${userId}] detectIntentWithOpenAI: OpenAI response parsed:`, parsed);
          // Cache the result
          intentDetectionCache.set(cacheKey, parsed);
          
          // Set a timeout to clear this cache entry
          setTimeout(() => {
            intentDetectionCache.delete(cacheKey);
          }, INTENT_CACHE_TTL);
          
          return parsed;
        } else {
          console.warn(`[${userId}] detectIntentWithOpenAI: OpenAI returned invalid intent: ${parsed.intent}, Raw: ${generatedText}`);
          return { intent: 'unknown', reasoning: 'OpenAI returned an invalid intent value.' };
        }
      } catch (e) {
        console.error(`[${userId}] detectIntentWithOpenAI: Failed to parse JSON from OpenAI. Raw: ${generatedText}, Error:`, e);
        return { intent: 'unknown', reasoning: 'Failed to parse OpenAI JSON response.' };
      }
    }
    console.error(`[${userId}] detectIntentWithOpenAI: No valid JSON object found in OpenAI response. Raw response: ${response.choices[0].message.content.trim()}`);
    return { intent: 'unknown', reasoning: 'No valid JSON object in OpenAI response.' };

  } catch (error) {
    console.error(`[${userId}] detectIntentWithOpenAI: Error calling OpenAI API:`, error);
    return { intent: 'unknown', reasoning: `OpenAI API call error: ${error.message}` };
  }
}

/**
 * Generate email subject using OpenAI
 * @param {string} commandText - The command text to analyze
 * @param {string} userId - The user ID for logging
 * @returns {string|null} Generated subject or null if failed
 */
async function generateSubjectWithOpenAI(commandText, userId) {
  console.log(`[${userId}] Generating email subject with OpenAI for command: "${commandText.substring(0, 100)}..."`);
  
  try {
    const prompt = `
    Generate a concise, professional email subject line based on the core topic of the email command/message below.
    The subject must be under 60 characters if possible.
    
    CRITICAL INSTRUCTIONS:
    1.  **Identify Core Topic:** The subject must reflect the main subject matter or purpose of the email (e.g., "Project Update," "Invoice #123 Inquiry," "Meeting Rescheduled").
    2.  **Strictly Exclude Recipient Details:** DO NOT include any recipient names (e.g., "Syed Affan"), company names, or phrases like "Email to [Name]", "For [Name]", or "[Name] -" in the subject line. This information from the command is for context only and must not appear in the subject.
    3.  **Focus on Email's Content, Not the Command Itself:** The subject should be about what the email *contains* (the actual topic), not about the act of you drafting or sending it. Avoid subjects like "Drafting Email," "Mail Regarding," or "Request to Send." For example, if the command is "draft an email about a request to send the report," a good subject is "Request for Report," not "Request to Send."
    4.  **Output Only the Subject Line:** Provide nothing but the subject line text itself. Do not include any explanations, labels (like "Subject:"), or quotation marks.
    
    Email command/message:
    "${commandText.trim()}"
        `.trim();

    const response = await openaiClient.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [{role: "user", content: prompt}],
      max_tokens: 100,
      temperature: 0.5,
    });

    let subject = response.choices[0].message.content.trim();
    
    // Remove quotes if OpenAI wrapped the subject in quotes
    subject = subject.replace(/^["'](.*)["']$/, '$1');
    
    // Clean up common prefixes that OpenAI might add
    subject = subject.replace(/^(?:Subject|Subject line|Email subject|Re:|Subject:)\s*[:;-]\s*/i, '');
    
    // Ensure proper capitalization
    subject = subject.replace(/\b\w/g, c => c.toUpperCase());
    
    console.log(`[${userId}] Generated subject with OpenAI: "${subject}"`);
    return subject;
  } catch (error) {
    console.error(`[${userId}] Error generating subject with OpenAI:`, error);
    return null;
  }
}

/**
 * Find best contact match using OpenAI
 * @param {string} recipientHint - The recipient hint to match
 * @param {string} contactsList - The formatted contacts list
 * @returns {object|null} Match result or null if no match
 */
async function findBestContactMatch(recipientHint, contactsList) {
  try {
    const prompt = `You are an EXTREMELY STRICT contact matching assistant. Your job is to find ONLY exact or very close matches.

USER'S SPECIFIED RECIPIENT: "${recipientHint}"

AVAILABLE CONTACTS:
${contactsList}

CRITICAL RULES - FOLLOW EXACTLY:

1. ONLY MATCH IF NAMES ARE ESSENTIALLY THE SAME:
   ✅ "Mike" → "Michael Smith" (common nickname)
   ✅ "Bob" → "Robert Johnson" (common nickname)  
   ✅ "Jon" → "John Doe" (slight spelling variation)
   ✅ "Alex" → "Alexander Brown" (common abbreviation)

2. ABSOLUTELY DO NOT MATCH DIFFERENT NAMES:
   ❌ "Mustafa" ≠ "Syedaffan" (completely different names)
   ❌ "Ahmed" ≠ "John" (different names)
   ❌ "Ahmed" ≠ "Syedaffan" (different names)
   ❌ "Ahmed" ≠ "Michael" (different names)
   ❌ "Mustafa" ≠ "Michael" (different names)
   ❌ "Random" ≠ "Affan" (different names)

3. EXAMPLES OF WHAT YOU MUST REJECT:
   - If user says "Mustafa" and contacts have "Syedaffan", "Michael", "John" → RETURN "no match"
   - If user says "Ahmed" and contacts have "Syedaffan", "Bob", "Alex" → RETURN "no match"  
   - If user says "RandomName" and no contact has similar name → RETURN "no match"

4. ONLY ACCEPT THESE TYPES OF MATCHES:
   - Exact name match: "John" → "John Smith"
   - Common nicknames: "Mike" → "Michael", "Bob" → "Robert", "Alex" → "Alexander"
   - Minor spelling: "Jon" → "John", "Sara" → "Sarah"

5. IF NAMES DON'T SHARE SIGNIFICANT SIMILARITY, RETURN "no match"

CURRENT TASK:
Find a match for "${recipientHint}" in the contact list.

CRITICAL QUESTION: Does "${recipientHint}" match any contact name closely enough to be the same person?

If you're not 100% sure it's the same person or a common nickname/variation, respond with "no match".

Response format:
{
  "email": "contact@email.com" OR "no match",
  "name": "Contact Name" OR "",
  "confidence": 0.0-1.0,
  "reasoning": "Explain your decision clearly",
  "alternatives": []
}

BE EXTREMELY CONSERVATIVE - it's better to say "no match" than to match the wrong person!`;

    // Implement timeout for OpenAI API calls
    const openaiResponsePromise = openaiClient.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [{role: "user", content: prompt}],
      max_tokens: 500,
      temperature: 0.1, // Lower temperature for more consistent results
    });

    const openaiResponse = await Promise.race([
      openaiResponsePromise,
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('OpenAI API timeout for contact matching')), 10000)
      )
    ]);

    try {
      const rawText = openaiResponse.choices[0].message.content.trim();
      const jsonRegex = /\{[\s\S]*\}/;
      const jsonMatch = rawText.match(jsonRegex);

      if (jsonMatch) {
        let jsonText = jsonMatch[0].trim();
        // Minimal cleaning: remove control characters that might break parsing.
        jsonText = jsonText.replace(/[\u0000-\u001F\u007F-\u009F]/g, '');
        
        const result = JSON.parse(jsonText);
        console.log('OpenAI contact matching result:', result);
        
        // ADDITIONAL VALIDATION: Double-check the AI's decision
        if (result.email && result.email !== "no match") {
          const recipientLower = recipientHint.toLowerCase().trim();
          const resultNameLower = (result.name || '').toLowerCase().trim();
          
          // Check if names are actually similar enough
          const isValidMatch = validateContactMatch(recipientLower, resultNameLower);
          
          if (!isValidMatch) {
            console.warn(`[VALIDATION FAILED] Rejected AI match: "${recipientHint}" → "${result.name}" (not similar enough)`);
            return {
              email: "no match",
              name: "",
              confidence: 0,
              reasoning: `Validation rejected: "${recipientHint}" and "${result.name}" are not similar enough to be the same person.`,
              alternatives: []
            };
          }
          
          // Validate the email is in the expected format
          const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
          if (!result.email.includes('@') || !emailRegex.test(result.email)) {
            console.warn('Invalid email format returned from OpenAI by findBestContactMatch:', result.email);
            return null;
          }
          
          // Ensure confidence is a number between 0 and 1
          result.confidence = typeof result.confidence === 'number' ? 
            Math.min(Math.max(result.confidence, 0), 1) : 0.5;
            
          // Ensure alternatives is an array
          result.alternatives = Array.isArray(result.alternatives) ? 
            result.alternatives.filter(alt => typeof alt === 'string' && alt.includes('@')) : [];
            
          return result;
        }
        return null;
      } else {
        console.error('No JSON object found in OpenAI response for findBestContactMatch. Raw text:', rawText);
        return null;
      }
    } catch (parseError) {
      console.error('Error parsing OpenAI JSON response in findBestContactMatch:', parseError, 'Raw text:', openaiResponse.choices[0].message.content.trim());
      
      // Fallback: try to extract email directly from raw text if parsing fails
      try {
        const emailMatch = openaiResponse.choices[0].message.content.trim().match(/["']email["']\s*:\s*["']([^"']+@[^"']+)["']/i);
        if (emailMatch && emailMatch[1] && emailMatch[1].includes('@') && emailMatch[1] !== "no match") {
          
          // Validate the fallback match too
          const recipientLower = recipientHint.toLowerCase().trim();
          const extractedEmail = emailMatch[1].toLowerCase();
          const emailName = extractedEmail.split('@')[0];
          
          if (!validateContactMatch(recipientLower, emailName)) {
            console.warn(`[FALLBACK VALIDATION FAILED] Rejected fallback match: "${recipientHint}" → "${emailName}"`);
            return null;
          }
          
          return {
            email: emailMatch[1],
            name: recipientHint,
            confidence: 0.6,
            reasoning: "Extracted via regex from malformed/non-JSON OpenAI response (validated)",
            alternatives: []
          };
        }
      } catch (extractError) {
        console.error('Error extracting email via regex from OpenAI response in findBestContactMatch:', extractError);
      }
      
      return null;
    }
  } catch (error) {
    console.error('Error in findBestContactMatch with OpenAI:', error);
    return null;
  }
}

/**
 * Validate if two names are similar enough to be considered a match
 * @param {string} recipientName - Name the user specified
 * @param {string} contactName - Name from contact list
 * @returns {boolean} - True if names are similar enough
 */
function validateContactMatch(recipientName, contactName) {
  if (!recipientName || !contactName) return false;
  
  const recipient = recipientName.toLowerCase().trim();
  const contact = contactName.toLowerCase().trim();
  
  // Exact match only
  if (recipient === contact) return true;
  
  // Very minor spelling differences ONLY (1 character difference)
  if (Math.abs(recipient.length - contact.length) <= 1) {
    let differences = 0;
    const minLen = Math.min(recipient.length, contact.length);
    
    // Count character differences
    for (let i = 0; i < minLen; i++) {
      if (recipient[i] !== contact[i]) differences++;
    }
    
    // Add length difference to differences count
    differences += Math.abs(recipient.length - contact.length);
    
    // Allow only 1 character difference for names of reasonable length (4+ chars)
    if (differences <= 1 && minLen >= 4) {
      return true;
    }
  }
  
  // Strict rejection - NO abbreviations, NO partial matches, NO nicknames
  return false;
}

module.exports = {
  detectIntentWithOpenAI,
  generateSubjectWithOpenAI,
  findBestContactMatch,
  openaiClient
}; 
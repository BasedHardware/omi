const OpenAI = require('openai');
const { 
  storeEmailContact, 
  getLastQueriesAndResponses, 
  storeQuery, 
  storeResponse 
} = require('./supabaseUtils');

// Initialize OpenAI client
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY || 'YOUR_OPENAI_API_KEY'
});


/**
 * Determine the type of action to take based on the user query
 * @param {string} query - The user's query
 * @returns {string} - Action type (fetch_emails, draft_email, search)
 */
async function determineAction(query) {
  try {
    // Use OpenAI to classify the action
    const examples = [
      { text: "show me emails from John", label: "fetch_emails" },
      { text: "find emails about project deadline", label: "fetch_emails" },
      { text: "get my recent messages", label: "fetch_emails" },
      { text: "search for invoice emails", label: "fetch_emails" },
      { text: "draft an email to the team about the meeting", label: "draft_email" },
      { text: "write a message to Sarah about the project update", label: "draft_email" },
      { text: "compose a response to the client", label: "draft_email" },
      { text: "what is the weather today", label: "search" },
      { text: "who is the president of France", label: "search" },
      { text: "when was the first iPhone released", label: "search" },
      { text: "how to make pancakes", label: "search" }
    ];

    const messages = [
      {
        role: "system",
        content: `You are a classification assistant. Classify the user's query into one of the following categories: fetch_emails, draft_email, or search. Respond with only the category label. Examples:\n${examples.map(ex => `Query: ${ex.text}\nCategory: ${ex.label}`).join('\n')}`
      },
      {
        role: "user",
        content: query
      }
    ];

    const response = await openai.chat.completions.create({
      model: "gpt-3.5-turbo", // Or another suitable model
      messages: messages,
      max_tokens: 10,
      temperature: 0
    });

    const classification = response.choices[0].message.content.trim();
    console.log(`Action classification: ${classification}`);
    
    // Basic validation of the classification
    const validLabels = ["fetch_emails", "draft_email", "search"];
    if (validLabels.includes(classification)) {
      return classification;
    } else {
      console.warn('OpenAI classification returned an invalid label:', classification);
      return 'search'; // Fallback
    }

  } catch (error) {
    console.error('Error determining action:', error);
    return 'search'; // Default to search as fallback
  }
}

/**
 * Get email response based on query
 * @param {string} query - User's query about emails
 * @param {string} uid - User ID
 * @returns {string} - Response with email information
 */
async function getEmailResponse(query, uid) {
  // This would connect to your email service
  // For demonstration purposes:
  return "I found several emails matching your query. The most recent one is from yesterday about the project update.";
}

/**
 * Draft an email based on user instructions
 * @param {string} instructions - User's email drafting instructions
 * @param {string} uid - User ID
 * @returns {string} - Confirmation of email draft
 */
async function draftEmail(instructions, uid) {
  // This would connect to your email composition service
  // For demonstration purposes:
  return "I've drafted an email based on your instructions. You can review and send it from your drafts folder.";
}

/**
 * Search for information using OpenAI
 * @param {string} query - User's search query
 * @returns {string} - Search results
 */
async function searchLikeEngine(query) {
  try {
    // Use OpenAI to generate a search response
    const response = await openai.generate({
      prompt: `Act as a search engine. Given a query, provide a concise, direct response in a search-engine style.
      For date context, today is ${new Date().toISOString().split('T')[0]}.
      Follow these rules:
      1. Start with the most relevant information
      2. Use bullet points for multiple pieces of information
      3. Keep responses as short and simple as possible while being correct
      4. Include only essential details
      5. Don't use first person or conversational language
      
      Query: ${query}
      
      Response:`,
      model: 'command',
      max_tokens: 300,
      temperature: 0.7,
    });

    return response.generations[0].text.trim();
  } catch (error) {
    console.error('Error searching:', error);
    return "I couldn't find information about that.";
  }
}

/**
 * Process a query from the webhook
 * @param {string} sessionId - Session ID
 * @param {string} fullQuestion - Complete question from user
 * @param {string} uid - User ID
 * @returns {string} - Response to the user's query
 */
async function processQuery(sessionId, fullQuestion, uid) {
  console.log(`Processing query: ${fullQuestion}`);
  
  // Check for recent conversations for context
  const { lastQueries, lastResponses } = await getLastQueriesAndResponses(sessionId, 60);
  let actionInstructions = fullQuestion;
  
  if (lastQueries && lastQueries.length > 0 && lastResponses && lastResponses.length > 0) {
    // Use OpenAI to combine context from previous conversation
    const response = await openai.generate({
      prompt: `You will be given previous queries, their responses, and a new query. 
      Determine if the new query is related to the previous queries and responses. They are related only if the current query depends on the previous queries or responses.
      If they are related, combine them to a single query that should make sense. Fix any typos if any.
      The combined query should have the complete context and it should sound like as if the user sent it.
      Do not add anything to the combined query on your own. It should exactly be what the user wants.
      
      Previous Queries: ${JSON.stringify(lastQueries)}
      Previous Responses: ${JSON.stringify(lastResponses)}
      Current Query: ${fullQuestion}
      
      Combined query:`,
      model: 'command',
      max_tokens: 300,
      temperature: 0.7,
    });
    
    actionInstructions = response.generations[0].text.trim();
    console.log(`Action instructions from OpenAI: ${actionInstructions}`);
  }
  
  // Determine the action type
  const action = await determineAction(actionInstructions);
  console.log(`Determined action: ${action}`);
  
  let response;
  switch (action) {
    case 'fetch_emails':
      response = await getEmailResponse(fullQuestion, uid);
      break;
    case 'draft_email':
      response = await draftEmail(actionInstructions, uid);
      break;
    case 'search':
      response = await searchLikeEngine(actionInstructions);
      break;
    default:
      response = "I'm not sure how to help with that request.";
  }
  
  console.log(`Response: ${response}`);
  
  // Store the current query and response in Supabase
  await storeQuery(sessionId, fullQuestion);
  await storeResponse(sessionId, response);
  
  return response;
}

module.exports = {
  storeEmailContact,
  determineAction,
  getEmailResponse,
  draftEmail,
  searchLikeEngine,
  processQuery
}; 
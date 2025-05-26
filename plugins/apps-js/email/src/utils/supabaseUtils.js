const { createClient } = require('@supabase/supabase-js');
const { v4: uuidv4 } = require('uuid');
require('dotenv').config();

// Initialize Supabase client
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.error('Missing Supabase credentials. Please check your .env file.');
}

const supabase = createClient(supabaseUrl, supabaseKey, {
  auth: {
    persistSession: false,
  }
});

/**
 * Fetch a user by their ID (Omi device UID)
 * @param {string} userId - User ID (Omi device UID) to find
 * @returns {Promise<Object|null>} - The found user or null
 */
async function fetchUserById(userId) {
  try {
    const { data, error } = await supabase
      .from('users')
      .select('*')
      .eq('id', userId)
      .single();

    if (error && error.code !== 'PGRST116') { // PGRST116 is 'No rows found'
        console.error('Error fetching user by ID (PGRST116 means not found):', error.message);
        throw error; 
    }
    return data; // Will be null if not found and error code is PGRST116
  } catch (error) {
    // Log non-PGRST116 errors or re-throw if preferred
    if (error.code !== 'PGRST116') {
        console.error('Serious error fetching user by ID:', error);
    }
    return null;
  }
}

/**
 * Fetch a user by their Google ID
 * @param {string} googleId - User's Google ID (sub)
 * @returns {Promise<Object|null>} - The found user or null
 */
async function fetchUserByGoogleId(googleId) {
  try {
    if (!googleId) {
      console.warn('fetchUserByGoogleId called with no googleId');
      return null;
    }
    const { data, error } = await supabase
      .from('users')
      .select('*')
      .eq('google_id', googleId)
      .single();

    if (error && error.code !== 'PGRST116') { 
        console.error('Error fetching user by Google ID:', error.message);
        throw error; 
    }
    return data; // null if not found and error is PGRST116
  } catch (error) {
    if (error.code !== 'PGRST116') {
        console.error('Serious error fetching user by Google ID:', error);
    }
    return null;
  }
}


/**
 * Create or update a user based on Google Profile information.
 * User is looked up by google_id. If not found, a new user is created with omiuid as id.
 * @param {Object} userData - User info from Google with tokens and id
 * @returns {Promise<Object|null>} - The upserted user object from database
 */
async function upsertUser(userData) {
  try {
    if (!userData.id) {
      console.error('upsertUser error: id is required');
      return null;
    }

    if (!userData.google_id) {
      console.error('upsertUser error: google_id is missing');
      return null;
    }

    // Check if the user exists already
    let existingUser = null;
    try {
      const { data, error } = await supabase
        .from('users')
        .select('*')
        .eq('user_id', userData.id)
        .single();
      
      if (!error) {
        existingUser = data;
      }
      
      // If not found by user_id, try to find by google_id
      if (!existingUser) {
        const { data: googleData, error: googleError } = await supabase
          .from('users')
          .select('*')
          .eq('google_id', userData.google_id)
          .single();
        
        if (!googleError) {
          existingUser = googleData;
        }
      }
    } catch (lookupError) {
      console.log('User lookup error (non-critical):', lookupError);
    }

    // Prepare user data
    const userRecord = {
      user_id: userData.id, // Firebase UID goes in user_id field
      google_id: userData.google_id,
      email: userData.email,
      name: userData.name,
      picture: userData.picture,
      token: userData.token,
      refresh_token: userData.refresh_token,
      token_expiry: userData.token_expiry,
      token_uri: userData.token_uri || 'https://oauth2.googleapis.com/token', // Add token_uri with fallback
      client_id: userData.client_id || process.env.GOOGLE_CLIENT_ID, // Add client_id with env var fallback
      scopes: userData.scopes || [],
      last_login: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    // If existing user, use that ID
    if (existingUser) {
      userRecord.id = existingUser.id; // Use existing UUID
    } else {
      userRecord.id = uuidv4(); // Generate new UUID for id field
    }

    // Upsert user
    const { data, error } = await supabase
      .from('users')
      .upsert(userRecord)
      .select()
      .single();

    if (error) {
      console.error('Error in upsertUser:', error);
      return null;
    }

    return data;
  } catch (error) {
    console.error('Error in upsertUser final catch:', error);
    return null;
  }
}

/**
 * Store an email contact
 * @param {string} userId - User ID (Omi device UID)
 * @param {string} email - Contact email
 * @param {string} name - Contact name (optional)
 * @param {string} context - Contact context (optional)
 * @returns {Promise<Object|null>} - The stored contact
 */
async function storeEmailContact(userId, email, name = null, context = null) {
  try {
    if (!userId || !email) {
      console.error('Missing required parameters:', { userId, email });
      return null;
    }

    const contactData = {
      user_id: userId,
      email: email.toLowerCase(),
      name,
      context,
      last_used: new Date().toISOString()
    };

    // Try to update existing contact first
    const { data: existingContact, error: selectError } = await supabase
      .from('email_contacts')
      .select('*')
      .eq('user_id', userId)
      .eq('email', email.toLowerCase())
      .single();

    if (selectError && selectError.code !== 'PGRST116') { // PGRST116 means no rows found
      console.error('Error checking for existing contact:', selectError);
      return null;
    }

    if (existingContact) {
      // Update existing contact
      const { data, error } = await supabase
        .from('email_contacts')
        .update({
          ...contactData,
          usage_count: existingContact.usage_count + 1
        })
        .eq('id', existingContact.id)
        .select()
        .single();

      if (error) {
        console.error('Error updating email contact:', error);
        return null;
      }

      return data;
    } else {
      // Insert new contact
      const { data, error } = await supabase
        .from('email_contacts')
        .insert({
          ...contactData,
          usage_count: 1,
          first_used: new Date().toISOString()
        })
        .select()
        .single();

      if (error) {
        console.error('Error inserting email contact:', error);
        return null;
      }

      return data;
    }
  } catch (error) {
    console.error('Error in storeEmailContact:', error);
    return null;
  }
}

/**
 * Store message in conversation history
 * @param {string} sessionId - Session ID
 * @param {string} role - Message role (user or assistant)
 * @param {string} content - Message content
 * @returns {Promise<Object|null>} - The stored message
 */
async function storeMessage(sessionId, role, content) {
  try {
    const { data, error } = await supabase
      .from('messages')
      .insert({
        session_id: sessionId,
        role: role,
        content: content,
        timestamp: new Date().toISOString()
      })
      .select();

    if (error) throw error;
    return data ? data[0] : null;
  } catch (error) {
    console.error('Error storing message:', error);
    return null;
  }
}

/**
 * Get last queries and responses within a time window for context
 * @param {string} sessionId - Session ID
 * @param {number} timeWindow - Time window in seconds (default 60s)
 * @returns {Promise<Object>} - Object with lastQueries and lastResponses arrays
 */
async function getLastQueriesAndResponses(sessionId, timeWindow = 60) {
  try {
    const since = new Date(Date.now() - timeWindow * 1000).toISOString();
    const { data, error } = await supabase
      .from('messages')
      .select('role, content')
      .eq('session_id', sessionId)
      .gte('timestamp', since)
      .order('timestamp', { ascending: true }); // Get in chronological order

    if (error) throw error;

    const lastQueries = [];
    const lastResponses = [];
    if (data) {
      data.forEach(msg => {
        if (msg.role === 'user') lastQueries.push(msg.content);
        if (msg.role === 'assistant') lastResponses.push(msg.content);
      });
    }
    return { lastQueries, lastResponses };
  } catch (error) {
    console.error('Error fetching last queries/responses:', error);
    return { lastQueries: [], lastResponses: [] };
  }
}

/**
 * Store a user query (simplified, assumes message table stores this)
 * @param {string} sessionId - Session ID
 * @param {string} query - User's query
 */
async function storeQuery(sessionId, query) {
  return storeMessage(sessionId, 'user', query);
}

/**
 * Store an assistant response (simplified, assumes message table stores this)
 * @param {string} sessionId - Session ID
 * @param {string} response - Assistant's response
 */
async function storeResponse(sessionId, response) {
  return storeMessage(sessionId, 'assistant', response);
}

module.exports = {
  supabase,
  fetchUserById,
  fetchUserByGoogleId,
  upsertUser,
  storeEmailContact,
  storeMessage,
  getLastQueriesAndResponses,
  storeQuery,
  storeResponse
}; 
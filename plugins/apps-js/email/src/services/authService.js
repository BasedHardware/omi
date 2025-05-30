const { createClient } = require('@supabase/supabase-js');

// Initialize Supabase client
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.error('Missing Supabase credentials. Please check your .env file.');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey, {
  auth: {
    persistSession: false,
  }
});

/**
 * Get authenticated user from Supabase
 * @param {string} userId - The user ID to authenticate (Omi UID)
 * @returns {object} The authenticated user object
 * @throws {Error} If authentication fails
 */
async function getAuthenticatedUser(userId) {
  try {
    console.log(`[AUTH] Looking up user with ID: ${userId}`);
    
    // Primary lookup: Try to find by user_id field (which contains Omi UID)
    let { data, error } = await supabase
      .from('users')
      .select('*')
      .eq('user_id', userId)
      .single();
    
    if (data && !error) {
      console.log(`[AUTH] Found user by user_id: ${data.email} (${data.name})`);
    } else {
      console.log(`[AUTH] User not found by user_id, trying other fields...`);
      
      // Fallback 1: Try to find by email if userId looks like an email
      if (userId.includes('@')) {
        ({ data, error } = await supabase
          .from('users')
          .select('*')
          .eq('email', userId)
          .single());
        
        if (data && !error) {
          console.log(`[AUTH] Found user by email: ${data.email}`);
        }
      }
      
      // Fallback 2: Try numeric ID lookup (legacy support)
      if (!data || error) {
        const numericId = parseInt(userId);
        if (!isNaN(numericId) && String(numericId) === userId) {
          ({ data, error } = await supabase
            .from('users')
            .select('*')
            .eq('id', numericId)
            .single());
          
          if (data && !error) {
            console.log(`[AUTH] Found user by numeric id: ${data.email}`);
          }
        }
      }
    }
      
    if (error) {
      console.error(`[AUTH] User fetch error: ${error.message}`);
      throw new Error(`User fetch error: ${error.message}`);
    }
    
    if (!data) {
      console.error(`[AUTH] User not found for ID: ${userId}`);
      throw new Error('User not found. Please connect your Gmail account first.');
    }
    
    // Check if token is expired
    if (data.token_expiry && new Date() >= new Date(data.token_expiry)) {
      console.error(`[AUTH] Token expired for user: ${data.email}`);
      throw new Error('Gmail authentication expired. Please reconnect your account.');
    }
    
    // Ensure all required fields exist
    data.user_id = data.user_id || data.id;
    data.id = data.id || data.user_id;
    
    console.log(`[AUTH] Successfully authenticated user: ${data.email} (${data.name})`);
    return data;
  } catch (error) {
    console.error(`[AUTH] Error fetching user for ${userId}:`, error);
    throw error;
  }
}

/**
 * Check Supabase connection
 */
async function checkSupabaseConnection() {
  try {
    const { data, error } = await supabase.from('users').select('count').limit(1);
    if (error) {
      console.error('Supabase connection error:', error);
      return false;
    } else {
      console.log('Supabase connected successfully');
      return true;
    }
  } catch (error) {
    console.error('Error checking Supabase connection:', error);
    return false;
  }
}

/**
 * Process query function (legacy support)
 * @param {string} sessionId - The session ID
 * @param {string} query - The query to process
 * @param {string} uid - The user ID
 * @returns {string} Query processing result
 */
async function processQuery(sessionId, query, uid) {
  try {
    // Get user data from Supabase
    await getAuthenticatedUser(uid);
    
    // Process query with your existing logic
    // ...
    
    return "Query processed successfully";
  } catch (error) {
    console.error('Error processing query:', error);
    return `Error: ${error.message}`;
  }
}

module.exports = {
  getAuthenticatedUser,
  checkSupabaseConnection,
  processQuery,
  supabase
}; 
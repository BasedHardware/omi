const { google } = require('googleapis');
const jwt = require('jsonwebtoken');
const { upsertUser, fetchUserById, supabase } = require('./supabaseUtils');
require('dotenv').config();

// OAuth2 client setup
const oauth2Client = new google.auth.OAuth2(
  process.env.GOOGLE_CLIENT_ID,
  process.env.GOOGLE_CLIENT_SECRET,
  process.env.GOOGLE_CALLBACK_URL
);

/**
 * Get Google Auth URL
 * @param {string} state - Optional Oauth state parameter
 * @returns {string} - Authorization URL
 */
function getAuthUrl(state) {
  const scopes = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/contacts.readonly',
    'https://www.googleapis.com/auth/contacts.other.readonly',
    'https://www.googleapis.com/auth/directory.readonly'
  ];

  return oauth2Client.generateAuthUrl({
    access_type: 'offline',
    scope: scopes,
    prompt: 'consent',
    state: state
  });
}

/**
 * Fetch and store user's contacts during authentication
 * @param {Object} user - User data
 * @returns {Promise<void>}
 */
async function fetchAndStoreContacts(user) {
  try {
    console.log(`[${user.id}] Fetching contacts during authentication...`);
    if (!supabase) {
      console.error(`[${user.id}] Supabase client not available in fetchAndStoreContacts.`);
      return;
    }
    const auth = await getGoogleClient(user);
    const gmail = google.gmail({ version: 'v1', auth });
    const people = google.people({ version: 'v1', auth });

    // Fetch contacts from People API
    const contactsResponse = await people.people.connections.list({
      resourceName: 'people/me',
      pageSize: 1000,
      personFields: 'names,emailAddresses'
    });

    const contacts = (contactsResponse.data.connections || [])
      .filter(person => person.emailAddresses && person.emailAddresses.length > 0)
      .map(person => ({
        user_id: user.id,
        email: person.emailAddresses[0].value,
        name: person.names ? person.names[0].displayName : person.emailAddresses[0].value.split('@')[0],
        context: 'contacts',
        usage_count: 1,
        first_used: new Date().toISOString(),
        last_used: new Date().toISOString()
      }));

    // Fetch recent emails (last 6 months)
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
    
    const emailResponse = await gmail.users.messages.list({
      userId: 'me',
      q: `after:${Math.floor(sixMonthsAgo.getTime() / 1000)}`,
      maxResults: 500
    });

    if (emailResponse.data.messages) {
      const emailSet = new Set();
      const nameEmailMap = new Map();

      for (const message of emailResponse.data.messages) {
        const details = await gmail.users.messages.get({
          userId: 'me',
          id: message.id,
          format: 'metadata',
          metadataHeaders: ['From', 'To', 'Cc']
        });

        const headers = details.data.payload.headers;
        ['From', 'To', 'Cc'].forEach(headerName => {
          const header = headers.find(h => h.name === headerName);
          if (header) {
            const emailRegex = /([^<\s@]+@[^>\s@]+\.[^>\s@]+)/g;
            const nameEmailRegex = /(?:"?([^"<]+)"?\s*)?<?([^<\s@]+@[^>\s@]+\.[^>\s@]+)>?/g;

            let match;
            while ((match = nameEmailRegex.exec(header.value)) !== null) {
              const [, name, email] = match;
              if (email && email !== user.email) {
                emailSet.add(email);
                if (name) {
                  nameEmailMap.set(email, name.trim());
                }
              }
            }
          }
        });
      }

      // Convert email contacts to array format
      const emailContacts = Array.from(emailSet).map(email => ({
        user_id: user.id,
        email: email,
        name: nameEmailMap.get(email) || email.split('@')[0],
        context: 'emails',
        usage_count: 1,
        first_used: new Date().toISOString(),
        last_used: new Date().toISOString()
      }));

      // Merge contacts from both sources
      contacts.push(...emailContacts);
    }

    // Store unique contacts in database
    if (contacts.length > 0) {
      const uniqueContacts = Array.from(
        new Map(contacts.map(contact => [contact.email, contact])).values()
      );

      const { error } = await supabase
        .from('email_contacts')
        .upsert(uniqueContacts, {
          onConflict: 'user_id,email',
          ignoreDuplicates: false
        });

      if (error) {
        console.error(`[${user.id}] Error storing contacts:`, error);
      } else {
        console.log(`[${user.id}] Successfully stored ${uniqueContacts.length} contacts`);
      }
    }
  } catch (error) {
    console.error(`[${user.id}] Error fetching and storing contacts:`, error);
  }
}

/**
 * Exchange code for tokens
 * @param {string} code - Authorization code
 * @param {string} omiuid - User's OMI UID from auth state
 * @returns {Promise<Object>} - Tokens
 */
async function getTokens(code, omiuid) {
  try {
    if (!omiuid) {
      throw new Error('omiuid is required for token exchange');
    }

    console.log('Getting tokens with code:', code);
    const { tokens } = await oauth2Client.getToken(code);
    console.log('Received tokens:', {
      access_token: tokens.access_token ? 'present' : 'missing',
      refresh_token: tokens.refresh_token ? 'present' : 'missing',
      expiry_date: tokens.expiry_date
    });

    // Set custom expiry date of one week from now
    const oneWeekFromNow = new Date();
    oneWeekFromNow.setDate(oneWeekFromNow.getDate() + 7);
    const customExpiryDate = oneWeekFromNow.getTime();
    
    console.log('Setting custom token expiry date:', {
      originalExpiry: new Date(tokens.expiry_date).toISOString(),
      newExpiry: new Date(customExpiryDate).toISOString(),
      extensionDays: 7
    });

    // Get user info to create/update user record
    oauth2Client.setCredentials(tokens);
    const userInfo = await getUserInfo(tokens.access_token);
    
    // Create/update user record with omiuid and custom expiry
    const user = await upsertUserRecord({
      ...userInfo,
      id: omiuid, // Use omiuid as the primary id
      google_id: userInfo.id, // Pass the Google ID
      token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      token_expiry: new Date(customExpiryDate).toISOString(), // Use our custom extended expiry
      last_login: new Date().toISOString() // Track authentication time for 6-month reverification
    });

    // Fetch and store contacts after user is created/updated
    if (user) {
      // Run fetchAndStoreContacts in the background, don't await it here
      // to make the auth callback respond faster.
      fetchAndStoreContacts(user).catch(error => {
        console.error(`[BACKGROUND_CONTACT_SYNC_ERROR] User ID ${user.id}:`, error.message);
      });
      console.log(`[${user.id}] Triggered background contact sync.`);
    } else {
      console.error('[GET_TOKENS] Failed to create/update user record, cannot trigger contact sync.');
    }

    // Return tokens with custom expiry
    return {
      ...tokens,
      expiry_date: customExpiryDate // Override with our custom expiry
    };
  } catch (error) {
    console.error('Error getting tokens:', error);
    throw error;
  }
}

/**
 * Get user info from Google
 * @param {string} accessToken - Access token
 * @returns {Promise<Object>} - User info
 */
async function getUserInfo(accessToken) {
  try {
    console.log('Getting user info with access token');
    const oauth2 = google.oauth2({
      auth: oauth2Client,
      version: 'v2'
    });
    
    oauth2Client.setCredentials({ access_token: accessToken });
    
    const { data } = await oauth2.userinfo.get();
    console.log('User info response (raw data from Google):', data);
    console.log('User info fields check:', {
      email: data.email,
      name: data.name,
      picture: data.picture ? 'present' : 'missing',
      sub_is_present: data.hasOwnProperty('sub'),
      id_is_present: data.hasOwnProperty('id'),
      retrieved_sub: data.sub,
      retrieved_id: data.id
    });
    return data;
  } catch (error) {
    console.error('Error getting user info:', error);
    throw error;
  }
}

/**
 * Create or update user in Supabase
 * @param {Object} userData - User data
 * @returns {Promise<Object>} - User data
 */
async function upsertUserRecord(userData) {
  try {
    if (!userData.id) {
      throw new Error('id is required');
    }

    console.log('Upserting user with data:', {
      id: userData.id,
      email: userData.email,
      name: userData.name,
      google_id: userData.google_id
    });
    
    return await upsertUser(userData);
  } catch (error) {
    console.error('Error in upsertUser:', error);
    throw error;
  }
}

/**
 * Generate JWT token for user
 * @param {Object} user - User data
 * @returns {string} - JWT token
 */
function generateToken(user) {
  try {
    if (!user) {
      throw new Error('User data is null or undefined');
    }
    
    const payload = {
      id: user.id,
      email: user.email,
      name: user.name
    };
    
    return jwt.sign(payload, process.env.JWT_SECRET || 'your-secret-key', {
      expiresIn: '7d'
    });
  } catch (error) {
    console.error('Error generating token:', error);
    throw error;
  }
}

/**
 * Check if user needs reverification (6 months since last auth)
 * @param {Object} user - User data
 * @returns {boolean} - True if reverification is needed
 */
function needsReverification(user) {
  if (!user.last_login && !user.createdAt) {
    return true; // No login date recorded, require reverification
  }
  
  const lastAuthDate = new Date(user.last_login || user.createdAt);
  const sixMonthsAgo = new Date();
  sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
  
  const needsReauth = lastAuthDate < sixMonthsAgo;
  
  console.log('Reverification check:', {
    userId: user.id || user.user_id,
    lastAuthDate: lastAuthDate.toISOString(),
    sixMonthsAgo: sixMonthsAgo.toISOString(),
    needsReverification: needsReauth
  });
  
  return needsReauth;
}

/**
 * Refresh access token
 * @param {Object} user - User data
 * @returns {Promise<string>} - New access token
 */
async function refreshAccessToken(user) {
  try {
    // Check if user needs reverification (6 months)
    if (needsReverification(user)) {
      console.warn(`[${user.id || user.user_id}] User needs reverification - 6 months since last auth`);
      throw new Error('REVERIFICATION_REQUIRED');
    }

    oauth2Client.setCredentials({
      refresh_token: user.refresh_token
    });
    
    const { credentials } = await oauth2Client.refreshAccessToken();
    const newAccessToken = credentials.access_token;
    
    // Set custom expiry date of one week from now
    const oneWeekFromNow = new Date();
    oneWeekFromNow.setDate(oneWeekFromNow.getDate() + 7);
    const customExpiryDate = oneWeekFromNow.getTime();
    
    console.log('Setting custom token expiry on refresh:', {
      userId: user.id || user.user_id,
      originalExpiry: new Date(credentials.expiry_date).toISOString(),
      newExpiry: new Date(customExpiryDate).toISOString(),
      extensionDays: 7
    });
    
    // Update user with new token, custom expiry, and last_login
    await upsertUser({
      ...user,
      token: newAccessToken,
      token_expiry: new Date(customExpiryDate).toISOString(),
      last_login: new Date().toISOString() // Update last login time
    });
    
    return newAccessToken;
  } catch (error) {
    console.error('Error refreshing access token:', error);
    
    // Handle specific refresh token errors that indicate need for reverification
    if (error.message?.includes('invalid_grant') || 
        error.message?.includes('Token has been expired or revoked') ||
        error.code === 400 ||
        error.message === 'REVERIFICATION_REQUIRED') {
      console.warn(`[${user.id || user.user_id}] Refresh token invalid or expired - reverification required`);
      throw new Error('REVERIFICATION_REQUIRED');
    }
    
    throw error;
  }
}

/**
 * Get Google client for API calls
 * @param {Object} user - User data
 * @returns {Promise<OAuth2Client>} - Authenticated OAuth2 client
 */
async function getGoogleClient(user) {
  try {
    // Check if token is expired
    const tokenExpiry = new Date(user.token_expiry);
    const now = new Date();
    
    if (now >= tokenExpiry) {
      // Token is expired, refresh it
      const newAccessToken = await refreshAccessToken(user);
      oauth2Client.setCredentials({
        access_token: newAccessToken,
        refresh_token: user.refresh_token
      });
    } else {
      // Token is still valid
      oauth2Client.setCredentials({
        access_token: user.token,
        refresh_token: user.refresh_token
      });
    }
    
    return oauth2Client;
  } catch (error) {
    console.error('Error getting Google client:', error);
    
    // If reverification is required, provide a clear error message
    if (error.message === 'REVERIFICATION_REQUIRED') {
      console.warn(`[${user.id || user.user_id}] User needs to re-authenticate - 6 months since last auth or refresh token expired`);
      throw new Error('REVERIFICATION_REQUIRED');
    }
    
    throw error;
  }
}

/**
 * Update user's tokens
 * @param {string} userId - User ID
 * @param {Object} tokenData - Token data
 * @returns {Promise<Object>} - Updated token data
 */
async function updateTokens(userId, tokenData) {
  try {
    const user = await fetchUserById(userId);
    if (!user) {
      throw new Error('User not found');
    }
    
    // Check if user needs reverification (6 months)
    if (needsReverification(user)) {
      console.warn(`[${userId}] User needs reverification during token update - 6 months since last auth`);
      throw new Error('REVERIFICATION_REQUIRED');
    }
    
    // Refresh the token if needed
    oauth2Client.setCredentials({
      refresh_token: tokenData.refreshToken || user.refresh_token
    });
    
    const { credentials } = await oauth2Client.refreshAccessToken();
    
    // Set custom expiry date of one week from now
    const oneWeekFromNow = new Date();
    oneWeekFromNow.setDate(oneWeekFromNow.getDate() + 7);
    const customExpiryDate = oneWeekFromNow.getTime();
    
    console.log('Setting custom token expiry on update:', {
      userId,
      originalExpiry: new Date(credentials.expiry_date).toISOString(),
      newExpiry: new Date(customExpiryDate).toISOString(),
      extensionDays: 7
    });
    
    // Update user with new tokens, custom expiry, and last_login
    const updatedUser = await upsertUser({
      ...user,
      token: credentials.access_token,
      refresh_token: credentials.refresh_token || user.refresh_token,
      token_expiry: new Date(customExpiryDate).toISOString(),
      last_login: new Date().toISOString() // Update last login time
    });
    
    return {
      accessToken: credentials.access_token,
      refreshToken: credentials.refresh_token || user.refresh_token,
      expiryDate: customExpiryDate // Return custom extended expiry date
    };
  } catch (error) {
    console.error('Error updating tokens:', error);
    
    // Handle specific refresh token errors that indicate need for reverification
    if (error.message?.includes('invalid_grant') || 
        error.message?.includes('Token has been expired or revoked') ||
        error.code === 400 ||
        error.message === 'REVERIFICATION_REQUIRED') {
      console.warn(`[${userId}] Refresh token invalid or expired during update - reverification required`);
      throw new Error('REVERIFICATION_REQUIRED');
    }
    
    throw error;
  }
}

module.exports = {
  getAuthUrl,
  getTokens,
  getUserInfo,
  upsertUser: upsertUserRecord,
  generateToken,
  refreshAccessToken,
  getGoogleClient,
  updateTokens,
  fetchAndStoreContacts,
  needsReverification
}; 
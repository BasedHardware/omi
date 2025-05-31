const express = require('express');
const router = express.Router();
const { body, validationResult } = require('express-validator');
const jwt = require('jsonwebtoken');
const crypto = require('crypto'); // Added for generating random state
const { redis, isConnected, initializeRedis } = require('../utils/redisUtils'); // Added isConnected and initializeRedis
const {
  getAuthUrl,
  getTokens,
  getUserInfo,
  generateToken,
  refreshAccessToken,
  updateTokens
} = require('../utils/googleAuth');
const { upsertUser: supabaseUpsertUser, fetchUserById } = require('../utils/supabaseUtils');
const auth = require('../middleware/auth');
const { getEmailContacts } = require('../utils/emailUtils'); // Added getEmailContacts import
const { v4: uuidv4 } = require('uuid'); // Already have crypto, but if needed for other state generation

// Add logging utility
const logAuth = (type, data) => {
  const timestamp = new Date().toISOString();
  console.log(`[AUTH ${type}] ${timestamp}:`, JSON.stringify(data, null, 2));
};

// Error handler wrapper
const asyncHandler = fn => (req, res, next) => {
  return Promise.resolve(fn(req, res, next)).catch(next);
};

// Middleware to verify JWT token
const verifyToken = (req, res, next) => {
  const token = req.headers.authorization?.split(' ')[1];
  logAuth('TOKEN_VERIFY', { 
    hasToken: !!token,
    headers: req.headers
  });
  
  if (!token) {
    return res.status(401).json({ error: 'No token provided' });
  }

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    logAuth('TOKEN_VERIFIED', { userId: decoded.id });
    req.user = decoded;
    next();
  } catch (error) {
    logAuth('TOKEN_ERROR', { error: error.message });
    return res.status(401).json({ error: 'Invalid token' });
  }
};

// Validate Omi device UID format
const isValidOmiUid = (uid) => {
  // Accept any non-empty string
  return typeof uid === 'string' && uid.length > 0;
};

// Login route - redirects to Google OAuth
router.get('/login/:omiuid?', asyncHandler(async (req, res) => {
  try {
    // Check both query parameter and route parameter for omiuid
    const omiuid = req.query.uid || req.params.omiuid;
    
    logAuth('LOGIN_START', {
      ip: req.ip,
      userAgent: req.headers['user-agent'],
      headers: req.headers,
      omiuid: omiuid || null,
      source: req.query.uid ? 'query' : (req.params.omiuid ? 'route' : 'none'),
      url: req.originalUrl,
      query: req.query
    });

    // Validate Omi UID if provided
    if (omiuid) {
      if (!isValidOmiUid(omiuid)) {
        logAuth('INVALID_OMI_UID', { omiuid });
        return res.status(400).json({ error: 'Invalid Omi device UID format' });
      }
      logAuth('VALID_OMI_UID', { omiuid });
    } else {
      logAuth('NO_OMI_UID', { url: req.originalUrl, query: req.query });
    }

    const state = crypto.randomBytes(16).toString('hex');
    const redisKey = `oauth_state:${state}`;

    try {
      let redisReady = await isConnected();
      if (!redisReady) {
        logAuth('REDIS_CONNECT', { status: 'attempting_initialization' });
        await initializeRedis();
        redisReady = await isConnected();
        if (!redisReady) {
          throw new Error('Redis not connected after attempting initialization');
        }
      }
      
      // Store Omi UID with state if provided
      await redis.set(redisKey, JSON.stringify({ 
        ip: req.ip, 
        userAgent: req.headers['user-agent'],
        omiuid: omiuid || null,
        source: req.query.uid ? 'query' : (req.params.omiuid ? 'route' : 'none')
      }), 'EX', 600);
      
      logAuth('REDIS_STATE_SAVED', { state, redisKey, hasOmiUid: !!omiuid });
    } catch (redisError) {
      logAuth('REDIS_ERROR', { error: redisError.message });
      return res.status(500).json({ error: 'Failed to initiate authentication due to Redis error.' });
    }

    const authUrl = getAuthUrl(state);
    logAuth('REDIRECT_TO_GOOGLE', { authUrl, omiuid: omiuid || null });
    res.redirect(authUrl);
  } catch (error) {
    logAuth('LOGIN_ERROR', { error: error.message, stack: error.stack });
    res.status(500).json({ error: 'Login initiation failed: ' + error.message });
  }
}));

// OAuth callback
router.get('/callback/:omiuid?', asyncHandler(async (req, res) => {
  const { code, error, state: returnedState } = req.query;
  const { omiuid: routeOmiUid } = req.params;
  
  logAuth('CALLBACK_START', {
    hasCode: !!code,
    hasError: !!error,
    hasState: !!returnedState,
    routeOmiUid: routeOmiUid || null,
    ip: req.ip,
    headers: req.headers
  });

  if (error) {
    logAuth('CALLBACK_OAUTH_ERROR', { error });
    return res.redirect(`${process.env.BASE_URL || '/'}?error=${encodeURIComponent(error)}`);
  }

  if (!code || !returnedState) {
    logAuth('CALLBACK_MISSING_PARAMS', { code: !!code, state: !!returnedState });
    return res.status(400).json({ 
      error: !code ? 'Authorization code is required' : 'State parameter missing' 
    });
  }

  try {
    let redisReady = await isConnected();
    logAuth('REDIS_STATUS', { connected: redisReady });

    const storedStateDataJSON = await redis.get(`oauth_state:${returnedState}`);
    if (!storedStateDataJSON) {
      logAuth('STATE_VALIDATION_FAILED', { returnedState });
      return res.status(400).json({ error: 'Invalid or expired state' });
    }

    await redis.del(`oauth_state:${returnedState}`);
    const { ip: storedIp, userAgent: storedUserAgent, omiuid: storedOmiUid } = JSON.parse(storedStateDataJSON);
    
    // Use route omiuid if available, fallback to stored one
    const omiuid = routeOmiUid || storedOmiUid;
    
    if (!omiuid) {
      logAuth('MISSING_OMI_UID', { routeOmiUid, storedOmiUid });
      return res.status(400).json({ error: 'Missing Omi device UID' });
    }

    logAuth('STATE_VALIDATION', {
      storedIp,
      currentIp: req.ip,
      ipMatch: storedIp === req.ip,
      userAgentMatch: storedUserAgent === req.headers['user-agent'],
      hasOmiUid: !!omiuid,
      omiuidSource: routeOmiUid ? 'route' : (storedOmiUid ? 'state' : 'none')
    });

    // Get tokens and pass omiuid
    const tokens = await getTokens(code, omiuid);
    logAuth('TOKENS_RECEIVED', {
      hasAccessToken: !!tokens.access_token,
      hasRefreshToken: !!tokens.refresh_token,
      expiryDate: tokens.expiry_date
    });

    const googleProfile = await getUserInfo(tokens.access_token);
    logAuth('GOOGLE_PROFILE', {
      hasProfile: !!googleProfile,
      email: googleProfile.email,
      name: googleProfile.name,
      hasSub: !!googleProfile.sub
    });

    if (!googleProfile) {
      throw new Error('Failed to retrieve Google profile');
    }

    // Use id as google_id since sub is not present
    const userData = {
      ...googleProfile,
      id: omiuid,
      google_id: googleProfile.id, // Use id as google_id
      token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      token_expiry: new Date(tokens.expiry_date).toISOString(),
      token_uri: 'https://oauth2.googleapis.com/token', // Add Google's OAuth token endpoint
      client_id: process.env.GOOGLE_CLIENT_ID // Add client ID from environment variables
    };

    let retryAttempt = 0;
    let user = null;
    // Try up to 3 times in case of intermittent errors
    while (!user && retryAttempt < 3) {
      user = await supabaseUpsertUser(userData);
      if (!user && retryAttempt < 2) {
        retryAttempt++;
        await new Promise(resolve => setTimeout(resolve, 500 * retryAttempt));
      } else {
        break;
      }
    }

    logAuth('USER_UPSERTED', {
      id: user?.id,
      user_id: user?.user_id, 
      email: user?.email,
      hasTokens: !!user?.token,
      omiuid: omiuid,
      retryAttempts: retryAttempt
    });

    if (!user) {
      // Even if user save fails, generate a token with what we have
      // This will allow basic functionality while we diagnose DB issues
      const tempUser = {
        id: omiuid,
        email: googleProfile.email, 
        name: googleProfile.name
      };
      const jwtToken = generateToken(tempUser);
      
      // Get the base URL from environment or construct from request
      const baseUrl = process.env.BASE_URL || 
        `${req.headers['x-forwarded-proto'] || req.protocol}://${req.headers['x-forwarded-host'] || req.get('host')}`;
      
      // Construct redirect URL with all necessary parameters
      const redirectUrl = new URL('/success.html', baseUrl);
      redirectUrl.searchParams.set('auth_status', 'partial');
      redirectUrl.searchParams.set('device_connected', 'true');
      redirectUrl.searchParams.set('omi_uid', omiuid);
      redirectUrl.searchParams.set('token', jwtToken);
      redirectUrl.searchParams.set('email', googleProfile.email);
      redirectUrl.searchParams.set('name', googleProfile.name);

      logAuth('PARTIAL_AUTH_REDIRECT', {
        reason: 'Failed to save full user details',
        redirecting: true,
        url: redirectUrl.toString()
      });
      
      return res.redirect(redirectUrl.toString());
    }

    // Background email contacts sync - don't wait for it to complete
    getEmailContacts(user)
      .then(contacts => {
        logAuth('EMAIL_SYNC_SUCCESS', { 
          userId: user.id,
          contactsCount: contacts.length 
        });
      })
      .catch(err => logAuth('EMAIL_SYNC_ERROR', { 
        userId: user.id, 
        error: err.message,
        stack: err.stack
      }));

    const jwtToken = generateToken(user);
    logAuth('JWT_GENERATED', { userId: user.id });

    res.cookie('token', jwtToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: process.env.NODE_ENV === 'production' ? 'Strict' : 'Lax',
      maxAge: 7 * 24 * 60 * 60 * 1000 // 7 days
    });

    logAuth('AUTH_SUCCESS', { 
      userId: user.id,
      hasOmiDevice: !!omiuid 
    });
    
    // Get the base URL from environment or construct from request
    const baseUrl = process.env.BASE_URL || 
      `${req.headers['x-forwarded-proto'] || req.protocol}://${req.headers['x-forwarded-host'] || req.get('host')}`;
    
    // Construct redirect URL with all necessary parameters
    const redirectUrl = new URL('/success.html', baseUrl);
    redirectUrl.searchParams.set('auth_status', 'success');
    redirectUrl.searchParams.set('device_connected', 'true');
    redirectUrl.searchParams.set('omi_uid', omiuid);
    redirectUrl.searchParams.set('token', jwtToken);
    redirectUrl.searchParams.set('email', user.email);
    redirectUrl.searchParams.set('name', user.name);
    
    logAuth('REDIRECT_URL', {
      baseUrl,
      fullUrl: redirectUrl.toString(),
      protocol: req.headers['x-forwarded-proto'] || req.protocol,
      host: req.headers['x-forwarded-host'] || req.get('host')
    });
    
    return res.redirect(redirectUrl.toString());
  } catch (error) {
    logAuth('CALLBACK_ERROR', { 
      error: error.message,
      stack: error.stack
    });
    const errorMessage = encodeURIComponent(error.message || 'Authentication failed');
    res.redirect(`${process.env.BASE_URL || '/'}?error=${errorMessage}`);
  }
}));

// Update tokens endpoint
router.post('/update-tokens', [
  body('refreshToken').isString().notEmpty(),
  auth
], asyncHandler(async (req, res) => {
  const errors = validationResult(req);
  logAuth('UPDATE_TOKENS_START', { 
    userId: req.user?.id,
    hasErrors: !errors.isEmpty()
  });

  if (!errors.isEmpty()) {
    return res.status(400).json({ errors: errors.array() });
  }

  try {
    const newTokens = await updateTokens(req.user.id, {
      refreshToken: req.body.refreshToken
    });
    
    logAuth('TOKENS_UPDATED', { 
      userId: req.user.id,
      hasNewAccessToken: !!newTokens.accessToken,
      hasNewRefreshToken: !!newTokens.refreshToken
    });

    res.cookie('token', newTokens.accessToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 3600000
    });

    res.json({ message: 'Tokens updated successfully' });
  } catch (error) {
    logAuth('UPDATE_TOKENS_ERROR', { 
      userId: req.user?.id,
      error: error.message
    });
    res.status(401).json({ error: 'Failed to update tokens' });
  }
}));

// Refresh token
router.post('/refresh-token', asyncHandler(async (req, res) => {
  const token = req.cookies.token;
  logAuth('REFRESH_TOKEN_START', { hasToken: !!token });

  if (!token) {
    return res.status(401).json({ error: 'No token provided' });
  }

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    logAuth('TOKEN_DECODED', { userId: decoded.id });
    
    const user = await fetchUserById(decoded.id);
    if (!user) {
      logAuth('USER_NOT_FOUND', { userId: decoded.id });
      return res.status(401).json({ error: 'Invalid token' });
    }

    const newAccessToken = await refreshAccessToken(user);
    logAuth('TOKEN_REFRESHED', { 
      userId: user.id,
      hasNewToken: !!newAccessToken
    });

    res.cookie('token', newAccessToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 7 * 24 * 60 * 60 * 1000
    });

    res.json({ message: 'Token refreshed successfully' });
  } catch (error) {
    logAuth('REFRESH_TOKEN_ERROR', { error: error.message });
    
    // Handle reverification requirement
    if (error.message === 'REVERIFICATION_REQUIRED') {
      return res.status(401).json({ 
        error: 'Reverification required',
        code: 'REVERIFICATION_REQUIRED',
        message: 'Your Gmail access has expired. Please re-authenticate to continue using email features.'
      });
    }
    
    res.status(401).json({ error: 'Failed to refresh token' });
  }
}));

// Logout
router.post('/logout', asyncHandler(async (req, res) => {
  const token = req.cookies.token;
  logAuth('LOGOUT', { 
    hasToken: !!token,
    ip: req.ip
  });
  
  res.clearCookie('token');
  res.json({ message: 'Logged out successfully' });
}));

// Get current user
router.get('/me', asyncHandler(async (req, res) => {
  const token = req.cookies.token;
  logAuth('GET_CURRENT_USER', { hasToken: !!token });

  if (!token) {
    return res.status(401).json({ error: 'Not authenticated' });
  }

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    logAuth('TOKEN_DECODED_ME', { userId: decoded.id });
    
    const user = await fetchUserById(decoded.id);
    
    if (!user) {
      logAuth('USER_NOT_FOUND_ME', { userId: decoded.id });
      res.clearCookie('token');
      return res.status(404).json({ error: 'User not found' });
    }

    logAuth('USER_FETCHED', {
      userId: user.id,
      email: user.email,
      name: user.name,
      hasOmiDevice: !!user.omi_device_uid
    });

    res.json({
      id: user.id,
      email: user.email,
      name: user.name,
      picture: user.picture,
      omi_device_uid: user.omi_device_uid
    });
  } catch (error) {
    logAuth('GET_CURRENT_USER_ERROR', { error: error.message });
    res.clearCookie('token');
    res.status(401).json({ error: 'Invalid or expired token' });
  }
}));

// Update user settings
router.patch('/settings', auth, async (req, res) => {
  try {
    const { emailNotifications, meetingReminders, timezone } = req.body;
    
    const user = await fetchUserById(req.user.id);
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Update preferences
    const updatedPreferences = {
      ...user.preferences,
      emailNotifications: emailNotifications !== undefined ? emailNotifications : user.preferences.emailNotifications,
      meetingReminders: meetingReminders !== undefined ? meetingReminders : user.preferences.meetingReminders,
      timezone: timezone || user.preferences.timezone
    };

    // Update user in Supabase
    const { data, error } = await supabase
      .from('users')
      .update({ 
        preferences: updatedPreferences,
        updated_at: new Date().toISOString()
      })
      .eq('user_id', req.user.id)
      .select()
      .single();

    if (error) throw error;
    res.json(data.preferences);
  } catch (error) {
    console.error('Error updating settings:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Get or update Omi device association
router.post('/device/:omiuid', auth, [
  body('omiuid').custom((value, { req }) => {
    const omiuid = req.params.omiuid || value;
    if (!isValidOmiUid(omiuid)) {
      throw new Error('Invalid Omi device UID format');
    }
    return true;
  })
], asyncHandler(async (req, res) => {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    return res.status(400).json({ errors: errors.array() });
  }

  try {
    const omiuid = req.params.omiuid;
    const user = await fetchUserById(req.user.id);
    
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Update user's Omi device association
    const { data, error } = await supabase
      .from('users')
      .update({ 
        omi_device_uid: omiuid,
        updated_at: new Date().toISOString()
      })
      .eq('user_id', req.user.id)
      .select()
      .single();

    if (error) throw error;

    logAuth('DEVICE_ASSOCIATED', {
      userId: user.id,
      omiuid: omiuid
    });

    res.json({ 
      message: 'Device associated successfully',
      omiuid: omiuid
    });
  } catch (error) {
    logAuth('DEVICE_ASSOCIATION_ERROR', {
      error: error.message,
      userId: req.user?.id
    });
    res.status(500).json({ error: 'Failed to associate device' });
  }
}));

module.exports = router; 
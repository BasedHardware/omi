const jwt = require('jsonwebtoken');
const { fetchUserById } = require('../utils/supabaseUtils');
const { needsReverification } = require('../utils/googleAuth');

const auth = async (req, res, next) => {
  try {
    // Get access token from cookie
    const token = req.cookies.token || req.headers.authorization?.split(' ')[1];
    
    if (!token) {
      return res.status(401).json({ error: 'No access token provided' });
    }

    try {
      // Verify access token
      const decoded = jwt.verify(token, process.env.JWT_SECRET);
      req.user = decoded;
      
      // Check if user still exists
      const user = await fetchUserById(decoded.id);
      if (!user) {
        throw new Error('User not found');
      }

      // Check if user needs reverification (6 months)
      if (needsReverification(user)) {
        return res.status(401).json({
          error: 'Reverification required',
          code: 'REVERIFICATION_REQUIRED',
          message: 'Your Gmail access has expired. Please re-authenticate to continue using email features.'
        });
      }

      // Check if token needs refresh
      const tokenExpiry = new Date(user.token_expiry);
      const now = new Date();
      
      if (now >= tokenExpiry) {
        // Token needs refresh - client should call /refresh-token endpoint
        return res.status(401).json({
          error: 'Token expired',
          code: 'TOKEN_EXPIRED'
        });
      }

      next();
    } catch (error) {
      if (error.name === 'TokenExpiredError') {
        return res.status(401).json({
          error: 'Token expired',
          code: 'TOKEN_EXPIRED'
        });
      }
      throw error;
    }
  } catch (error) {
    console.error('Auth middleware error:', error);
    res.status(401).json({ error: 'Authentication failed' });
  }
};

module.exports = auth; 
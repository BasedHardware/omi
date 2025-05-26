const mongoose = require('mongoose');

const userSchema = new mongoose.Schema({
  email: {
    type: String,
    required: true,
    trim: true,
    lowercase: true
  },
  name: {
    type: String,
    required: true,
    trim: true
  },
  picture: {
    type: String,
    trim: true
  },
  googleId: {
    type: String,
    sparse: true
  },
  user_id: {
    type: String,
    required: true
  },
  token: {
    type: String,
    required: true
  },
  refresh_token: {
    type: String
  },
  token_uri: {
    type: String,
    required: true,
    default: 'https://oauth2.googleapis.com/token'
  },
  client_id: {
    type: String,
    required: true
  },
  client_secret: {
    type: String,
    required: true
  },
  scopes: {
    type: [String],
    default: [
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
    ]
  },
  token_expiry: {
    type: Date,
    required: true
  },
  last_login: {
    type: Date,
    default: Date.now
  },
  last_contact_sync: {
    type: Date
  },
  contact_sync_status: {
    type: String,
    enum: ['pending', 'in_progress', 'completed', 'failed'],
    default: 'pending'
  },
  createdAt: {
    type: Date,
    default: Date.now
  },
  updatedAt: {
    type: Date,
    default: Date.now
  }
}, {
  timestamps: true,
  indexes: [
    { email: 1, unique: true },
    { user_id: 1, unique: true },
    { googleId: 1, unique: true, sparse: true }
  ]
});

// Pre-save middleware to update timestamps
userSchema.pre('save', function(next) {
  this.updatedAt = new Date();
  next();
});

// Method to check if token needs refresh
userSchema.methods.needsTokenRefresh = function() {
  if (!this.tokenExpiry) return true;
  return Date.now() >= this.tokenExpiry.getTime();
};

// Method to sanitize user object for client
userSchema.methods.toJSON = function() {
  const obj = this.toObject();
  delete obj.token;
  delete obj.refresh_token;
  delete obj.client_secret;
  delete obj.__v;
  return obj;
};

const User = mongoose.model('User', userSchema);

module.exports = User; 
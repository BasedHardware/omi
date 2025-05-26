const mongoose = require('mongoose');

const emailSchema = new mongoose.Schema({
  user: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true,
    index: true
  },
  messageId: {
    type: String,
    unique: true,
    required: true,
    index: true
  },
  subject: String,
  from: {
    email: String,
    name: String
  },
  to: [{
    email: String,
    name: String
  }],
  cc: [{
    email: String,
    name: String
  }],
  bcc: [{
    email: String,
    name: String
  }],
  content: {
    text: String,
    html: String
  },
  attachments: [{
    filename: String,
    contentType: String,
    size: Number
  }],
  analysis: {
    sentiment: {
      score: Number,
      label: String
    },
    priority: {
      type: String,
      enum: ['low', 'medium', 'high', 'urgent'],
      default: 'medium',
      index: true
    },
    category: {
      type: String,
      enum: ['work', 'personal', 'promotional', 'other']
    },
    summary: String,
    actionItems: [String],
    keywords: [String]
  },
  receivedAt: {
    type: Date,
    required: true,
    index: true
  },
  processed: {
    type: Boolean,
    default: false
  },
  created: {
    type: Date,
    default: Date.now
  },
  updated: {
    type: Date,
    default: Date.now
  }
});

emailSchema.pre('save', function(next) {
  this.updated = new Date();
  next();
});

module.exports = mongoose.model('Email', emailSchema); 
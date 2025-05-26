const rateLimit = require('express-rate-limit');
const Joi = require('joi');

// Updated webhook request validation schema to match actual format
const webhookSchema = Joi.object({
  session_id: Joi.string().required(),
  segments: Joi.array().items(
    Joi.object({
      id: Joi.string().required(),
      text: Joi.string().required(),
      speaker: Joi.string().required(),
      speaker_id: Joi.number().required(),
      is_user: Joi.boolean().required(),
      person_id: Joi.any().allow(null),
      start: Joi.number().required(),
      end: Joi.number().required(),
      translations: Joi.array().items(Joi.any()).default([])
    })
  ).min(1).required()
}).required();

// Rate limiter for webhooks
const webhookRateLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 100, // Limit each IP to 100 requests per windowMs
  message: {
    error: 'rate_limit_exceeded',
    message: 'Too many webhook requests, please try again later'
  },
  standardHeaders: true,
  legacyHeaders: false,
  // Add trusted proxy configuration
  trustProxy: true,
  handler: (req, res) => {
    res.status(429).json({
      error: 'rate_limit_exceeded',
      message: 'Too many webhook requests, please try again later'
    });
  }
});

// Simplified webhook validation middleware
const validateWebhook = async (req, res, next) => {
  try {
    // Validate request body against schema
    const { error: validationError } = webhookSchema.validate(req.body);
    if (validationError) {
      return res.status(400).json({
        error: 'invalid_request_body',
        message: validationError.details[0].message
      });
    }

    next();
  } catch (error) {
    console.error('Webhook validation error:', error);
    return res.status(500).json({
      error: 'validation_error',
      message: 'Error validating webhook request'
    });
  }
};

// Error handling middleware for webhooks
const handleWebhookError = (err, req, res, next) => {
  console.error('Webhook Error:', err);

  // Handle specific error types
  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({
      error: 'invalid_json',
      message: 'Invalid JSON payload'
    });
  }

  // Default error response
  res.status(500).json({
    error: 'internal_error',
    message: 'Internal server error processing webhook',
    errorId: `err_${Date.now()}`
  });
};

module.exports = {
  webhookRateLimiter,
  validateWebhook,
  handleWebhookError
}; 
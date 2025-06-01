/**
 * Comprehensive error handling system
 * Implements centralized error handling, logging, and standardized error responses
 */

/**
 * Custom error class with additional properties
 */
class AppError extends Error {
  constructor(message, statusCode = 500, errorCode = 'internal_error', details = null) {
    super(message);
    this.statusCode = statusCode;
    this.errorCode = errorCode;
    this.details = details;
    this.isOperational = true; // Whether this is a known operational error
    this.timestamp = new Date().toISOString();
    
    Error.captureStackTrace(this, this.constructor);
  }
}

/**
 * Factory for common error types
 */
const ErrorFactory = {
  badRequest: (message, errorCode = 'bad_request', details = null) => 
    new AppError(message, 400, errorCode, details),
    
  unauthorized: (message = 'Authentication required', errorCode = 'unauthorized', details = null) => 
    new AppError(message, 401, errorCode, details),
    
  forbidden: (message = 'Access denied', errorCode = 'forbidden', details = null) => 
    new AppError(message, 403, errorCode, details),
    
  notFound: (message = 'Resource not found', errorCode = 'not_found', details = null) => 
    new AppError(message, 404, errorCode, details),
    
  conflict: (message, errorCode = 'conflict', details = null) => 
    new AppError(message, 409, errorCode, details),
    
  validation: (message, details = null) => 
    new AppError(message, 422, 'validation_error', details),
    
  rateLimited: (message = 'Too many requests', errorCode = 'rate_limited', details = null) => 
    new AppError(message, 429, errorCode, details),
    
  internal: (message = 'Internal server error', errorCode = 'internal_error', details = null) => 
    new AppError(message, 500, errorCode, details),
    
  serviceUnavailable: (message = 'Service temporarily unavailable', errorCode = 'service_unavailable', details = null) => 
    new AppError(message, 503, errorCode, details),
};

/**
 * Catch async errors in route handlers
 * @param {Function} fn - Async function to wrap
 * @returns {Function} - Express middleware function
 */
const catchAsync = (fn) => {
  return (req, res, next) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
};

/**
 * Utility to handle API timeouts
 * @param {Promise} promise - The promise to execute
 * @param {number} ms - Timeout in milliseconds
 * @param {string} errorMessage - Error message on timeout
 * @returns {Promise} - Promise with timeout handling
 */
const withTimeout = (promise, ms = 5000, errorMessage = 'Request timed out') => {
  return Promise.race([
    promise,
    new Promise((_, reject) => 
      setTimeout(() => reject(ErrorFactory.serviceUnavailable(errorMessage, 'timeout')), ms)
    )
  ]);
};

module.exports = {
  AppError,
  ErrorFactory,
  catchAsync,
  withTimeout
}; 
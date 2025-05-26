const sendOmiNotification = require('../utils/omiUtils');
const { detectIntentWithOpenAI } = require('../services/intentService');
const { processEmailCommand } = require('../services/emailService');
const { fetchEmailsByContext } = require('../models/aiEmailFetcher');
const { enhancedEmailSearch } = require('../models/enhancedEmailSearch');
const { loadSessionState, saveSessionState } = require('../services/sessionService');
const { getAuthenticatedUser } = require('../services/authService');
const {
  TRIGGER_PATTERN,
  EMAIL_CONTEXT_COLLECTION_DURATION,
  MIN_COLLECTION_TIME,
  SEND_EMAIL_MIN_COLLECTION_TIME
} = require('../config/constants');

// Map to track active timeouts by session_id
const activeTimeouts = new Map();

// Map to track which sessions have already received the "I'm listening" message
const triggerAcknowledged = new Map();

// Helper functions
function updateContext(currentContext, newText) {
  if (currentContext && newText) {
    const endsWithSpace = /\s$/.test(currentContext);
    const startsWithSpace = /^\s/.test(newText);
    
    if (endsWithSpace && startsWithSpace) {
      return currentContext + newText.trimStart();
    } else if (!endsWithSpace && !startsWithSpace && currentContext.length > 0) {
      return currentContext + ' ' + newText;
    } else {
      return currentContext + newText;
    }
  } else {
    return currentContext || newText;
  }
}

function shouldProcessImmediately(preliminaryIntentResult, state, now) {
  const canProcessFetchImmediately = preliminaryIntentResult.intent === 'send_email' ? 
                                     false : 
                                     (preliminaryIntentResult.intent === 'fetch_email' || preliminaryIntentResult.intent === 'search_email') && 
                                     state.emailRawContext.length > 15;
  
  const hasExplicitCompletion = state.userCompletedInput || 
                                /(?:that['']s all|that is all|send it|send now|that['']s it|go ahead|please send|just send)\s*\.?$/i.test(state.emailRawContext.trim());
  
  const timeSinceStart = now - state.triggerTime;
  const intentIsSendEmail = preliminaryIntentResult.intent === 'send_email';
  const minTimeForCurrentIntent = intentIsSendEmail ? SEND_EMAIL_MIN_COLLECTION_TIME : MIN_COLLECTION_TIME;
  const hasReachedIntentSpecificTime = timeSinceStart >= minTimeForCurrentIntent;
  const isTimeoutApproaching = (state.emailContextDeadline - now) < 8000;
  
  if (canProcessFetchImmediately) {
    return { should: true, reason: "Can process fetch immediately - simple check." };
  } else if (intentIsSendEmail && hasExplicitCompletion) {
    return { should: true, reason: "Processing send_email due to explicit completion signal." };
  } else if (intentIsSendEmail && hasReachedIntentSpecificTime && isTimeoutApproaching) {
    return { should: true, reason: `Processing send_email due to minimum collection time (${SEND_EMAIL_MIN_COLLECTION_TIME/1000}s) reached + approaching deadline.` };
  } else if (isTimeoutApproaching) {
    return { should: true, reason: `Timeout approaching for ${preliminaryIntentResult.intent}.` };
  }
  
  return { should: false, reason: "Conditions not met for immediate processing." };
}

async function processIntent(preliminaryIntentResult, user, state, session_id, res) {
  try {
    if (preliminaryIntentResult.intent === 'fetch_email') {
      console.log(`[${session_id}] Processing FETCH_EMAIL immediately.`);
      const fetchResult = await fetchEmailsByContext(user, state.emailRawContext);
      state.lastMessage = fetchResult.message;
      state.lastIntentDetection = preliminaryIntentResult;
      await saveSessionState(session_id, state);
      console.log(`[${session_id}] Sending immediate fetch_email result.`);
      return res.json({ success: true, message: fetchResult.message });
    } else if (preliminaryIntentResult.intent === 'search_email') {
      console.log(`[${session_id}] Processing SEARCH_EMAIL immediately.`);
      const searchResult = await enhancedEmailSearch(user, state.emailRawContext);
      state.lastMessage = searchResult.message;
      state.lastIntentDetection = preliminaryIntentResult;
      await saveSessionState(session_id, state);
      console.log(`[${session_id}] Sending immediate search_email result.`);
      return res.json({ success: true, message: searchResult.message });
    } else {
      console.log(`[${session_id}] Processing SEND_EMAIL or unknown intent immediately.`);
      const emailResult = await processEmailCommand(state.emailRawContext, session_id, res);
      state.lastIntentDetection = preliminaryIntentResult;
      
      if (emailResult === true) {
        console.log(`[${session_id}] Response already sent by processEmailCommand.`);
        return;
      }
      
      if (emailResult.success) {
        state.emailSentSuccessfully = true;
        state.finalRecipient = emailResult.recipient;
        state.generatedSubject = emailResult.subject;
      }
      state.lastMessage = emailResult.message;
      await saveSessionState(session_id, state);
      
      if (!res.headersSent) {
        console.log(`[${session_id}] Sending email result via HTTP response: ${emailResult.message?.substring(0, 100) || 'No message'}`);
        return res.json({ message: emailResult.message });
      }
      return;
    }
  } catch (error) {
    console.error(`[${session_id}] Error in processIntent:`, error);
    
    // Handle reverification requirement
    if (error.message === 'REVERIFICATION_REQUIRED') {
      console.warn(`[${session_id}] User needs to re-authenticate - 6 months since last auth or refresh token expired`);
      const reverificationMessage = "Your Gmail access has expired. Please re-authenticate by visiting the app settings to continue using email features.";
      
      try {
        await sendOmiNotification(session_id, reverificationMessage);
        return res.json({ success: false, message: reverificationMessage, requiresAuth: true });
      } catch (notificationError) {
        console.error(`[${session_id}] Failed to send reverification notification:`, notificationError);
        return res.json({ success: false, message: reverificationMessage, requiresAuth: true });
      }
    }
    
    // Handle other authentication errors
    if (error.message?.includes('Invalid Credentials') || 
        error.message?.includes('invalid_grant') ||
        error.code === 401) {
      console.warn(`[${session_id}] Authentication error:`, error.message);
      const authErrorMessage = "There was an authentication issue with your Gmail account. Please re-authenticate in the app settings.";
      
      try {
        await sendOmiNotification(session_id, authErrorMessage);
        return res.json({ success: false, message: authErrorMessage, requiresAuth: true });
      } catch (notificationError) {
        console.error(`[${session_id}] Failed to send auth error notification:`, notificationError);
        return res.json({ success: false, message: authErrorMessage, requiresAuth: true });
      }
    }
    
    // Handle general errors
    const errorMessage = "I encountered an error while processing your request. Please try again.";
    try {
      await sendOmiNotification(session_id, errorMessage);
      return res.json({ success: false, message: errorMessage });
    } catch (notificationError) {
      console.error(`[${session_id}] Failed to send error notification:`, notificationError);
      return res.json({ success: false, message: errorMessage });
    }
  }
}

function setupTimeoutProcessing(session_id) {
  const timeoutId = setTimeout(async () => {
    activeTimeouts.delete(session_id);
    
    try {
      console.log(`[${session_id}] Timeout triggered. Processing...`);
      await new Promise(resolve => setTimeout(resolve, 500));
      
      let currentState = await loadSessionState(session_id);
      
      if (currentState && currentState.currentMode === 'collecting_email_context' && currentState.emailRawContext && currentState.emailRawContext.trim() !== "") {
        console.log(`[${session_id}] Processing final context after timeout: "${currentState.emailRawContext}"`);
        
        try {
          const intentResult = await detectIntentWithOpenAI(currentState.emailRawContext, session_id);
          console.log(`[${session_id}] Detected intent after timeout: ${intentResult.intent}`);
          
          const user = await getAuthenticatedUser(session_id);
          let processingOutcome = { success: false, message: "Processing failed or user not authenticated.", intent: intentResult.intent };

          if (!user) {
            console.error(`[${session_id}] Failed to authenticate user for auto-processing after timeout`);
            processingOutcome.message = "Authentication failed during processing.";
          } else {
            try {
              if (intentResult.intent === 'fetch_email') {
                const fetchResult = await fetchEmailsByContext(user, currentState.emailRawContext);
                processingOutcome = {
                  success: true, 
                  message: fetchResult.message,
                  timestamp: Date.now()
                };
              } else {
                const emailCommandResult = await processEmailCommand(currentState.emailRawContext, session_id, null);
                if (emailCommandResult.success) {
                  currentState.emailSentSuccessfully = true;
                  currentState.finalRecipient = emailCommandResult.recipient;
                  currentState.generatedSubject = emailCommandResult.subject;
                }
                processingOutcome = {
                  ...emailCommandResult,
                  timestamp: Date.now()
                };
              }
            } catch (authError) {
              console.error(`[${session_id}] Authentication error in timeout processing:`, authError);
              
              if (authError.message === 'REVERIFICATION_REQUIRED') {
                processingOutcome = {
                  success: false,
                  message: "Your Gmail access has expired. Please re-authenticate by visiting the app settings to continue using email features.",
                  requiresAuth: true,
                  timestamp: Date.now()
                };
              } else if (authError.message?.includes('Invalid Credentials') || 
                        authError.message?.includes('invalid_grant') ||
                        authError.code === 401) {
                processingOutcome = {
                  success: false,
                  message: "There was an authentication issue with your Gmail account. Please re-authenticate in the app settings.",
                  requiresAuth: true,
                  timestamp: Date.now()
                };
              } else {
                processingOutcome = {
                  success: false,
                  message: authError.message || "An error occurred during processing.",
                  timestamp: Date.now()
                };
              }
            }
          }
          
          currentState.processingResult = processingOutcome;
          console.log(`[${session_id}] Result stored in session state for retrieval`);
        } catch (processingError) {
          console.error(`[${session_id}] Error processing context after timeout:`, processingError);
          currentState.processingResult = { 
            success: false, 
            message: processingError.message || "An error occurred during processing.",
            timestamp: Date.now()
          };
        }
        
        currentState.currentMode = 'idle';
        currentState.lastUpdated = Date.now();
        await saveSessionState(session_id, currentState);
      }
    } catch (e) {
      console.error(`[${session_id}] Error in timeout processing:`, e);
    }
  }, Math.max(EMAIL_CONTEXT_COLLECTION_DURATION, MIN_COLLECTION_TIME));
  
  activeTimeouts.set(session_id, timeoutId);
}

async function handleTriggerDetection(session_id, combinedText, now, res) {
  // Check if we've already acknowledged this trigger recently
  if (triggerAcknowledged.has(session_id) && (now - triggerAcknowledged.get(session_id)) < 5000) {
    console.log(`[${session_id}] Ignoring duplicate trigger detection within 5 seconds.`);
    return res.status(200).json({ 
      status: 'ok',
      message: 'Continuing to collect context'
    });
  }
  
  console.log(`[${session_id}] Trigger word detected in: "${combinedText}". Transitioning to 'collecting_email_context'.`);
  const state = {
    session_id,
    currentMode: 'collecting_email_context',
    triggerDetected: true,
    triggerTime: now,
    emailContextDeadline: now + EMAIL_CONTEXT_COLLECTION_DURATION + 20000, // Add extra 20 seconds buffer
    emailRawContext: combinedText.replace(/(?:hey|hi|hello|हे)?\s*(?:email|mail|e-mail)/i, '').trim(), // Remove trigger phrases
    originalSegments: [],
    lastUpdated: now,
    // Add a strict minimum processing time to prevent premature intent detection
    minProcessingTime: now + MIN_COLLECTION_TIME,
    // Track if user has explicitly indicated completion
    userCompletedInput: false
  };
  console.log(`[${session_id}] Collection deadline set to ${new Date(now + EMAIL_CONTEXT_COLLECTION_DURATION + 20000).toISOString()} (${Math.floor((EMAIL_CONTEXT_COLLECTION_DURATION + 20000)/1000)}s from now)`);
  await saveSessionState(session_id, state);

  // Clear any existing timeout for this session
  if (activeTimeouts.has(session_id)) {
    clearTimeout(activeTimeouts.get(session_id));
    console.log(`[${session_id}] Cleared existing timeout for this session`);
  }

  // Set up timer for email processing
  setupTimeoutProcessing(session_id);
  
  // Mark this trigger as acknowledged to prevent duplicates
  triggerAcknowledged.set(session_id, now);
  
  // Set a timeout to clear the acknowledgment after a reasonable period
  setTimeout(() => {
    triggerAcknowledged.delete(session_id);
  }, 20000); // Clear after 20 seconds
  
  // Send notification through Omi instead of direct response
  try {
    await sendOmiNotification(session_id, "I'm listening. Please provide the context for your email.");
    return res.sendStatus(202); // Return 202 Accepted status
  } catch (notificationError) {
    console.error(`[${session_id}] Failed to send Omi notification:`, notificationError);
    // Fallback to direct response if notification fails
    return res.json({ 
      message: "I'm listening. Please provide the context for your email."
    });
  }
}

async function handleContextCollection(session_id, state, combinedText, normalizedSegments, now, res) {
  const timeRemainingForMinCollection = state.minProcessingTime ? Math.max(0, state.minProcessingTime - now) : MIN_COLLECTION_TIME;
  const hasReachedMinTime = !state.minProcessingTime || timeRemainingForMinCollection < 500; // If less than 0.5s remaining, consider it reached.

  if (!hasReachedMinTime) {
    // Update context and wait for min time
    let updatedContext = updateContext(state.emailRawContext, combinedText);
    state.emailRawContext = updatedContext.trim();
    state.originalSegments.push(...normalizedSegments);
    state.lastUpdated = now;
    state.lastIncomingSegmentTime = now;
    console.log(`[${session_id}] Not reached minimum collection time yet (${Math.ceil(timeRemainingForMinCollection/1000)}s remaining). Updating context: "${state.emailRawContext.substring(0,100)}..."${state.emailRawContext.length > 100 ? '' : ''}`);

    await saveSessionState(session_id, state);
    return res.sendStatus(202); // Acknowledge segment, wait for min time
  }

  // Update context for processing
  let updatedContext = updateContext(state.emailRawContext, combinedText);
  state.emailRawContext = updatedContext.trim();
  state.originalSegments.push(...normalizedSegments);
  state.lastUpdated = now;
  state.lastIncomingSegmentTime = now;

  // Extend deadline if still receiving text
  const extendedDeadline = now + 20000;
  if (extendedDeadline > state.emailContextDeadline) {
    state.emailContextDeadline = extendedDeadline;
    console.log(`[${session_id}] Extended context collection deadline to ${new Date(extendedDeadline).toISOString()}`);
  }

  // Attempt early intent detection for immediate processing
  const preliminaryIntentResult = await detectIntentWithOpenAI(state.emailRawContext, session_id);
  console.log(`[${session_id}] Preliminary intent: ${preliminaryIntentResult.intent}, Reason: ${preliminaryIntentResult.reasoning.substring(0,100)}...`);

  const user = await getAuthenticatedUser(session_id);
  if (!user) {
    console.error(`[${session_id}] User authentication failed for immediate processing.`);
    state.currentMode = 'idle';
    state.lastErrorMessage = "User authentication failed.";
    await saveSessionState(session_id, state);
    return res.status(401).json({ success: false, message: "Authentication failed. Please ensure you are logged in." });
  }

  // Determine if should process immediately
  const shouldProcessImmediatelyResult = shouldProcessImmediately(preliminaryIntentResult, state, now);

  if (shouldProcessImmediatelyResult.should) {
    console.log(`[${session_id}] Conditions met for immediate processing. Reason: ${shouldProcessImmediatelyResult.reason}`);
    
    if (activeTimeouts.has(session_id)) {
      clearTimeout(activeTimeouts.get(session_id));
      activeTimeouts.delete(session_id);
      console.log(`[${session_id}] Cleared active timeout due to immediate processing.`);
    }
    
    state.currentMode = 'idle';
    return await processIntent(preliminaryIntentResult, user, state, session_id, res);
  } else if (now < state.emailContextDeadline) {
    // Not processing immediately, still collecting context
    console.log(`[${session_id}] Conditions for immediate processing NOT met. Still collecting. Deadline: ${new Date(state.emailContextDeadline).toISOString()}`);
    await saveSessionState(session_id, state);
    return res.sendStatus(202);
  } else {
    // Deadline reached, process final context
    console.log(`[${session_id}] Email context collection deadline reached within webhook execution (fallback).`);
    state.currentMode = 'idle';
    const finalProcessingResult = await processEmailCommand(state.emailRawContext, session_id, res);
    
    if (finalProcessingResult === true) {
      console.log(`[${session_id}] Response already sent by processEmailCommand.`);
      return;
    }
    
    if (finalProcessingResult.success) {
      state.emailSentSuccessfully = true;
      state.finalRecipient = finalProcessingResult.recipient;
      state.generatedSubject = finalProcessingResult.subject;
    }
    state.lastMessage = finalProcessingResult.message;
    await saveSessionState(session_id, state);
    
    if (!res.headersSent) {
      return res.json({ ...finalProcessingResult });
    }
    return;
  }
}

// Main webhook handler
async function handleWebhook(req, res) {
  const webhookReceivedTime = Date.now();
  let initialRequestId = `req_${webhookReceivedTime}_${Math.random().toString(36).substring(2, 7)}`;
  console.log(`[${initialRequestId}] Webhook received at ${new Date(webhookReceivedTime).toISOString()}`);

  try {
    if (!req.body) {
      console.error(`[${initialRequestId}] Missing request body`);
      return res.status(400).json({ 
        error: 'invalid_request',
        message: 'Missing request body' 
      });
    }
    
    const { session_id, segments } = req.body;
    if (!session_id || !Array.isArray(segments)) {
      console.error(`[${initialRequestId}] Invalid request format - missing session_id or segments array`);
      return res.status(400).json({ 
        error: 'invalid_request',
        message: 'Invalid request format. Session ID and segments array are required.' 
      });
    }

    const now = Date.now();
    let state = await loadSessionState(session_id);

    // Check if this session has a processed result waiting to be delivered
    if (state?.processingResult) {
      console.log(`[${session_id}] Found processed result from previous request`);
      const result = state.processingResult;
      
      // Clear the result now that we're delivering it
      state.processingResult = null;
      await saveSessionState(session_id, state);
      
      return res.json(result);
    }

    // Process segments
    const segmentsWithText = segments.filter(s => {
      if (!s || !s.text) return false;
      const trimmedText = s.text.trim();
      if (!trimmedText) return false;
      if (trimmedText.length < 2 && !/^(ok|no|yes|hi|ok)$/i.test(trimmedText)) return false;
      return true;
    });
    
    if (segmentsWithText.length === 0) {
      return res.status(200).json({ status: 'ok', message: 'No valid text segments found' });
    }

    const normalizedSegments = segmentsWithText.map((s, i) => ({
      id: s.id || `seg_${now}_${Math.random().toString(36).substring(2, 10)}_${i}`,
      text: s.text.trim(),
      speaker: s.speaker || s.speaker_id || 'unknown',
      start: typeof s.start === 'number' ? s.start : 0,
      end: typeof s.end === 'number' ? s.end : 0,
      timestamp: now
    }));

    let combinedText = normalizedSegments.map(s => s.text).join(' ').replace(/\\s+/g, ' ').trim();
    console.log(`[${session_id}] Combined text: "${combinedText}"`);

    // Check for trigger word with more flexible pattern matching
    const triggerMatch = combinedText.match(TRIGGER_PATTERN);
    const isTriggerAtStart = /^(?:hey|hi|hello|हे|ए|a|at|ok)?\s*(?:email|mail|e-mail|इमेल)/i.test(combinedText.trim());
    const isStandaloneEmail = /^(?:email|mail|e-mail)$/i.test(combinedText.trim());
    
    if (triggerMatch || isStandaloneEmail || isTriggerAtStart) {
      return await handleTriggerDetection(session_id, combinedText, now, res);
    }

    // Handle email context collection
    if (state?.currentMode === 'collecting_email_context') {
      return await handleContextCollection(session_id, state, combinedText, normalizedSegments, now, res);
    }

    // Check for completed email state - simplified since we use Omi notifications directly
    if (state?.emailSentSuccessfully && state?.finalRecipient) {
      // Reset state
      state = {
        session_id,
        currentMode: 'idle',
        lastUpdated: now
      };
      await saveSessionState(session_id, state);
      return res.status(200).json({ status: 'acknowledged' });
    }

    return res.status(200).json({ status: 'acknowledged' });

  } catch (error) {
    console.error('Webhook error:', error);
    return res.status(500).json({ 
      error: 'internal_error',
      message: 'Internal server error',
      errorId: initialRequestId
    });
  }
}

module.exports = {
  handleWebhook
}; 
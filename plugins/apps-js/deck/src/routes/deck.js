const express = require('express');
const router = express.Router();
const fetch = require('node-fetch-commonjs');
const { 
  sendPresentationReadyNotification, 
  sendPresentationStartedNotification,
  sendPresentationFailedNotification 
} = require('../utils/deckUtils');
require('dotenv').config();

// Initialize Supabase client
const { createClient } = require('@supabase/supabase-js');
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

// Initialize presentations table
async function initializePresentationsTable() {
  try {
    // Create the table if it doesn't exist
    const { error: createError } = await supabase.rpc('create_presentations_table_if_not_exists');
    if (createError) {
      console.error('Error creating presentations table:', createError);
    }
    
    // Add the new columns if they don't exist
    const { error: alterError } = await supabase.rpc('exec', {
      sql: `
        ALTER TABLE presentations 
        ADD COLUMN IF NOT EXISTS embed_url TEXT,
        ADD COLUMN IF NOT EXISTS download_url TEXT;
        
        CREATE INDEX IF NOT EXISTS idx_presentations_embed_url ON presentations(embed_url);
        CREATE INDEX IF NOT EXISTS idx_presentations_download_url ON presentations(download_url);
      `
    });
    
    if (alterError) {
      console.log('Note: Could not add new columns via RPC (this is normal if they already exist):', alterError.message);
    }
    
    console.log('Presentations table initialized successfully with URL columns');
  } catch (error) {
    console.error('Failed to initialize presentations table:', error);
    // Don't throw error to prevent app from crashing
  }
}

// Call initialization on startup
initializePresentationsTable().catch(console.error);

// Helper function to generate random 4-character ID
function generateShortId() {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let result = '';
  for (let i = 0; i < 4; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

// SlidesGPT API constants
const SLIDESGPT_API_KEY = process.env.SLIDESGPT_API_KEY;
const SLIDESGPT_API_URL = 'https://api.slidesgpt.com/v1/presentations/generate';
const TRIGGER_PATTERN = /\b(?:hey|hi|hello)[,\s]+(?:omi|omie)\b/i;
// Map to track active timeouts by session_id
const activeTimeouts = new Map();

// Set timeout for presentation generation
const PRESENTATION_TIMEOUT = 20000; // 20 seconds to collect content
const STATE_EXPIRY_SECONDS = 300; // 5 minutes for Redis state

// Status constants for better tracking
const STATUS = {
  IDLE: 'idle',
  LISTENING: 'listening',
  COLLECTING: 'collecting',
  GENERATING: 'generating',
  COMPLETED: 'completed',
  FAILED: 'failed'
};

/**
 * Status endpoint to check presentation generation progress
 */
router.get('/status/:presentation_id', async (req, res) => {
  try {
    const { presentation_id } = req.params;
    if (!presentation_id) {
      return res.status(400).json({
        error: 'missing_presentation_id',
        message: 'Presentation ID is required'
      });
    }

    // Find the session that has this presentation_id
    const state = await findSessionByPresentationId(presentation_id);
    if (!state) {
      return res.status(404).json({
        error: 'presentation_not_found',
        message: 'No active presentation generation found'
      });
    }

    // Return different information based on status
    switch (state.status) {
      case STATUS.LISTENING:
        return res.json({
          status: state.status,
          message: "Waiting for presentation details...",
          progress: 10
        });
      
      case STATUS.COLLECTING:
        return res.json({
          status: state.status,
          message: "Collecting presentation content...",
          progress: 30,
          content_length: state.presentationContent?.length || 0
        });
      
      case STATUS.GENERATING:
        return res.json({
          status: state.status,
          message: "Generating your presentation...",
          progress: 70,
          started_at: state.generationStarted
        });
      
      case STATUS.COMPLETED:
        return res.json({
          status: state.status,
          message: "Your presentation is ready!",
          progress: 100,
          presentation: {
            embed: state.embedUrl || null,
            download: state.downloadUrl || null
          }
        });
      
      case STATUS.FAILED:
        return res.json({
          status: state.status,
          message: "Failed to generate presentation",
          error: state.error || "Unknown error",
          progress: 0
        });
      
      default:
        return res.json({
          status: state.status || STATUS.IDLE,
          message: "No active presentation generation",
          progress: 0
        });
    }
  } catch (error) {
    console.error('Error fetching presentation status:', error);
    return res.status(500).json({
      error: 'internal_error',
      message: 'Failed to fetch presentation status'
    });
  }
});

/**
 * Returns a quick-loading viewer page for presentation generation
 */
router.get('/viewer/:presentation_id', async (req, res) => {
  const { presentation_id } = req.params;
  if (!presentation_id) {
    return res.status(400).send('Presentation ID is required');
  }

  // Find the session that has this presentation_id
  const state = await findSessionByPresentationId(presentation_id);
  if (!state) {
    return res.status(404).send('Presentation not found');
  }

  // Get initial state if available
  const initialStatus = state?.status || STATUS.IDLE;
  const initialProgress = getProgressForStatus(initialStatus);
  const initialMessage = getMessageForStatus(initialStatus);

  // Check if we already have a completed presentation
  let presentationEmbed = '';
  let presentationDownload = '';
  if (state?.status === STATUS.COMPLETED) {
    // Use the direct URLs from the new schema
    presentationEmbed = state.embedUrl || '';
    presentationDownload = state.downloadUrl || '';
    console.log('Found completed presentation:', {
      embed: presentationEmbed,
      download: presentationDownload,
      slidesgpt_response: !!state.slidesGptResponse
    });
  }

  // Return HTML with built-in JS for polling
  const html = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Presentation Generator</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #2563eb;
      --primary-dark: #1d4ed8;
      --success: #059669;
      --error: #dc2626;
      --background: #f8fafc;
      --surface: #ffffff;
      --text: #1e293b;
      --text-light: #64748b;
    }

    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      line-height: 1.6;
      color: var(--text);
      background-color: var(--background);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }

    .container {
      background-color: var(--surface);
      border-radius: 1rem;
      box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
      padding: 2.5rem;
      width: 100%;
      max-width: 800px;
      text-align: center;
      position: relative;
      overflow: hidden;
    }

    .header {
      margin-bottom: 2rem;
    }

    h1 {
      font-size: 1.875rem;
      font-weight: 600;
      color: var(--text);
      margin-bottom: 0.5rem;
    }

    .subtitle {
      color: var(--text-light);
      font-size: 1rem;
    }

    .progress-container {
      margin: 2rem 0;
      background-color: #e2e8f0;
      border-radius: 9999px;
      height: 8px;
      overflow: hidden;
      position: relative;
    }

    .progress-bar {
      height: 100%;
      background: linear-gradient(90deg, var(--primary), var(--primary-dark));
      border-radius: 9999px;
      transition: width 0.5s ease;
      width: ${initialProgress}%;
      position: relative;
    }

    .progress-bar::after {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: linear-gradient(
        90deg,
        rgba(255, 255, 255, 0) 0%,
        rgba(255, 255, 255, 0.3) 50%,
        rgba(255, 255, 255, 0) 100%
      );
      animation: shimmer 2s infinite;
    }

    @keyframes shimmer {
      0% { transform: translateX(-100%); }
      100% { transform: translateX(100%); }
    }

    .status-container {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 1rem;
      margin: 1.5rem 0;
      min-height: 40px;
    }

    .loader {
      width: 24px;
      height: 24px;
      border: 3px solid #e2e8f0;
      border-top-color: var(--primary);
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .status-message {
      font-size: 1.125rem;
      color: var(--text);
      font-weight: 500;
    }

    .presentation-container {
      margin-top: 2rem;
      display: ${presentationEmbed ? 'block' : 'none'};
      animation: fadeIn 0.5s ease;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }

    iframe {
      border: none;
      width: 100%;
      height: 600px;
      border-radius: 0.5rem;
      box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    }

    .button-group {
      display: flex;
      gap: 1rem;
      justify-content: center;
      margin-top: 1.5rem;
    }

    .button {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      background-color: var(--primary);
      color: white;
      border: none;
      padding: 0.75rem 1.5rem;
      border-radius: 0.5rem;
      font-size: 1rem;
      font-weight: 500;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.2s;
    }

    .button:hover {
      background-color: var(--primary-dark);
      transform: translateY(-1px);
    }

    .button:active {
      transform: translateY(0);
    }

    .button.secondary {
      background-color: #e2e8f0;
      color: var(--text);
    }

    .button.secondary:hover {
      background-color: #cbd5e1;
    }

    .error-container {
      background-color: #fee2e2;
      color: var(--error);
      padding: 1rem;
      border-radius: 0.5rem;
      margin-top: 1rem;
      text-align: left;
      display: none;
      animation: shake 0.5s ease;
    }

    @keyframes shake {
      0%, 100% { transform: translateX(0); }
      25% { transform: translateX(-5px); }
      75% { transform: translateX(5px); }
    }

    .success-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      background-color: #dcfce7;
      color: var(--success);
      padding: 0.5rem 1rem;
      border-radius: 9999px;
      font-weight: 500;
      margin-bottom: 1rem;
    }

    .success-badge svg {
      width: 20px;
      height: 20px;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Presentation Generator</h1>
      <p class="subtitle">Creating your presentation with AI</p>
    </div>

    <div id="progress-container" class="progress-container">
      <div id="progress-bar" class="progress-bar"></div>
    </div>

    <div id="status-container" class="status-container">
      <div id="loader" class="loader"></div>
      <div id="status-message" class="status-message">${initialMessage}</div>
    </div>

    <div id="error-container" class="error-container"></div>

    <div id="presentation-container" class="presentation-container">
      <div id="success-badge" class="success-badge" style="display: none;">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
        Presentation Ready!
      </div>
      <iframe id="presentation-frame" src="${presentationEmbed}" allowfullscreen></iframe>
      <div class="button-group">
        <a id="download-btn" class="button" href="${presentationDownload}" style="display: ${presentationDownload ? 'inline-flex' : 'none'}" target="_blank">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Download PowerPoint
        </a>
        <a id="open-btn" class="button secondary" href="${presentationEmbed}" target="_blank" style="display: ${presentationEmbed ? 'inline-flex' : 'none'}">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
          Open in New Tab
        </a>
      </div>
    </div>
  </div>

  <script>
    const presentationId = "${presentation_id}";
    const statusElement = document.getElementById('status-message');
    const progressBar = document.getElementById('progress-bar');
    const loader = document.getElementById('loader');
    const presentationContainer = document.getElementById('presentation-container');
    const presentationFrame = document.getElementById('presentation-frame');
    const errorContainer = document.getElementById('error-container');
    const downloadBtn = document.getElementById('download-btn');
    const openBtn = document.getElementById('open-btn');
    const successBadge = document.getElementById('success-badge');

    let currentStatus = "${initialStatus}";
    let pollingInterval;
    let failedAttempts = 0;
    const MAX_FAILED_ATTEMPTS = 5;

    // Start polling immediately
    startPolling();

    function startPolling() {
      // Clear any existing polling
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }

      // Set up polling interval - check status every second
      pollingInterval = setInterval(checkStatus, 1000);
      
      // Also check immediately
      checkStatus();
    }

    async function checkStatus() {
      try {
        const response = await fetch('/api/deck/status/' + presentationId);
        
        if (!response.ok) {
          throw new Error('Error fetching status: ' + response.status);
        }
        
        const data = await response.json();
        
        // Update progress bar
        progressBar.style.width = data.progress + '%';
        
        // Update status message
        statusElement.textContent = data.message;
        
        // Show/hide elements based on status
        if (data.status === 'completed') {
          loader.style.display = 'none';
          presentationContainer.style.display = 'block';
          successBadge.style.display = 'inline-flex';
          
          // Update iframe src if needed
          if (data.presentation?.embed) {
            presentationFrame.src = data.presentation.embed;
            openBtn.href = data.presentation.embed;
            openBtn.style.display = 'inline-flex';
            
            // Setup download button if available
            if (data.presentation.download) {
              downloadBtn.href = data.presentation.download;
              downloadBtn.style.display = 'inline-flex';
            }
          } else {
            console.error('No presentation embed URL found in response:', data);
            errorContainer.textContent = 'Error: No presentation embed URL found';
            errorContainer.style.display = 'block';
          }
        } else if (data.status === 'failed') {
          loader.style.display = 'none';
          errorContainer.style.display = 'block';
          errorContainer.textContent = data.error || 'Failed to generate presentation';
        }
      } catch (error) {
        console.error('Error checking status:', error);
        failedAttempts++;
        
        if (failedAttempts >= MAX_FAILED_ATTEMPTS) {
          clearInterval(pollingInterval);
          errorContainer.textContent = 'Error: Failed to check presentation status';
          errorContainer.style.display = 'block';
          loader.style.display = 'none';
        }
      }
    }
  </script>
</body>
</html>
  `;

  // Send the HTML immediately
  res.send(html);
});

// Helper functions for the viewer
function getProgressForStatus(status) {
  switch (status) {
    case STATUS.LISTENING: return 10;
    case STATUS.COLLECTING: return 30;
    case STATUS.GENERATING: return 70;
    case STATUS.COMPLETED: return 100;
    case STATUS.FAILED: return 0;
    default: return 0;
  }
}

function getMessageForStatus(status) {
  switch (status) {
    case STATUS.LISTENING: return "Waiting for presentation details...";
    case STATUS.COLLECTING: return "Collecting presentation content...";
    case STATUS.GENERATING: return "Generating your presentation...";
    case STATUS.COMPLETED: return "Your presentation is ready!";
    case STATUS.FAILED: return "Failed to generate presentation";
    default: return "Initializing...";
  }
}

/**
 * Get all presentations for a session
 */
router.get('/history/:session_id', async (req, res) => {
  try {
    const { session_id } = req.params;
    if (!session_id) {
      return res.status(400).json({
        error: 'missing_session_id',
        message: 'Session ID is required'
      });
    }

    const { data, error } = await supabase
      .from('presentations')
      .select('presentation_id, status, embed_url, download_url, prompt, generation_started_at, generation_completed_at, created_at, updated_at')
      .eq('session_id', session_id)
      .order('created_at', { ascending: false });

    if (error) {
      console.error('[' + session_id + '] Error fetching presentation history:', error);
      return res.status(500).json({
        error: 'database_error',
        message: 'Failed to fetch presentation history'
      });
    }

    return res.json({
      session_id,
      presentations: data || [],
      total: data ? data.length : 0
    });
  } catch (error) {
    console.error('Error fetching presentation history:', error);
    return res.status(500).json({
      error: 'internal_error',
      message: 'Failed to fetch presentation history'
    });
  }
});

/**
 * Webhook endpoint for deck generation triggers
 * Processes voice commands starting with "Hey Deck" to create presentations
 * 
 * NOTIFICATION SYSTEM (3 notifications only):
 * 1. TRIGGER DETECTED: res.json() - Initial listening response with viewer URL
 * 2. GENERATION STARTED: sendPresentationStartedNotification() - When processing begins
 * 3. GENERATION COMPLETED: sendPresentationReadyNotification() - When presentation is ready
 */ 
router.post('/webhook', async (req, res) => {
  const webhookReceivedTime = Date.now();
  const requestId = 'req_' + webhookReceivedTime + '_' + Math.random().toString(36).substring(2, 7);
  console.log('[' + requestId + '] Deck webhook received at ' + new Date(webhookReceivedTime).toISOString());

  // Store the response object for later use
  const responseObject = res;

  try {
    // Validate request body
    if (!req.body) {
      console.error('[' + requestId + '] Missing request body');
      return res.status(400).json({ 
        error: 'invalid_request',
        message: 'Missing request body' 
      });
    }
    
    const { session_id, segments } = req.body;
    if (!session_id || !Array.isArray(segments)) {
      console.error('[' + requestId + '] Invalid request format - missing session_id or segments array');
      return res.status(400).json({ 
        error: 'invalid_request',
        message: 'Invalid request format. Session ID and segments array are required.' 
      });
    }

    const now = Date.now();
    let state = await loadSessionState(session_id);

    // Process segments first to get combined text
    const segmentsWithText = segments.filter(s => {
      if (!s || !s.text) return false;
      const trimmedText = s.text.trim();
      if (!trimmedText) return false;
      if (trimmedText.length < 2) return false;
      return true;
    });
    
    if (segmentsWithText.length === 0) {
      return res.status(200).json({ status: 'ok', message: 'No valid text segments found' });
    }

    const normalizedSegments = segmentsWithText.map((s, i) => ({
      id: s.id || 'seg_' + now + '_' + Math.random().toString(36).substring(2, 10) + '_' + i,
      text: s.text.trim(),
      speaker: s.speaker || s.speaker_id || 'unknown',
      start: typeof s.start === 'number' ? s.start : 0,
      end: typeof s.end === 'number' ? s.end : 0,
      timestamp: now
    }));

    let combinedText = normalizedSegments.map(s => s.text).join(' ').replace(/\\s+/g, ' ').trim();
    console.log('[' + session_id + '] Combined text: "' + combinedText + '"');

    // Check for trigger word - MOVED UP to be available for isAdditionalContent check
    const triggerMatch = combinedText.match(TRIGGER_PATTERN);
    const isTriggerAtStart = /^(?:hey|hi|hello)[,\s]+(?:omi|omie)\b/i.test(combinedText.trim());
    const isInPresentationMode = state?.currentMode === 'collecting_presentation_content';
    
    // Check if this is an explicit "hey omi" command (priority over existing sessions)
    const isExplicitDeckCommand = /\b(?:hey|hi|hello)[,\s]+(?:omi|omie)\b/i.test(combinedText);

    console.log('[' + session_id + '] Trigger analysis:', {
      combinedText: combinedText,
      triggerMatch: triggerMatch ? triggerMatch[0] : null,
      isTriggerAtStart,
      isExplicitDeckCommand,
      isInPresentationMode,
      currentStatus: state?.status || 'no_state'
    });

    // Check if this session has a processed result waiting to be delivered
    if (state?.processingResult) {
      console.log('[' + session_id + '] Found processed presentation result from previous request');
      
      // Check if the processed result is stale (older than 5 minutes)
      const resultAge = state.processingResult.timestamp ? Date.now() - state.processingResult.timestamp : 0;
      const isStaleResult = resultAge > 5 * 60 * 1000; // 5 minutes
      
      // Check if content is getting too long (over 2000 chars indicates stuck session)
      const contentTooLong = state.presentationContent && state.presentationContent.length > 2000;
      
      // Only clear if this is NOT additional content for the presentation OR if result is stale OR content too long
      const isAdditionalContent = state.currentMode === 'collecting_presentation_content' && 
                                 !isExplicitDeckCommand && 
                                 !triggerMatch &&
                                 !isStaleResult &&
                                 !contentTooLong;
      
      // If this is an explicit command, always clear and start fresh
      if (isExplicitDeckCommand || triggerMatch || isStaleResult || contentTooLong) {
        const reason = isExplicitDeckCommand ? 'explicit command' : 
                      triggerMatch ? 'trigger detected' :
                      isStaleResult ? 'stale result' : 'content too long';
        console.log('[' + session_id + '] Clearing previous state due to: ' + reason);
        
        state.processingResult = null;
        state.currentMode = 'idle';
        state.status = STATUS.IDLE;
        state.presentationContent = '';
        state.error = null;
        
        await saveSessionState(session_id, state);
        console.log('[' + session_id + '] Previous state cleared for new session');
        // Continue to process the new trigger
      } else if (!isAdditionalContent) {
        // Clear just the processed result, keep the session record
        state.processingResult = null;
        state.currentMode = 'idle';
        state.status = STATUS.IDLE;
        
        await saveSessionState(session_id, state);
        console.log('[' + session_id + '] Processed result cleared, session ready for new requests');
        
        return res.status(200).json({ status: 'acknowledged' });
      } else {
        console.log('[' + session_id + '] Keeping processed result, this appears to be additional content');
      }
    }

    // Check if there's an active presentation in progress
    const isActivePresentation = state && (
      state.status === STATUS.LISTENING ||
      state.status === STATUS.COLLECTING ||
      state.status === STATUS.GENERATING
    );
    
    // Check if the session is stale (stuck for more than 5 minutes)
    const STALE_SESSION_TIMEOUT = 5 * 60 * 1000; // 5 minutes
    let isStaleSession = false;
    
    if (isActivePresentation && state.updated_at) {
      const sessionAge = Date.now() - new Date(state.updated_at).getTime();
      isStaleSession = sessionAge > STALE_SESSION_TIMEOUT;
      
      if (isStaleSession) {
        console.log(`[${session_id}] Detected stale session (${Math.round(sessionAge/1000)}s old), resetting...`);
        
        // Reset the stale session
        state.status = STATUS.IDLE;
        state.currentMode = 'idle';
        state.processingResult = null;
        state.error = 'Session reset due to timeout';
        
        await saveSessionState(session_id, state);
        console.log(`[${session_id}] Stale session reset to idle`);
      }
    }
    
    console.log('[' + session_id + '] Trigger detection:', {
      triggerMatch: triggerMatch ? triggerMatch[0] : null,
      isTriggerAtStart,
      isInPresentationMode,
      isExplicitDeckCommand,
      isActivePresentation,
      isStaleSession,
      currentStatus: state?.status,
      sessionAge: state?.updated_at ? Math.round((Date.now() - new Date(state.updated_at).getTime())/1000) + 's' : 'new',
      text: combinedText
    });
    
    // Start new session if trigger detected or in presentation mode
    if ((isExplicitDeckCommand || triggerMatch || isTriggerAtStart) && (!isActivePresentation || isStaleSession || isExplicitDeckCommand)) {
      // If this is an explicit command, ALWAYS start fresh regardless of existing state
      if (isExplicitDeckCommand) {
        console.log('[' + session_id + '] EXPLICIT COMMAND DETECTED - Starting completely fresh session');
        
        // Clear any existing timeout for this session FIRST
        if (activeTimeouts.has(session_id)) {
          clearTimeout(activeTimeouts.get(session_id));
          activeTimeouts.delete(session_id);
          console.log('[' + session_id + '] Cleared existing timeout for explicit command');
        }
        
        // Clear any existing state completely
        if (state) {
          state.processingResult = null;
          state.currentMode = 'idle';
          state.status = STATUS.IDLE;
          state.presentationContent = '';
          state.error = null;
        }
      }
      
      // Generate a new short ID for this presentation
      const presentationId = generateShortId();
      console.log('[' + session_id + '] Generated new presentation ID: ' + presentationId);

      // Generate viewer URL immediately
      const host = req.get('host');
      const viewerUrl = 'http://' + host + '/api/deck/viewer/' + presentationId;

      try {
        // Clear any existing timeout for this session FIRST (if not already done)
        if (activeTimeouts.has(session_id) && !isExplicitDeckCommand) {
          clearTimeout(activeTimeouts.get(session_id));
          activeTimeouts.delete(session_id);
          console.log('[' + session_id + '] Cleared existing timeout for this session');
        }

        // Set up initial state - completely fresh for this session
        state = {
          session_id,
          presentation_id: presentationId,
          currentMode: 'collecting_presentation_content',
          status: STATUS.LISTENING,
          triggerDetected: true,
          triggerTime: new Date(now).toISOString(),
          presentationContent: '',  // Start with empty content, will be filled by subsequent messages
          viewerUrl: viewerUrl, // Add viewer URL to state
          lastUpdated: new Date(now).toISOString(),
          created_at: new Date(now).toISOString(),
          updated_at: new Date(now).toISOString()
        };

        console.log('[' + session_id + '] Saving initial state:', {
          presentation_id: presentationId,
          status: state.status,
          content: state.presentationContent,
          content_length: state.presentationContent.length,
          trigger_time: state.triggerTime,
          session_isolation: isExplicitDeckCommand ? 'EXPLICIT_COMMAND_NEW_SESSION' : 'NEW_SESSION_CREATED'
        });

        // Save state immediately
        const saved = await saveSessionState(session_id, state);
        if (!saved) {
          console.error('[' + session_id + '] Failed to save initial state');
          return res.status(500).json({
            error: 'state_save_failed',
            message: 'Failed to initialize presentation state'
          });
        }

        console.log('[' + session_id + '] Initial state saved successfully');

        // NOTIFICATION 1/3: Send immediate response with viewer URL and listening message (via res.json)
        const responseData = { 
          status: STATUS.LISTENING,
          session_id: session_id,
          presentation_id: presentationId,
          viewer_url: viewerUrl,
          message: "👋 Hi! I'm listening. Tell me what presentation you'd like me to create. Track progress: " + viewerUrl,
          trigger_type: isExplicitDeckCommand ? 'explicit_command' : 'trigger_detected'
        };
        
        console.log('[' + session_id + '] NOTIFICATION 1/3: Sending JSON response:', responseData);
        res.json(responseData);
        console.log('[' + session_id + '] NOTIFICATION 1/3: JSON response sent successfully');

        // Set up timer for presentation processing
        const timeoutId = setTimeout(async () => {
          try {
            activeTimeouts.delete(session_id);
            console.log('[' + session_id + '] Processing presentation request...');
            
            const currentState = await loadSessionState(session_id);
            if (!currentState) {
              console.error('[' + session_id + '] No state found when processing timeout');
              return;
            }
            
            if (currentState?.currentMode === 'collecting_presentation_content') {
              // Validate content length and meaningfulness
              const content = currentState.presentationContent ? currentState.presentationContent.trim() : '';
              
              // Check how long we've been collecting content
              const triggerTime = currentState.triggerTime ? new Date(currentState.triggerTime).getTime() : Date.now();
              const timeElapsed = Date.now() - triggerTime;
              
              // Ensure timeElapsed is valid
              const validTimeElapsed = isNaN(timeElapsed) ? 0 : timeElapsed;
              
              console.log('[' + session_id + '] Processing after ' + Math.round(validTimeElapsed/1000) + 's with ' + content.length + ' chars: "' + content.substring(0, 50) + '..."');
              
              if (content.length < 10) {
                console.log('[' + session_id + '] Content too short (' + content.length + ' chars), extending timeout...');
                
                // Extend the timeout to wait for more content
                const extendedTimeoutId = setTimeout(async () => {
                  try {
                    const extendedState = await loadSessionState(session_id);
                    const extendedContent = extendedState?.presentationContent ? extendedState.presentationContent.trim() : '';
                    if (extendedContent.length >= 10) {
                      // Process with the extended content (no response object since this is delayed)
                      console.log('[' + session_id + '] Extended content sufficient (' + extendedContent.length + ' chars), processing...');
                      await processPresentation(session_id, extendedState, viewerUrl);
                    } else {
                      console.log('[' + session_id + '] Still insufficient content after extension (' + extendedContent.length + ' chars), failing...');
                      await failPresentation(session_id, 'Please tell me what presentation you\'d like me to create. I need more details to generate your presentation.');
                    }
                  } catch (err) {
                    console.error('[' + session_id + '] Error in extended timeout:', err);
                    await failPresentation(session_id, err.message);
                  }
                }, 20000);
                
                activeTimeouts.set(session_id, extendedTimeoutId);
                return;
              }
              
              console.log('[' + session_id + '] Content sufficient (' + content.length + ' chars), processing now...');
              // Process presentation (no response object since this is delayed)
              await processPresentation(session_id, currentState, viewerUrl);
            }
          } catch (e) {
            console.error('[' + session_id + '] Error in timeout processing:', e);
            await failPresentation(session_id, e.message);
          }
        }, PRESENTATION_TIMEOUT);
        
        // Store the timeout ID
        activeTimeouts.set(session_id, timeoutId);
        
      } catch (error) {
        console.error('[' + session_id + '] Error setting up presentation:', error);
        return res.status(500).json({
          error: 'setup_failed',
          message: 'Failed to set up presentation generation'
        });
      }
      
      return;
    }

    // If already in presentation mode AND NOT an explicit deck command, collect more content
    if (isInPresentationMode && !isExplicitDeckCommand) {
      // Check if this session has been collecting for too long
      const sessionStartTime = state.triggerTime ? new Date(state.triggerTime).getTime() : Date.now();
      const collectionTime = Date.now() - sessionStartTime;
      const hasBeenCollectingTooLong = collectionTime > 60000; // 60 seconds
      
      // If collecting too long and has sufficient content, process immediately
      if (hasBeenCollectingTooLong && state.presentationContent && state.presentationContent.length > 50) {
        console.log('[' + session_id + '] Session has been collecting for ' + Math.round(collectionTime/1000) + 's with ' + state.presentationContent.length + ' chars - processing now');
        
        // Generate viewer URL
        const host = req.get('host');
        const viewerUrl = 'http://' + host + '/api/deck/viewer/' + state.presentation_id;
        
        // Clear any existing timeout
        if (activeTimeouts.has(session_id)) {
          clearTimeout(activeTimeouts.get(session_id));
          activeTimeouts.delete(session_id);
        }
        
        // Process immediately
        await processPresentation(session_id, state, viewerUrl);
        
        // Check if the presentation completed successfully
        const updatedState = await loadSessionState(session_id);
        if (updatedState?.status === STATUS.COMPLETED) {
          console.log('[' + session_id + '] Presentation completed successfully');
        }
        
        // Don't send additional res.json responses during immediate processing
        // The initial notification was already sent, just acknowledge
        console.log('[' + session_id + '] Processing immediately due to long collection time');
        
        return res.status(200).json({ status: 'acknowledged', message: 'Processing started' });
      }
      
      // Update the presentation content with the new text
      const existingContent = (state.presentationContent || '').trim();
      const newContent = combinedText.trim();
      
      if (existingContent && newContent) {
        state.presentationContent = existingContent + ' ' + newContent;
      } else if (newContent) {
        state.presentationContent = newContent;
      } else {
        state.presentationContent = existingContent;
      }
      state.lastUpdated = now;
      state.status = STATUS.COLLECTING;
      
      console.log('[' + session_id + '] Updated presentation content: "' + state.presentationContent + '"');
      
      await saveSessionState(session_id, state);

      // Generate viewer URL
      const host = req.get('host');
      const viewerUrl = 'http://' + host + '/api/deck/viewer/' + state.presentation_id;
      
      // Always wait for the full timeout period (20 seconds) before processing
      // Don't process immediately even if content is sufficient
      // Don't send additional res.json responses during collection phase
      // The initial notification was already sent, just acknowledge
      console.log('[' + session_id + '] Content collected (' + state.presentationContent.length + ' chars), continuing to listen...');
      
      return res.status(202).json({ status: 'acknowledged', message: 'Content collected' });
    }

    // If no trigger detected and not in presentation mode, just acknowledge
    console.log('[' + session_id + '] No trigger detected, sending acknowledgment');
    return res.status(200).json({ status: 'acknowledged' });

  } catch (error) {
    console.error('Deck webhook error:', error);
    return res.status(500).json({ 
      error: 'internal_error',
      message: 'Internal server error',
      errorId: requestId
    });
  }
});

/**
 * Register a callback URL for a session
 * This allows clients to receive notifications when presentations are generated
 */
router.post('/register-callback/:session_id', async (req, res) => {
  const { session_id } = req.params;
  const { callback_url } = req.body;
  
  if (!session_id) {
    return res.status(400).json({ error: 'Session ID is required' });
  }
  
  if (!callback_url) {
    return res.status(400).json({ error: 'Callback URL is required' });
  }
  
  try {
    // Load current state
    let state = await loadSessionState(session_id);
    if (!state) {
      state = { session_id };
    }
    
    // Add callback URL to state
    state.callback_url = callback_url;
    await saveSessionState(session_id, state);
    
    console.log('[' + session_id + '] Registered callback URL: ' + callback_url);
    
    return res.status(200).json({ 
      success: true, 
      message: 'Callback URL registered successfully',
      session_id
    });
  } catch (error) {
    console.error('[' + session_id + '] Error registering callback:', error);
    return res.status(500).json({ error: 'Failed to register callback URL' });
  }
});

/**
 * Generate a presentation using SlidesGPT API
 * @param {string} prompt - The prompt to use for generating the presentation
 * @returns {Object} - The presentation data including embed and download links
 */
async function generatePresentation(prompt) {
  console.log('Generating presentation with prompt: "' + prompt.substring(0, 100) + '..."');
  
  if (!SLIDESGPT_API_KEY) {
    throw new Error("SlidesGPT API key is not configured");
  }
  
  try {
    const response = await fetch(SLIDESGPT_API_URL, {
      method: "POST",
      headers: {
        "Authorization": "Bearer " + SLIDESGPT_API_KEY,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ prompt })
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error('SlidesGPT API error: ' + response.status + ' - ' + errorText);
    }
    
    const result = await response.json();
    console.log('SlidesGPT API Response:', result);
    
    if (!result.embed || !result.download) {
      throw new Error('Invalid response from SlidesGPT API: Missing embed or download URLs');
    }
    
    return {
      embed: result.embed,
      download: result.download
    };
  } catch (error) {
    console.error('Error generating presentation:', error);
    throw error;
  }
}

/**
 * Load session state from Supabase with new schema
 * @param {string} sessionId - The session ID
 * @returns {object|null} The session state or null if not found
 */
async function loadSessionState(sessionId) {
  try {
    // Find the most recent ACTIVE presentation by session_id
    // Don't load completed presentations as they shouldn't interfere with new ones
    let { data, error } = await supabase
      .from('presentations')
      .select('*')
      .eq('session_id', sessionId)
      .in('status', ['listening', 'collecting', 'generating']) // Only active statuses
      .order('created_at', { ascending: false })
      .limit(1)
      .single();

    if (error) {
      // If no active presentation found, that's normal - return null
      if (error.code === 'PGRST116') {
        console.log('[' + sessionId + '] No active presentation found (this is normal for new sessions)');
        return null;
      }
      console.error('[' + sessionId + '] Error loading state from Supabase:', error);
      return null;
    }

    if (data) {
      // Convert the database record back to our state object format
      const state = {
        // Basic identifiers
        session_id: data.session_id,
        presentation_id: data.presentation_id,
        
        // Status and mode
        status: data.status,
        currentMode: data.current_mode,
        
        // Content
        presentationContent: data.content ? data.content.trim() : '',
        prompt: data.prompt,
        
        // SlidesGPT data
        slidesGptResponse: data.slidesgpt_response ? JSON.parse(data.slidesgpt_response) : null,
        embedUrl: data.embed_url,
        downloadUrl: data.download_url,
        
        // Our application data
        viewerUrl: data.viewer_url,
        processingResult: data.app_result ? JSON.parse(data.app_result) : null,
        
        // Error handling
        error: data.error_message,
        
        // Timing data
        triggerTime: data.trigger_time,
        generationStarted: data.generation_started_at ? new Date(data.generation_started_at).getTime() : null,
        generationCompleted: data.generation_completed_at ? new Date(data.generation_completed_at).getTime() : null,
        
        // Standard timestamps
        created_at: data.created_at,
        updated_at: data.updated_at
      };
      
      console.log('[' + sessionId + '] Loaded active presentation state:', {
        presentation_id: state.presentation_id,
        status: state.status,
        current_mode: state.currentMode,
        has_content: !!state.presentationContent,
        has_slidesgpt_response: !!state.slidesGptResponse,
        has_embed_url: !!state.embedUrl,
        has_download_url: !!state.downloadUrl,
        has_viewer_url: !!state.viewerUrl
      });
      
      return state;
    }

    return null;
  } catch (error) {
    console.error('[' + sessionId + '] Error in loadSessionState:', error);
    return null;
  }
}

/**
 * Save session state to Supabase with new schema
 * @param {string} sessionId - The session ID
 * @param {object} state - The state object to save
 * @returns {boolean} Success status
 */
async function saveSessionState(sessionId, state) {
  try {
    const now = new Date().toISOString();
    
    // Prepare the data for the new schema
    const presentationData = {
      session_id: sessionId,
      presentation_id: state.presentation_id,
      status: state.status || STATUS.IDLE,
      current_mode: state.currentMode || 'idle',
      content: (state.presentationContent && state.presentationContent.trim()) || null,
      prompt: state.prompt || null, // The prompt sent to SlidesGPT
      
      // SlidesGPT response data
      slidesgpt_response: state.slidesGptResponse ? JSON.stringify(state.slidesGptResponse) : null,
      embed_url: state.embedUrl || null,
      download_url: state.downloadUrl || null,
      
      // Our application data
      viewer_url: state.viewerUrl || null,
      app_result: state.processingResult ? JSON.stringify(state.processingResult) : null,
      
      // Error handling
      error_message: state.error || null,
      
      // Timing data
      trigger_time: state.triggerTime || null,
      generation_started_at: state.generationStarted ? new Date(state.generationStarted).toISOString() : null,
      generation_completed_at: state.generationCompleted ? new Date(state.generationCompleted).toISOString() : null,
      
      // Standard timestamps
      created_at: state.created_at || now,
      updated_at: now
    };

    console.log('[' + sessionId + '] Saving presentation data to new schema:', {
      presentation_id: presentationData.presentation_id,
      status: presentationData.status,
      current_mode: presentationData.current_mode,
      has_content: !!presentationData.content,
      has_prompt: !!presentationData.prompt,
      has_slidesgpt_response: !!presentationData.slidesgpt_response,
      has_embed_url: !!presentationData.embed_url,
      has_download_url: !!presentationData.download_url,
      has_viewer_url: !!presentationData.viewer_url
    });

    // Use upsert with presentation_id as the unique key
    const { error } = await supabase
      .from('presentations')
      .upsert(presentationData, {
        onConflict: 'presentation_id',
        ignoreDuplicates: false
      });

    if (error) {
      console.error('[' + sessionId + '] Error saving state to Supabase:', error);
      return false;
    }

    console.log('[' + sessionId + '] Successfully saved presentation data');
    return true;
  } catch (error) {
    console.error('[' + sessionId + '] Error in saveSessionState:', error);
    return false;
  }
}

// Add a function to send a callback notification when presentation generation completes
async function sendCompletionNotification(clientUrl, data) {
  if (!clientUrl) return;
  
  try {
    console.log('Sending completion notification to: ' + clientUrl);
    const response = await fetch(clientUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    
    if (!response.ok) {
      console.error('Failed to send completion notification: ' + response.status + ' ' + response.statusText);
    } else {
      console.log('Completion notification sent successfully');
    }
  } catch (error) {
    console.error('Error sending completion notification:', error);
  }
}

// Helper function to find a session by presentation_id
async function findSessionByPresentationId(presentationId) {
  try {
    console.log('[' + presentationId + '] Searching for presentation in database...');
    const { data, error } = await supabase
      .from('presentations')
      .select('*')
      .eq('presentation_id', presentationId)
      .order('created_at', { ascending: false })
      .limit(1)
      .single();

    if (error) {
      console.error('[' + presentationId + '] Error finding presentation:', error);
      return null;
    }

    if (data) {
      console.log('[' + presentationId + '] Found presentation:', {
        id: data.id,
        status: data.status,
        created_at: data.created_at,
        has_embed_url: !!data.embed_url,
        has_download_url: !!data.download_url,
        has_slidesgpt_response: !!data.slidesgpt_response
      });
      
      // Convert the database record back to our state object format
      const state = {
        // Basic identifiers
        session_id: data.session_id,
        presentation_id: data.presentation_id,
        
        // Status and mode
        status: data.status,
        currentMode: data.current_mode,
        
        // Content
        presentationContent: data.content ? data.content.trim() : '',
        prompt: data.prompt,
        
        // SlidesGPT data
        slidesGptResponse: data.slidesgpt_response ? JSON.parse(data.slidesgpt_response) : null,
        embedUrl: data.embed_url,
        downloadUrl: data.download_url,
        
        // Our application data
        viewerUrl: data.viewer_url,
        processingResult: data.app_result ? JSON.parse(data.app_result) : null,
        
        // Error handling
        error: data.error_message,
        
        // Timing data
        triggerTime: data.trigger_time,
        generationStarted: data.generation_started_at ? new Date(data.generation_started_at).getTime() : null,
        generationCompleted: data.generation_completed_at ? new Date(data.generation_completed_at).getTime() : null,
        
        // Standard timestamps
        created_at: data.created_at,
        updated_at: data.updated_at
      };
      
      return state;
    }

    console.log('[' + presentationId + '] No presentation found in database');
    return null;
  } catch (error) {
    console.error('[' + presentationId + '] Error:', error);
    return null;
  }
}

// Helper function to process presentation generation
async function processPresentation(session_id, currentState, viewerUrl) {
  try {
    // Update status to generating immediately
    currentState.status = STATUS.GENERATING;
    currentState.generationStarted = Date.now();
    currentState.viewerUrl = viewerUrl;
    
    // Store the initial processing result
    currentState.processingResult = {
      success: true,
      message: "🚀 Starting to generate your presentation... You can track it here: " + viewerUrl,
      viewer_url: viewerUrl,
      timestamp: Date.now()
    };
    
    const saved = await saveSessionState(session_id, currentState);
    if (!saved) {
      console.error('[' + session_id + '] Failed to save generating state');
      return;
    }
    
    console.log(`[${session_id}] 🚀 Generation started! Viewer URL: ${viewerUrl}`);
    console.log(`[${session_id}] Content to generate: "${currentState.presentationContent}"`);
    
    // NOTIFICATION 2/3: Send generation started notification (via deckUtils)
    try {
      await sendPresentationStartedNotification(session_id, viewerUrl);
      console.log(`[${session_id}] NOTIFICATION 2/3: Generation started notification sent`);
    } catch (notificationError) {
      console.log(`[${session_id}] NOTIFICATION 2/3: Generation started notification failed:`, notificationError.message);
    }
    
    // Prepare the prompt for SlidesGPT
    const prompt = currentState.presentationContent;
    currentState.prompt = prompt;
    
    // Now generate the presentation
    console.log(`[${session_id}] Calling SlidesGPT API with prompt: "${prompt.substring(0, 100)}..."`);
    const presentationResult = await generatePresentation(prompt);
    console.log('[' + session_id + '] SlidesGPT API call completed successfully');
    
    // Store the full SlidesGPT response
    currentState.slidesGptResponse = presentationResult;
    currentState.embedUrl = presentationResult.embed;
    currentState.downloadUrl = presentationResult.download;
    currentState.generationCompleted = Date.now();
    
    // Update the final result with presentation data
    currentState.currentMode = 'idle';
    currentState.status = STATUS.COMPLETED;
    currentState.processingResult = {
      success: true,
      message: '✅ Your presentation is ready! You can view it here: ' + viewerUrl,
      presentationData: {
        embed: presentationResult.embed,
        download: presentationResult.download
      },
      viewer_url: viewerUrl,
      slidesgpt_response: presentationResult, // Include the full SlidesGPT response
      timestamp: Date.now()
    };
    
    const finalSaved = await saveSessionState(session_id, currentState);
    if (!finalSaved) {
      console.error('[' + session_id + '] Failed to save final state');
      return;
    }
    
    console.log(`[${session_id}] ✅ Presentation ready!`, {
      embed_url: presentationResult.embed,
      download_url: presentationResult.download,
      generation_time: Math.round((currentState.generationCompleted - currentState.generationStarted) / 1000) + 's'
    });
    
    // NOTIFICATION 3/3: Send final completion notification (via deckUtils)
    try {
      await sendPresentationReadyNotification(session_id, viewerUrl);
      console.log(`[${session_id}] NOTIFICATION 3/3: Final completion notification sent`);
    } catch (notificationError) {
      console.log(`[${session_id}] NOTIFICATION 3/3: Final completion notification failed:`, notificationError.message);
      
      // Store fallback message in the processing result for the viewer to pick up
      currentState.processingResult = {
        success: true,
        message: `✅ Your presentation is ready! View: ${viewerUrl} | Download: ${presentationResult.download}`,
        viewer_url: viewerUrl,
        presentationData: {
          embed: presentationResult.embed,
          download: presentationResult.download
        },
        slidesgpt_response: presentationResult,
        timestamp: Date.now(),
        notification_failed: true,
        fallback_message: `✅ Presentation ready! The notification system is temporarily unavailable, but your presentation is complete and accessible via the viewer.`
      };
      
      // Save the fallback state
      await saveSessionState(session_id, currentState);
      console.log(`[${session_id}] ✅ Fallback completion message stored in state for viewer pickup`);
    }
    
    // If a callback URL was provided, notify of completion
    if (currentState.callback_url) {
      await sendCompletionNotification(currentState.callback_url, {
        status: STATUS.COMPLETED,
        session_id,
        presentation_id: currentState.presentation_id,
        viewer_url: viewerUrl,
        embed_url: presentationResult.embed,
        download_url: presentationResult.download,
        slidesgpt_response: presentationResult,
        message: '✅ Your presentation is ready! You can view it here: ' + viewerUrl
      });
    }
    
  } catch (err) {
    console.error('[' + session_id + '] Error generating presentation:', err);
    await failPresentation(session_id, err.message);
  }
}

// Helper function to handle presentation failures
async function failPresentation(session_id, errorMessage) {
  try {
    const currentState = await loadSessionState(session_id);
    if (!currentState) {
      console.error('[' + session_id + '] No state found when failing presentation');
      return;
    }
    
    currentState.processingResult = {
      success: false,
      message: '❌ I couldn\'t create your presentation. Please try again.',
      error: errorMessage,
      timestamp: Date.now()
    };
    
    currentState.currentMode = 'idle';
    currentState.status = STATUS.FAILED;
    currentState.error = errorMessage;
    
    await saveSessionState(session_id, currentState);
    
    console.log(`[${session_id}] ❌ Presentation failed: ${errorMessage}`);
    
    // Send failure notification via deckUtils
    try {
      await sendPresentationFailedNotification(session_id, errorMessage);
      console.log(`[${session_id}] NOTIFICATION: Failure notification sent`);
    } catch (notificationError) {
      console.log(`[${session_id}] NOTIFICATION: Failure notification failed:`, notificationError.message);
    }
    
    // If a callback URL was provided, notify of failure
    if (currentState.callback_url) {
      await sendCompletionNotification(currentState.callback_url, {
        status: STATUS.FAILED,
        session_id,
        presentation_id: currentState.presentation_id,
        message: 'Failed to generate your presentation. Please try again.',
        error: errorMessage
      });
    }
  } catch (error) {
    console.error('[' + session_id + '] Error in failPresentation:', error);
  }
}

module.exports = router;

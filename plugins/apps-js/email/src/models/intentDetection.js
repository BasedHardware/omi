// Constants for recording mechanism
const RECORDING_TIMEOUT = 30000; // 30 seconds in milliseconds
const STOP_TRIGGER_PATTERN = /\b(?:stop|end|finish|done)\s*(?:email|e-mail|mail)\b/i;

// Build trigger variations with flexible spacing and punctuation
const PREFIXES = [
  'hey',
  'hi',
  'hello',
  'okay',
  'ok',
  'yo',
  'हे',    // Hindi variations
  'हाय',
  'नमस्ते'
];

const TRIGGER_BASE = [
  'email',
  'e-mail',
  'mail',
  'इमेल',   // Hindi variations
  'मेल'
];

const NAME_VARIATIONS = [
  'assistant',
  'help',
  'buddy',
  'सहायक',  // Hindi variations
  'मदद'
];

// Combine prefixes with base triggers
const TRIGGER_COMBINATIONS = [];

// Add prefix + base combinations
PREFIXES.forEach(prefix => {
  TRIGGER_BASE.forEach(base => {
    TRIGGER_COMBINATIONS.push(`${prefix}\\s+${base}`);
  });
});

// Add base + name combinations
TRIGGER_BASE.forEach(base => {
  NAME_VARIATIONS.forEach(name => {
    TRIGGER_COMBINATIONS.push(`${base}\\s*${name}`);
    TRIGGER_COMBINATIONS.push(`${name}\\s*${base}`);
  });
  // Also allow the base trigger alone
  TRIGGER_COMBINATIONS.push(`\\b${base}\\b`);
});

// Create the final regex pattern with more lenient matching
const TRIGGER_PATTERN = new RegExp(`(${TRIGGER_COMBINATIONS.join('|')})`, 'i');

// Separate pattern for email intent detection
const EMAIL_COMMAND_PATTERN = /\b(?:send|write|compose|draft|drop|create|make|do|start|begin|email|mail|message|send|write|prepare)\s+(?:an?|the)?\s*(?:email|mail|message|draft)?\b|\b(?:email|mail|message)\s+(?:to|for)\b/i;

// Constants for confirmation handling
const CONFIRMATION_PATTERNS = {
  yes: /\b(?:yes|yeah|yep|yup|correct|right|sure|ok|okay|confirm|send|send it|that's right|that's correct|sounds good|हां|हा|ठीक|सही)\b/i,
  no: /\b(?:no|nope|nah|wrong|incorrect|cancel|stop|don't send|do not send|नहीं|नही|मत|रुको)\b/i,
  wrong: /\b(?:wrong|incorrect|not right|different|other|another|not that|not this|गलत|दूसरा|अलग)\b/i,
  numbers: /\b(?:one|two|three|four|five|1|2|3|4|5|first|second|third|fourth|fifth)\b|^(\d+)\.?$/i
};

// Function to detect if a command is likely incomplete
function isLikelyIncompleteCommand(text) {
  if (!text) return false;
  
  // Check if the text ends with prepositions, conjunctions, or articles that suggest more is coming
  const incompleteEndingsRegex = /\b(to|and|or|the|a|an|in|on|at|by|for|with|about|please|generate|can you|would you|could you|send|write|draft|create|compose)$/i;
  if (incompleteEndingsRegex.test(text.trim())) {
    return true;
  }
  
  // Check if the text ends with a coordinating conjunction suggesting more content to follow
  if (/\b(and|or|but|so|yet|for|nor)\s*$/i.test(text.trim())) {
    return true;
  }
  
  // Check if we have a command start without enough content
  if (EMAIL_COMMAND_PATTERN.test(text) && text.split(/\s+/).length < 6) {
    // Email command detected but less than 6 words - likely incomplete
    return true;
  }
  
  // Check if the text contains "to" but doesn't have enough words after "to" to specify a recipient
  const toMatch = text.match(/\bto\s+(\S+\s){0,2}$/i);
  if (toMatch) {
    // We have "to" followed by 0-2 words at the end of the string
    return true;
  }
  
  return false;
}

// Function to determine if segments contain useful command data
function segmentsContainCommandData(segments) {
  // Skip segments that are just acknowledgments or common fillers
  const fillerRegex = /^(um|uh|hmm|er|ah|like|you know|well|so|okay|ok|right|yeah|yes|no|mhm|hmm)\.?$/i;
  
  for (const segment of segments) {
    const text = segment.text || '';
    if (text.trim().length > 2 && !fillerRegex.test(text.trim())) {
      return true;
    }
  }
  
  return false;
}

// Helper function to analyze the command for key elements
function analyzeCommand(command) {
  const lowerCommand = command.toLowerCase();
  return {
    mentionsAttachment: /\b(?:attach|document|file|pdf|presentation|spreadsheet)\b/.test(lowerCommand),
    isFollowUp: /\b(?:follow[- ]?up|previous|earlier|last|our|regarding|re:|as discussed)\b/.test(lowerCommand),
    containsQuestion: /\?|what|when|where|who|why|how|could|would|will|can|should/.test(lowerCommand),
    requestsResponse: /\b(?:let me know|your thoughts|respond|reply|feedback|answer|get back|confirm)\b/.test(lowerCommand),
    requestsMeeting: /\b(?:meet|meeting|schedule|call|zoom|teams|discuss|chat|talk|conversation)\b/.test(lowerCommand),
    containsDateOrTime: /\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|december|am|pm|:\d{2}|\d{1,2}\/\d{1,2}|\d{1,2}\.\d{1,2}|\d{1,2}-\d{1,2})\b/i.test(lowerCommand),
    containsNumbers: /\$\d+|\d+%|\d+\.\d+|\b\d{3,}\b/.test(lowerCommand),
    isUrgent: /\b(?:urgent|asap|as soon as possible|immediately|right away|important|priority|critical)\b/.test(lowerCommand)
  };
}

// Helper function to extract subject intent
function getSubjectIntent(subject) {
  const lowerSubject = subject.toLowerCase();
  
  if (/\b(?:meet|meeting|call|appointment|schedule|discussion)\b/.test(lowerSubject)) {
    return 'meeting';
  } else if (/\b(?:update|status|progress|report)\b/.test(lowerSubject)) {
    return 'update';
  } else if (/\b(?:question|inquiry|query|help|assist|support)\b/.test(lowerSubject)) {
    return 'question';
  } else if (/\b(?:follow.?up|regarding|re:|reference)\b/.test(lowerSubject)) {
    return 'followup';
  } else if (/\b(?:proposal|offer|quote|estimate)\b/.test(lowerSubject)) {
    return 'proposal';
  } else if (/\b(?:thank|appreciate|gratitude)\b/.test(lowerSubject)) {
    return 'thanks';
  } else if (/\b(?:payment|invoice|bill|receipt|transaction)\b/.test(lowerSubject)) {
    return 'payment';
  }
  
  return 'general';
}

module.exports = {
  RECORDING_TIMEOUT,
  STOP_TRIGGER_PATTERN,
  TRIGGER_PATTERN,
  EMAIL_COMMAND_PATTERN,
  CONFIRMATION_PATTERNS,
  isLikelyIncompleteCommand,
  segmentsContainCommandData,
  analyzeCommand,
  getSubjectIntent
};

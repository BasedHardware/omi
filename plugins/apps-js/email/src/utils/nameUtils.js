const natural = require('natural');
const DoubleMetaphone = natural.DoubleMetaphone;
const metaphone = new DoubleMetaphone();

// Constants for context detection
const CONTEXT_MARKERS = ['at', 'in', 'from', 'of', 'who', 'works', 'working'];
const IMPLICIT_CONTEXT_MARKERS = /(?:team|department|group|division|company|org|organization)/i;
const DEPARTMENT_TERMS = [
  'engineering', 'developer', 'frontend', 'backend', 'fullstack',
  'design', 'product', 'marketing', 'sales', 'support',
  'hr', 'finance', 'legal', 'operations', 'management',
  'research', 'development', 'qa', 'testing', 'devops',
  'infrastructure', 'security', 'data', 'analytics',
  'customer', 'service', 'success', 'experience',
  'content', 'creative', 'brand', 'communication',
  'business', 'strategy', 'partnership', 'growth'
];

/**
 * Get all possible name variations and nicknames for a given name
 * @param {string} name - The name to get variations for
 * @returns {string[]} - Array of name variations
 */
function getNameVariations(name) {
  const normalized = name.toLowerCase().trim();
  const variations = new Set([normalized]);
  
  // Add common variations
  const commonVariations = {
    'marc': ['mark', 'marcus', 'marco'],
    'mark': ['marc', 'marcus', 'marco'],
    'michael': ['mike', 'mick', 'mickey'],
    'mike': ['michael', 'mick', 'mickey'],
    'robert': ['rob', 'bob', 'bobby'],
    'william': ['will', 'bill', 'billy'],
    'james': ['jim', 'jimmy', 'jamie'],
    'john': ['jon', 'johnny', 'jonathan'],
    'christopher': ['chris', 'kris', 'topher'],
    'chris': ['christopher', 'kris', 'topher'],
    'alexander': ['alex', 'al', 'sandy'],
    'alex': ['alexander', 'al', 'sandy'],
    'thomas': ['tom', 'tommy', 'thom'],
    'tom': ['thomas', 'tommy', 'thom']
  };
  
  // Add common variations
  for (const [base, vars] of Object.entries(commonVariations)) {
    if (normalized === base || vars.includes(normalized)) {
      variations.add(base);
      vars.forEach(v => variations.add(v));
    }
  }

  // Add phonetic variations using metaphone
  try {
    const phoneticCode = metaphone.process(normalized);
    // Find other names that sound similar
    Object.keys(commonVariations).forEach(base => {
      if (metaphone.process(base) === phoneticCode) {
        variations.add(base);
        commonVariations[base].forEach(v => variations.add(v));
      }
    });
  } catch (error) {
    console.log('Metaphone processing failed for:', name);
  }
  
  // Add the original name parts
  const nameParts = normalized.split(/\s+/);
  nameParts.forEach(part => {
    if (part.length > 1) {
      variations.add(part);
    }
  });
  
  return Array.from(variations);
}

/**
 * Calculate similarity between two names
 * @param {string} name1 - First name
 * @param {string} name2 - Second name
 * @returns {number} - Similarity score between 0 and 1
 */
function calculateNameSimilarity(name1, name2) {
  if (!name1 || !name2) return 0;
  
  const n1 = name1.toLowerCase().trim();
  const n2 = name2.toLowerCase().trim();
  
  // Exact match
  if (n1 === n2) return 1.0;
  
  // Check common variations and nicknames
  const n1Variations = getNameVariations(n1);
  const n2Variations = getNameVariations(n2);
  if (n1Variations.some(v => n2Variations.includes(v))) return 0.9;
  
  try {
    // Fuzzy string matching
    const fuzzScore = natural.JaroWinklerDistance(n1, n2);
    if (fuzzScore > 0.8) return fuzzScore;
    
    // Double Metaphone matching with error handling
    try {
      const [n1Primary, n1Secondary] = metaphone.tokenize(n1);
      const [n2Primary, n2Secondary] = metaphone.tokenize(n2);
      
      // Check primary and secondary codes
      if (n1Primary === n2Primary) return 0.8;
      if (n1Secondary && n2Secondary && n1Secondary === n2Secondary) return 0.7;
    } catch (error) {
      console.log('Metaphone matching failed, continuing with other methods');
    }
    
    // Check substring matches
    if (n1.includes(n2) || n2.includes(n1)) return 0.7;
    
    // Check word-by-word matching
    const n1Words = n1.split(/\s+/);
    const n2Words = n2.split(/\s+/);
    const commonWords = n1Words.filter(w => n2Words.includes(w));
    if (commonWords.length > 0) {
      return 0.6 * (commonWords.length / Math.max(n1Words.length, n2Words.length));
    }
    
    // Levenshtein as last resort
    const levenshtein = natural.LevenshteinDistance(n1, n2);
    const lengthNormalized = 1 - (levenshtein / Math.max(n1.length, n2.length));
    return lengthNormalized * 0.5; // Weight it lower since it's less reliable
    
  } catch (error) {
    console.log('Falling back to basic string matching for:', n1, n2);
    return n1.includes(n2) || n2.includes(n1) ? 0.6 : 0;
  }
}

/**
 * Parse recipient from a complex phrase
 * @param {string} phrase - The phrase to parse
 * @returns {Object} - Object with name and context properties
 */
function parseRecipientPhrase(phrase) {
  // Normalize the phrase
  const normalizedPhrase = phrase.toLowerCase().trim();
  
  // Split into parts by common separators
  const parts = normalizedPhrase.split(/\s+/);
  
  // Extract potential name and context
  let nameWords = [];
  let contextWords = [];
  let isContext = false;
  let hasContextMarker = false;

  for (let i = 0; i < parts.length; i++) {
    const word = parts[i];
    
    // Check if this word starts context section
    if (CONTEXT_MARKERS.includes(word)) {
      isContext = true;
      hasContextMarker = true;
      continue;
    }
    
    // Check for implicit context markers
    if (!hasContextMarker && i > 0 && IMPLICIT_CONTEXT_MARKERS.test(word)) {
      isContext = true;
      continue;
    }
    
    if (isContext) {
      contextWords.push(word);
    } else {
      nameWords.push(word);
    }
  }

  // If no explicit context was found, try to extract role/department
  if (!hasContextMarker && nameWords.length > 1) {
    const lastWord = nameWords[nameWords.length - 1];
    if (DEPARTMENT_TERMS.some(term => natural.JaroWinklerDistance(term, lastWord) > 0.8)) {
      contextWords = [lastWord];
      nameWords.pop();
    }
  }

  return {
    name: nameWords.join(' '),
    context: contextWords.join(' ')
  };
}

/**
 * Match contact by context
 * @param {Object} contact - Contact object with email property
 * @param {string} context - Context string
 * @returns {number} - Similarity score between 0 and 1
 */
function matchContactByContext(contact, context) {
  if (!context) return 0;
  
  // Normalize email and context
  const emailParts = contact.email.toLowerCase().split('@');
  const domain = emailParts[1] || '';
  const localPart = emailParts[0] || '';
  const contextWords = context.toLowerCase().split(/\s+/);
  
  let score = 0;
  let matchedTerms = 0;
  
  // Check each context word against email parts and department terms
  for (const word of contextWords) {
    if (word.length < 3) continue; // Skip very short words
    
    // Check domain part with higher weight
    if (domain.includes(word)) {
      score += 0.4;
      matchedTerms++;
    }
    
    // Check local part
    if (localPart.includes(word)) {
      score += 0.3;
      matchedTerms++;
    }
    
    // Check department/role terms with fuzzy matching
    const departmentMatch = DEPARTMENT_TERMS.some(term => {
      const similarity = natural.JaroWinklerDistance(term, word);
      return similarity > 0.8;
    });
    if (departmentMatch) {
      score += 0.3;
      matchedTerms++;
    }
  }
  
  // Normalize score based on number of matched terms
  return matchedTerms > 0 ? Math.min(score / matchedTerms, 1) : 0;
}

/**
 * Extract potential recipient name from text
 * @param {string} text - Text to extract name from
 * @returns {string} - Extracted name or 'unknown recipient'
 */
function extractNameFromText(text) {
  // Try various patterns to extract a name
  const patterns = [
    /(?:to|for)\s+([A-Za-z\s]{2,20})(?:\s|$)/i,           // "to John Smith"
    /(?:email|mail|send|write)\s+([A-Za-z\s]{2,20})(?:\s|$)/i, // "email John Smith"
    /(?:tell|ask|contact)\s+([A-Za-z\s]{2,20})(?:\s|$)/i, // "tell John Smith"
    /([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})/                // Capitalized words (likely names)
  ];
  
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && match[1] && match[1].length > 1) {
      return match[1].trim();
    }
  }
  
  // Default fallback - look for words that might be names (capitalized)
  const words = text.split(/\s+/);
  for (const word of words) {
    if (word.length > 1 && /^[A-Z][a-z]+$/.test(word)) {
      return word;
    }
  }
  
  return 'unknown recipient';
}
// Function to find matching emails
async function findMatchingEmails(recipientHint, user, getEmailContacts) {
  try {
    const contacts = await getEmailContacts(user);
    
    // Parse the recipient hint into name and context
    const { name, context } = parseRecipientPhrase(recipientHint);
    console.log('Parsed recipient:', { name, context });
    
    // If no name was extracted, try to use the whole hint as a name
    const searchName = name || recipientHint.trim();
    if (!searchName) {
      console.log('No searchable name found');
      return [];
    }
    
    // Get all possible variations of the search name
    const searchVariations = getNameVariations(searchName);
    console.log('Searching for variations:', searchVariations);
    
    // Prepare contacts with names
    const contactsWithNames = contacts.map(email => {
      if (typeof email === 'string') {
        // Extract display name from email
        const [localPart, domain] = email.split('@');
        const displayName = localPart
          .replace(/[._-]/g, ' ')
          .split(' ')
          .map(part => part.charAt(0).toUpperCase() + part.slice(1))
          .join(' ');

        // Add domain-based context
        const domainContext = domain.split('.')[0];
        
        return {
          email,
          name: displayName,
          context: domainContext,
          variations: getNameVariations(displayName)
        };
      } else {
        // Email is already an object with properties
        return {
          ...email,
          variations: getNameVariations(email.name || email.email.split('@')[0])
        };
      }
    });
    
    // Find matches using both name variations and context
    const results = contactsWithNames.map(contact => {
      try {
        // Check if any of the search variations match any of the contact variations
        const nameMatch = searchVariations.some(searchVar => 
          contact.variations.some(contactVar => {
            // Direct match
            if (contactVar === searchVar) return true;
            
            // Case-insensitive partial match
            const searchLower = searchVar.toLowerCase();
            const contactLower = contactVar.toLowerCase();
            if (contactLower.includes(searchLower) || searchLower.includes(contactLower)) return true;
            
            // Fuzzy match using Jaro-Winkler
            return natural.JaroWinklerDistance(contactLower, searchLower) > 0.85;
          })
        );
        
        // Get name similarity score
        const nameScore = nameMatch ? 0.9 : Math.max(
          ...searchVariations.map(searchVar =>
            Math.max(...contact.variations.map(contactVar =>
              natural.JaroWinklerDistance(contactVar.toLowerCase(), searchVar.toLowerCase())
            ))
          )
        );
        
        // Get context match score if context exists
        const contextScore = context ? matchContactByContext(contact, context) : 0;
        
        // Combine scores with adjusted weights
        const combinedScore = context 
          ? (nameScore * 0.8) + (contextScore * 0.2)
          : nameScore;
        
        return {
          ...contact,
          score: combinedScore,
          nameMatch: nameScore,
          contextMatch: contextScore
        };
      } catch (error) {
        console.error('Error calculating match score for contact:', contact, error);
        return {
          ...contact,
          score: 0,
          nameMatch: 0,
          contextMatch: 0
        };
      }
    });
    
    // Adjust thresholds
    const HIGH_THRESHOLD = 0.5;  // Lowered threshold for better matching
    const LOW_THRESHOLD = 0.3;   // Lower threshold for partial matches
    
    // Filter and sort results
    const matches = results
      .filter(r => r.score >= HIGH_THRESHOLD)
      .sort((a, b) => b.score - a.score);
    
    // If no matches found with high threshold, try with lower threshold
    if (matches.length === 0) {
      console.log('No matches found with high threshold, trying lower threshold');
      const lowThresholdMatches = results
        .filter(r => r.score >= LOW_THRESHOLD)
        .sort((a, b) => b.score - a.score)
        .slice(0, 3); // Limit to top 3 matches
      
      if (lowThresholdMatches.length > 0) {
        console.log('Found matches with lower threshold:', lowThresholdMatches);
        return lowThresholdMatches;
      }
    }
    
    return matches;
  } catch (error) {
    console.error('Error finding matching emails:', error);
    return [];
  }
}

module.exports = {
  getNameVariations,
  calculateNameSimilarity,
  parseRecipientPhrase,
  matchContactByContext,
  extractNameFromText,
  findMatchingEmails,
  CONTEXT_MARKERS,
  IMPLICIT_CONTEXT_MARKERS,
  DEPARTMENT_TERMS
}; 
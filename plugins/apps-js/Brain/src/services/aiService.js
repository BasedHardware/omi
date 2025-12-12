const openai = require('../config/openai');

async function processChatWithGPT(message, context) {
    const idToNode = new Map(context.nodes.map(n => [n.id, n]));
    const contextString = `People and Places: ${context.nodes.map(n => n.name).join(', ')}\n` +
        `Facts: ${context.relationships.map(r => `${idToNode.get(r.source)?.name || r.source} ${r.action} ${idToNode.get(r.target)?.name || r.target}`).join('. ')}`;

    const systemPrompt = `You are a friendly and engaging AI companion with access to these memories:

${contextString}

Personality Guidelines:
- Be warm and conversational, like chatting with a friend
- Show enthusiasm and genuine interest
- Use casual language and natural expressions
- Add personality with occasional humor or playful remarks
- Be empathetic and understanding
- Share insights in a relatable way

When responding:
1. Make it personal:
   - Connect memories to emotions and experiences
   - Share observations like you're telling a story
   - Use "I notice" or "I remember" instead of formal statements
   - Express excitement about interesting connections

2. Keep it natural:
   - Chat like a friend would
   - Use contractions (I'm, you're, that's)
   - Add conversational fillers (you know, actually, well)
   - React naturally to discoveries ("Oh, that's interesting!")

3. Be helpful but human:
   - If you know something, share it enthusiastically
   - If you don't know, be honest and casual about it
   - Suggest possibilities and connections
   - Show curiosity about what you're discussing

Memory Status: ${context.nodes.length > 0 ?
            `I've got quite a collection here - ${context.nodes.length} memories all connected in interesting ways!` :
            "I don't have any memories stored yet, but I'm excited to learn!"}`;

    try {
        const completion = await openai.chat.completions.create({
            model: "gpt-4o-mini",
            messages: [
                {
                    role: "system",
                    content: systemPrompt
                },
                {
                    role: "user",
                    content: message
                }
            ],
            temperature: 0.7,
            max_tokens: 150
        });

        return completion.choices[0].message.content;
    } catch (error) {
        console.error('Error processing chat:', error);
        throw error;
    }
}

async function processTextWithGPT(text, existingMemory = { nodes: new Map(), relationships: [] }) {
    // Convert existing nodes to a more usable format for the prompt
    const existingNodes = Array.from(existingMemory.nodes.values());
    const existingRelationships = existingMemory.relationships;

    // Create context strings for existing memory
    const existingNodesContext = existingNodes.length > 0 ?
        `\nEXISTING NODES (REUSE THESE IDs WHEN POSSIBLE):\n${existingNodes.map(n => `- ${n.id}: ${n.name} (${n.type})`).join('\n')}` :
        '';

    const existingRelationshipsContext = existingRelationships.length > 0 ?
        `\nEXISTING RELATIONSHIPS (REUSE THESE PATTERNS):\n${existingRelationships.map(r => `- ${r.source} → ${r.target}: ${r.action}`).slice(0, 20).join('\n')}` :
        '';

    const prompt = `Analyze this text like a human brain processing new information. Extract key entities and their relationships, focusing on logical connections and cognitive patterns.

IMPORTANT: Before creating new entities, check if they already exist in the memory graph below. If an entity matches or is very similar to an existing one, REUSE the existing node ID instead of creating a new one.

${existingNodesContext}${existingRelationshipsContext}

Text to analyze: "${text}"

Format response as JSON:
{
    "entities": [
        {
            "id": "ORB-EntityName OR existing-node-id",
            "type": "person|location|event|concept",
            "name": "Original Name"
        }
    ],
    "relationships": [
        {
            "source": "node-id-1",
            "target": "node-id-2",
            "action": "description of relationship"
        }
    ]
}

Guidelines for brain-like processing:
1. Entity Recognition Priority:
   - FIRST: Check if entity matches existing nodes (same person, place, concept)
   - If match found: Use existing node ID, keep existing name
   - If no match: Create new entity with ORB-EntityName format
   - People: Identify as agents (ORB-FirstName format for new ones)
   - Locations: Places that provide spatial context
   - Events: Temporal markers connecting other entities
   - Concepts: Abstract ideas linking multiple entities

2. Relationship Analysis:
   - Check existing relationships for similar patterns
   - Reuse similar action descriptions when appropriate
   - Focus on cause and effect, temporal sequences
   - Include contextual links and logical dependencies

3. Memory Integration Rules:
   - Prioritize connecting to existing nodes over creating new ones
   - If uncertain about entity match, favor reusing existing nodes
   - Only create new entities for genuinely new information
   - Link new information to existing patterns when possible

4. Quality Control:
   - Only extract significant, memorable information
   - Focus on actionable relationships
   - Avoid creating duplicate or near-duplicate entities
   - Ensure relationships make logical sense

Return empty arrays if no meaningful patterns found.`;

    try {
        const completion = await openai.chat.completions.create({
            model: "gpt-4o-mini",
            messages: [
                {
                    role: "system",
                    content: "You are a precise entity and relationship extraction system. Extract key information and format it exactly as requested. Return only valid JSON."
                },
                {
                    role: "user",
                    content: prompt
                }
            ],
            response_format: { type: "json_object" },
            temperature: 0.45,
            max_tokens: 1000
        });

        return JSON.parse(completion.choices[0].message.content);
    } catch (error) {
        console.error('Error processing text with GPT:', error);
        throw error;
    }
}

module.exports = {
    processChatWithGPT,
    processTextWithGPT
};

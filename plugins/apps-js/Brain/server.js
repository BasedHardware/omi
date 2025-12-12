/*
 * Copyright (c) 2025 Neo (github.com/neooriginal)
 * All rights reserved.
 */

require('dotenv').config();
const express = require('express');
const bodyParser = require('body-parser');
const axios = require('axios');
const cookieParser = require('cookie-parser');
const session = require('express-session');
const sanitizeHtml = require('sanitize-html');
const { URL } = require('url');

// Config & Utils
const supabase = require('./src/config/supabase');
const openai = require('./src/config/openai');
const { handleDatabaseError, decryptText, resolveUid } = require('./src/utils/helpers');

// Middleware
const { requireAuth } = require('./src/middleware/auth');
const {
    validateUid,
    validateTextInput,
    validateNodeData,
    validateInput
} = require('./src/middleware/validation');

// Services
const {
    loadMemoryGraph,
    saveMemoryGraph,
    addSampleData,
    deleteAllUserData
} = require('./src/services/memoryService');

const {
    processChatWithGPT,
    processTextWithGPT
} = require('./src/services/aiService');

const app = express();
app.set('trust proxy', 1); // Trust Render's proxy for secure cookies
const port = process.env.PORT || 3000;

app.use(bodyParser.json({ limit: '10mb' }));
app.use(bodyParser.urlencoded({ limit: '10mb', extended: true }));
app.use(cookieParser());

const sessionConfig = {
    secret: process.env.SESSION_SECRET || 'brain-app-default-secret-please-change-in-production',
    resave: false,
    saveUninitialized: false,
    cookie: {
        secure: process.env.NODE_ENV === 'production',
        httpOnly: true,
        maxAge: 24 * 60 * 60 * 1000, // 24 hours
        sameSite: process.env.NODE_ENV === 'production' ? 'strict' : 'lax'
    }
};

if (process.env.SESSION_DOMAIN) {
    sessionConfig.cookie.domain = process.env.SESSION_DOMAIN;
}

app.use(session(sessionConfig));
app.use(express.static(__dirname + '/public'));

app.get("/privacy", (req, res) => {
    res.sendFile(__dirname + '/public/privacy.html');
});

app.get("/overview", (req, res) => {
    res.sendFile(__dirname + '/public/overview.html');
});

app.get("/", (req, res) => {
    res.sendFile(__dirname + '/public/main.html');
});

app.get("/login", (req, res) => {
    res.sendFile(__dirname + '/public/login.html');
});

app.post("/api/auth/login", validateUid, async (req, res) => {
    try {
        const uid = req.uid;

        await supabase
            .from('brain_users')
            .upsert([
                {
                    uid: uid
                }
            ]);

        const { data: userRow } = await supabase
            .from('brain_users')
            .select('has_key')
            .eq('uid', uid)
            .single();

        req.session.userId = uid;
        req.session.loginTime = new Date().toISOString();

        req.session.save((err) => {
            if (err) {
                console.error('Session save error:', err);
                return res.status(500).json({ error: 'Login failed' });
            }

            res.json({
                success: true,
                uid: uid,
                hasKey: userRow?.has_key || false
            });
        });
    } catch (error) {
        console.error('Login error:', error);
        res.status(500).json({ error: 'Login failed' });
    }
});

app.post("/api/auth/logout", (req, res) => {
    req.session.destroy((err) => {
        if (err) {
            return res.status(500).json({ error: 'Logout failed' });
        }
        res.clearCookie('connect.sid');
        res.json({ success: true });
    });
});

app.get('/api/profile', requireAuth, async (req, res) => {
    try {
        const uid = req.uid;
        const { data: rows, error } = await supabase
            .from('brain_users')
            .select('uid, has_key')
            .eq('uid', uid);

        if (error) {
            throw error;
        }

        let profileRow = rows && rows.length > 0 ? rows[0] : null;

        if (!profileRow) {
            const { data: insertedRows, error: upsertError } = await supabase
                .from('brain_users')
                .upsert([{ uid }])
                .select('uid, has_key')
                .eq('uid', uid);

            if (upsertError) {
                throw upsertError;
            }

            profileRow = insertedRows && insertedRows.length > 0
                ? insertedRows[0]
                : { uid, has_key: false };
        }

        res.json({
            uid: profileRow.uid,
            hasKey: profileRow.has_key ?? false,
            loginTime: req.session.loginTime
        });
    } catch (error) {
        console.error('Profile error:', error);
        res.status(500).json({ error: 'Error fetching profile' });
    }
});

app.get('/api/code-check', requireAuth, async (req, res) => {
    try {
        const { data, error } = await supabase
            .from('brain_users')
            .select('code_check')
            .eq('uid', req.uid)
            .single();
        if (error) {
            return res.json({ cipher: null });
        }
        res.json({ cipher: data.code_check });
    } catch (err) {
        res.json({ cipher: null });
    }
});

app.post('/api/code-check', requireAuth, async (req, res) => {
    try {
        const { cipher } = req.body;
        await supabase
            .from('brain_users')
            .update({ code_check: cipher, has_key: true })
            .eq('uid', req.uid);
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: 'Failed to save verification' });
    }
});

app.get("/setup", async (req, res) => {
    res.json({ 'is_setup_completed': true });
});

app.put('/api/node/:nodeId', requireAuth, validateNodeData, async (req, res) => {
    try {
        const { nodeId } = req.params;
        const { name, type } = req.body;
        const uid = req.uid;

        if (!nodeId || typeof nodeId !== 'string' || nodeId.length > 100) {
            return res.status(400).json({ error: 'Invalid node ID' });
        }

        await supabase
            .from('memory_nodes')
            .update({
                name: name,
                type: type
            })
            .eq('uid', uid)
            .eq('node_id', nodeId);

        // Get updated memory graph
        const memoryGraph = await loadMemoryGraph(uid);
        const visualizationData = {
            nodes: Array.from(memoryGraph.nodes.values()),
            relationships: memoryGraph.relationships
        };

        res.json(visualizationData);
    } catch (error) {
        console.error('Error updating node:', error);
        res.status(500).json({ error: 'Error updating node' });
    }
});

app.delete('/api/node/:nodeId', requireAuth, async (req, res) => {
    const { nodeId } = req.params;
    const uid = req.uid;

    if (!nodeId || typeof nodeId !== 'string' || nodeId.length > 100) {
        return res.status(400).json({ error: 'Invalid node ID' });
    }

    try {
        await supabase
            .from('memory_relationships')
            .delete()
            .eq('uid', uid)
            .or(`source.eq.${nodeId},target.eq.${nodeId}`);

        await supabase
            .from('memory_nodes')
            .delete()
            .eq('uid', uid)
            .eq('node_id', nodeId);

        // Get updated memory graph
        const memoryGraph = await loadMemoryGraph(uid);
        const visualizationData = {
            nodes: Array.from(memoryGraph.nodes.values()),
            relationships: memoryGraph.relationships
        };

        res.json(visualizationData);
    } catch (error) {
        console.error('Error deleting node:', error);
        res.status(500).json({ error: 'Error deleting node' });
    }
});

app.post('/api/chat', requireAuth, validateTextInput, async (req, res) => {
    try {
        const { message, context, key } = req.body;

        if (!message || typeof message !== 'string') {
            return res.status(400).json({ error: 'Message is required' });
        }

        let finalContext = context;

        if (key) {
            const memoryGraph = await loadMemoryGraph(req.uid);
            const nodes = [];
            for (const node of memoryGraph.nodes.values()) {
                nodes.push({
                    id: node.id,
                    type: decryptText(node.type, key),
                    name: decryptText(node.name, key),
                    connections: node.connections
                });
            }
            const relationships = memoryGraph.relationships.map(r => ({
                source: r.source,
                target: r.target,
                action: decryptText(r.action, key)
            }));
            finalContext = { nodes, relationships };
        }

        const response = await processChatWithGPT(message, finalContext || { nodes: [], relationships: [] });
        res.json({ response });
    } catch (error) {
        console.error('Error:', error);
        res.status(500).json({ error: 'Error processing chat' });
    }
});

app.get('/api/memory-graph', requireAuth, async (req, res) => {
    try {
        const uid = req.uid;
        const sample = req.query.sample === 'true';

        let memoryGraph = await loadMemoryGraph(uid);

        if (sample) {
            memoryGraph = addSampleData(uid, 500, 800);
        }
        const visualizationData = {
            nodes: Array.from(memoryGraph.nodes.values()),
            relationships: memoryGraph.relationships
        };

        res.json(visualizationData);
    } catch (error) {
        console.error('Error:', error);
        res.status(500).json({ error: 'Error fetching memory graph' });
    }
});

app.post('/api/memory-graph', requireAuth, async (req, res) => {
    try {
        const uid = req.uid;
        const result = await saveMemoryGraph(uid, req.body);
        res.json({ success: true, ...result });
    } catch (error) {
        console.error('Error saving memory graph:', error);
        res.status(500).json({ error: 'Error saving memory graph' });
    }
});

app.post('/api/process-text', validateTextInput, async (req, res) => {
    try {
        const { transcript_segments } = req.body;
        const uid = resolveUid(req);

        if (!uid) {
            return res.status(401).json({ error: 'Unauthorized: missing or invalid user context' });
        }
        req.uid = uid;

        if (!transcript_segments || !Array.isArray(transcript_segments)) {
            return res.status(400).json({ error: 'Transcript segments are required' });
        }

        let text = '';
        for (const segment of transcript_segments) {
            if (segment && segment.speaker && segment.text) {
                text += `${segment.speaker}: ${segment.text}\n`;
            }
        }

        if (!text.trim()) {
            return res.status(400).json({ error: 'No valid text content found' });
        }

        // Load existing memory graph to avoid creating duplicates
        const existingMemory = await loadMemoryGraph(uid);

        const processedData = await processTextWithGPT(text, existingMemory);

        const entities = Array.isArray(processedData.entities) ? processedData.entities : [];
        const relationships = Array.isArray(processedData.relationships) ? processedData.relationships : [];

        const persistPayload = {
            entities: entities.map(entity => ({
                id: entity.id,
                type: entity.type,
                name: entity.name,
                connections: entity.connections ?? 0
            })),
            relationships: relationships.map(rel => ({
                source: rel.source,
                target: rel.target,
                action: rel.action
            }))
        };

        let saveResult = { nodesUpserted: 0, relationshipsInserted: 0 };

        if (persistPayload.entities.length > 0 || persistPayload.relationships.length > 0) {
            saveResult = await saveMemoryGraph(uid, persistPayload);
        }

        console.info(`Processed text for uid=${uid}: ${saveResult.nodesUpserted} nodes upserted, ${saveResult.relationshipsInserted} relationships inserted.`);

        res.json({
            ...processedData,
            saveResult
        });
    } catch (error) {
        console.error('Error processing text:', error);
        res.status(500).json({ error: 'Error processing text' });
    }
});

app.post('/api/delete-all-data', requireAuth, async (req, res) => {
    try {
        const uid = req.uid;
        await deleteAllUserData(uid);

        // Destroy session since user data is deleted
        req.session.destroy((err) => {
            if (err) {
                console.error('Session destruction error:', err);
            }
        });

        res.json({ success: true, message: 'All data deleted successfully' });
    } catch (error) {
        console.error('Error in delete-all-data endpoint:', error);
        res.status(500).json({ error: 'Failed to delete data' });
    }
});

app.post('/api/generate-description', requireAuth, async (req, res) => {
    try {
        const { node, connections } = req.body;

        if (!node || !node.name || !node.type) {
            return res.status(400).json({ error: 'Invalid node data' });
        }

        if (!connections || !Array.isArray(connections)) {
            return res.status(400).json({ error: 'Invalid connections data' });
        }

        const prompt = `Analyze this node and its connections in a brain-like memory network:

Node: ${node.name} (Type: ${node.type})

Connections:
${connections.map(c => `- ${c.isSource ? 'Connects to' : 'Connected from'} ${c.node.name} through action: ${c.action}`).join('\n')}

Provide a concise but insightful description that:
1. Summarizes the node's role and significance
2. Highlights key relationships and patterns
3. Suggests potential implications or insights

Keep the description natural and engaging, focusing on the most meaningful connections.`;

        const completion = await openai.chat.completions.create({
            model: "gpt-4o-mini",
            messages: [
                {
                    role: "system",
                    content: "You are an insightful analyst helping understand connections in a memory network. Focus on meaningful patterns and relationships."
                },
                {
                    role: "user",
                    content: prompt
                }
            ],
            temperature: 0.7,
            max_tokens: 200
        });

        res.json({ description: completion.choices[0].message.content });
    } catch (error) {
        console.error('Error generating description:', error);
        res.status(500).json({ error: 'Failed to generate description' });
    }
});

app.post('/api/enrich-content', requireAuth, validateInput, async (req, res) => {
    try {
        const { query, type } = req.body;

        // Configure axios with proper headers and timeout
        const axiosConfig = {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            },
            timeout: 5000,
            maxRedirects: 5,
            validateStatus: (status) => status >= 200 && status < 300
        };

        // Search for images with rate limiting
        const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(query + ' ' + type)}&tbm=isch`;

        const response = await axios.get(searchUrl, axiosConfig);
        const cleanHtml = sanitizeHtml(response.data, {
            allowedTags: [],
            allowedAttributes: {},
            textFilter: function (text) {
                return text.replace(/[^\x20-\x7E]/g, '');
            }
        });

        // Extract and validate image URLs
        const regex = /\["(https?:\/\/[^"]+\.(?:jpg|jpeg|png|gif))"/gi;
        const images = [];
        const seenUrls = new Set();
        let match;

        while ((match = regex.exec(cleanHtml)) !== null && images.length < 4) {
            try {
                const imageUrl = match[1];

                // Skip if we've seen this URL before
                if (seenUrls.has(imageUrl)) {
                    continue;
                }

                // Validate URL
                const parsedUrl = new URL(imageUrl);
                if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
                    continue;
                }

                // Add valid image
                images.push({
                    url: imageUrl,
                    title: `Related image for ${query}`,
                    source: parsedUrl.hostname
                });

                seenUrls.add(imageUrl);
            } catch (err) {
                console.warn('Invalid image URL found:', err.message);
                continue;
            }
        }

        // Return results with appropriate cache headers
        res.set('Cache-Control', 'private, max-age=3600');
        res.json({
            images,
            links: [],
            query,
            timestamp: new Date().toISOString()
        });

    } catch (error) {
        console.error('Error enriching content:', error);

        // Handle specific error types
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({
                error: 'Request timeout',
                images: [],
                links: []
            });
        }

        if (axios.isAxiosError(error) && error.response) {
            return res.status(error.response.status || 500).json({
                error: 'External service error',
                images: [],
                links: []
            });
        }

        res.status(500).json({
            error: 'Internal server error',
            images: [],
            links: []
        });
    }
});

app.use((req, res, next) => {
    res.status(404).sendFile(__dirname + '/public/404.html');
});

app.use((err, req, res, next) => {
    const result = handleDatabaseError(err, 'request handling');
    console.error('Unhandled error:', result.error);
    res.status(result.status).sendFile(__dirname + '/public/500.html');
});

app.listen(port, () => {
    console.log(`Server running on port ${port}`);
});

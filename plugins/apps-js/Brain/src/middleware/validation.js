function validateUid(req, res, next) {
    // Handle both JSON and form data
    const uid = req.body.uid || req.query.uid;
    if (!uid || typeof uid !== 'string' || uid.length < 3 || uid.length > 50) {
        return res.status(400).json({ error: 'Invalid user ID format' });
    }
    // Simple sanitization
    req.uid = uid.replace(/[^a-zA-Z0-9-_]/g, '');
    next();
}

function validateTextInput(req, res, next) {
    const { message, transcript_segments } = req.body;

    if (message && (typeof message !== 'string')) {
        return res.status(400).json({ error: 'Invalid message format' });
    }

    if (transcript_segments && (!Array.isArray(transcript_segments))) {
        return res.status(400).json({ error: 'Invalid transcript format' });
    }

    next();
}

function validateNodeData(req, res, next) {
    const { name, type } = req.body;

    if (!name || typeof name !== 'string' || name.length > 1000) {
        return res.status(400).json({ error: 'Invalid node name' });
    }

    if (!type || typeof type !== 'string' || type.length > 1000) {
        return res.status(400).json({ error: 'Invalid node type' });
    }

    next();
}

const validateInput = (req, res, next) => {
    const { query, type } = req.body;

    if (!query || typeof query !== 'string' || query.length > 200) {
        return res.status(400).json({
            error: 'Invalid query parameter'
        });
    }

    if (!type || typeof type !== 'string' || type.length > 50) {
        return res.status(400).json({
            error: 'Invalid type parameter'
        });
    }

    // Remove any potentially harmful characters
    req.body.query = query.replace(/[^\w\s-]/g, '');
    req.body.type = type.replace(/[^\w\s-]/g, '');

    next();
};

module.exports = {
    validateUid,
    validateTextInput,
    validateNodeData,
    validateInput
};

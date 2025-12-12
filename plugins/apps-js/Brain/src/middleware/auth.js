function requireAuth(req, res, next) {
    if (!req.session) {
        return res.status(401).json({ error: 'No session - please login again' });
    }

    if (!req.session.userId) {
        return res.status(401).json({ error: 'Session invalid - please login again' });
    }

    req.uid = req.session.userId;
    next();
}

module.exports = { requireAuth };

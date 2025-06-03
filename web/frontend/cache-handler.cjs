// Custom cache handler to bypass 2MB fetch cache limit
const FileSystemCache = require('next/dist/server/lib/incremental-cache/file-system-cache.js');

module.exports = FileSystemCache; 
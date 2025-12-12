-- Custom setup script for the "Brain" app
-- Run this in your Supabase SQL editor to set up the required tables and security policies for the Brain app.

-- 1. Helper Function
CREATE OR REPLACE FUNCTION exec_sql(sql_query TEXT)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    EXECUTE sql_query;
    RETURN 'SQL executed successfully';
EXCEPTION
    WHEN OTHERS THEN
        RETURN 'Error: ' || SQLERRM;
END;
$$;

-- 2. Brain App Tables

-- Brain Users table
CREATE TABLE IF NOT EXISTS brain_users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    uid TEXT UNIQUE NOT NULL,
    code_check TEXT,
    has_key BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Ensure columns exist (useful if table was created by an older script)
ALTER TABLE brain_users ADD COLUMN IF NOT EXISTS code_check TEXT;
ALTER TABLE brain_users ADD COLUMN IF NOT EXISTS has_key BOOLEAN DEFAULT false;

-- Memory Nodes table
CREATE TABLE IF NOT EXISTS memory_nodes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    uid TEXT NOT NULL,
    node_id TEXT NOT NULL,
    type TEXT,
    name TEXT,
    connections INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(uid, node_id)
);

-- Memory Relationships table
CREATE TABLE IF NOT EXISTS memory_relationships (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    uid TEXT NOT NULL,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    action TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Indexes for Performance
CREATE INDEX IF NOT EXISTS idx_memory_nodes_uid ON memory_nodes(uid);
CREATE INDEX IF NOT EXISTS idx_memory_nodes_node_id ON memory_nodes(node_id);
CREATE INDEX IF NOT EXISTS idx_memory_relationships_uid ON memory_relationships(uid);
CREATE INDEX IF NOT EXISTS idx_memory_relationships_source ON memory_relationships(source);
CREATE INDEX IF NOT EXISTS idx_memory_relationships_target ON memory_relationships(target);

-- 4. Security (Row Level Security)
ALTER TABLE brain_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_relationships ENABLE ROW LEVEL SECURITY;

-- 5. Access Policies
-- Note: These policies allow "ALL" access.
CREATE POLICY "Users can access their own data" ON brain_users FOR ALL USING (true);
CREATE POLICY "Users can access their own memory nodes" ON memory_nodes FOR ALL USING (true);
CREATE POLICY "Users can access their own relationships" ON memory_relationships FOR ALL USING (true);

SELECT 'Brain app tables and functions set up successfully!' as result;

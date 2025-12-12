const supabase = require('../config/supabase');
const { getRandomElement } = require('../utils/helpers');

async function loadMemoryGraph(uid) {
    const nodes = new Map();
    const relationships = [];

    try {
        // Load nodes
        const { data: dbNodes } = await supabase
            .from('memory_nodes')
            .select()
            .eq('uid', uid);

        dbNodes.forEach(node => {
            nodes.set(node.node_id, {
                id: node.node_id,
                type: node.type,
                name: node.name,
                connections: node.connections
            });
        });

        // Load relationships
        const { data: dbRelationships } = await supabase
            .from('memory_relationships')
            .select()
            .eq('uid', uid);

        relationships.push(...dbRelationships.map(rel => ({
            source: rel.source,
            target: rel.target,
            action: rel.action
        })));

        return { nodes, relationships };
    } catch (error) {
        console.error('Error loading memory graph:', error);
        throw error;
    }
}

async function saveMemoryGraph(uid, newData) {
    try {
        // Accept either "entities" (preferred) or "nodes" (fallback) to be robust to client payloads
        const incomingEntities = Array.isArray(newData.entities) && newData.entities.length > 0
            ? newData.entities
            : (Array.isArray(newData.nodes) ? newData.nodes : []);

        const nodeRows = incomingEntities.map(entity => ({
            uid,
            node_id: entity.id,
            type: entity.type,
            name: entity.name,
            connections: entity.connections ?? 0
        }));

        let nodesResult = { count: 0 };
        if (nodeRows.length > 0) {
            // Use explicit conflict target so PostgREST performs a true UPSERT on the composite unique key
            const { data: nodeData, error: nodeError } = await supabase
                .from('memory_nodes')
                .upsert(nodeRows, { onConflict: 'uid,node_id' })
                .select('uid,node_id');

            if (nodeError) {
                throw nodeError;
            }
            nodesResult.count = Array.isArray(nodeData) ? nodeData.length : 0;
        }

        const relationshipRows = (newData.relationships || []).map(rel => ({
            uid,
            source: rel.source,
            target: rel.target,
            action: rel.action
        }));

        let relResult = { count: 0 };
        if (relationshipRows.length > 0) {
            // Insert relationships; table has no unique composite, so avoid unintended conflict behavior
            const { data: relData, error: relationshipError } = await supabase
                .from('memory_relationships')
                .insert(relationshipRows)
                .select('uid,source,target');

            if (relationshipError) {
                throw relationshipError;
            }
            relResult.count = Array.isArray(relData) ? relData.length : 0;
        }

        return {
            nodesUpserted: nodesResult.count,
            relationshipsInserted: relResult.count
        };
    } catch (error) {
        console.error('Failed to persist memory graph:', error);
        throw error;
    }
}

function addSampleData(uid, numNodes = 3000, numRelationships = 5000) {
    const types = ['person', 'location', 'event', 'concept'];
    const actions = ['knows', 'lives_in', 'attended', 'connected_to', 'influenced', 'created'];

    const firstNames = ['Liam', 'Emma', 'Noah', 'Olivia', 'Ethan', 'Ava', 'James', 'Sophia', 'Lucas', 'Mia'];
    const lastNames = ['Johnson', 'Smith', 'Brown', 'Williams', 'Taylor', 'Anderson', 'Davis', 'Miller', 'Wilson', 'Moore'];
    const places = ['New York', 'Berlin', 'Tokyo', 'London', 'Paris', 'Sydney', 'Toronto', 'Madrid', 'Rome', 'Amsterdam'];
    const events = ['Tech Conference', 'Music Festival', 'Art Exhibition', 'Startup Meetup', 'Science Fair'];
    const concepts = ['Quantum Computing', 'AI Ethics', 'Sustainable Energy', 'Blockchain Security', 'Neural Networks'];

    let nodes = [];
    let relationships = [];

    for (let i = 0; i < numNodes; i++) {
        const id = `node-${i}`;
        const type = getRandomElement(types);
        let name;

        switch (type) {
            case 'Person':
                name = `${getRandomElement(firstNames)} ${getRandomElement(lastNames)}`;
                break;
            case 'Location':
                name = getRandomElement(places);
                break;
            case 'Event':
                name = getRandomElement(events);
                break;
            case 'Concept':
                name = getRandomElement(concepts);
                break;
        }

        nodes.push({ id, type, name, uid });
    }

    for (let i = 0; i < numRelationships; i++) {
        const source = getRandomElement(nodes).id;
        const target = getRandomElement(nodes).id;
        if (source !== target) {
            const action = getRandomElement(actions);
            relationships.push({ source, target, action, uid });
        }
    }

    return { nodes, relationships };
}

async function deleteAllUserData(uid) {
    try {
        await supabase
            .from('memory_relationships')
            .delete()
            .eq('uid', uid);

        await supabase
            .from('memory_nodes')
            .delete()
            .eq('uid', uid);

        await supabase
            .from('brain_users')
            .delete()
            .eq('uid', uid);

        return true;
    } catch (error) {
        console.error('Error deleting user data:', error);
        throw error;
    }
}

module.exports = {
    loadMemoryGraph,
    saveMemoryGraph,
    addSampleData,
    deleteAllUserData
};

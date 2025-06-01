const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

/**
 * Initialize Supabase connection
 * @returns {Object} Supabase client
 */
const initializeDatabase = () => {
  try {
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
    
    console.log('Supabase client initialized');

    // Add simple connection check
    (async () => {
      try {
        const { data, error } = await supabase.from('users').select('count').limit(1);
        if (error) {
          console.error('Supabase connection error:', error);
        } else {
          console.log('Supabase connected successfully');
        }
      } catch (err) {
        console.error('Error checking Supabase connection:', err);
      }
    })();

    return supabase;
  } catch (error) {
    console.error('Supabase initialization error:', error);
    return null;
  }
};

module.exports = {
  initializeDatabase,
  // Export commonly used database operations as helper functions
  async findById(table, id) {
    const supabase = initializeDatabase();
    const { data, error } = await supabase
      .from(table)
      .select('*')
      .eq('id', id)
      .single();
      
    if (error) {
      console.error(`Error finding ${table} by ID:`, error);
      return null;
    }
    
    return data;
  },
  
  async findByUserId(table, userId) {
    const supabase = initializeDatabase();
    const { data, error } = await supabase
      .from(table)
      .select('*')
      .eq('user_id', userId);
      
    if (error) {
      console.error(`Error finding ${table} by user ID:`, error);
      return [];
    }
    
    return data;
  },
  
  async findOne(table, conditions) {
    const supabase = initializeDatabase();
    let query = supabase
      .from(table)
      .select('*');
    
    // Apply each condition
    Object.entries(conditions).forEach(([key, value]) => {
      query = query.eq(key, value);
    });
    
    // Get single result
    const { data, error } = await query.single();
    
    if (error && error.code !== 'PGRST116') {
      console.error(`Error finding in ${table}:`, error);
      return null;
    }
    
    return data;
  },
  
  async insertOne(table, record) {
    const supabase = initializeDatabase();
    const { data, error } = await supabase
      .from(table)
      .insert(record)
      .select();
      
    if (error) {
      console.error(`Error inserting into ${table}:`, error);
      return null;
    }
    
    return data[0];
  },
  
  async updateOne(table, id, updates) {
    const supabase = initializeDatabase();
    const { data, error } = await supabase
      .from(table)
      .update(updates)
      .eq('id', id)
      .select();
      
    if (error) {
      console.error(`Error updating ${table}:`, error);
      return null;
    }
    
    return data[0];
  },
  
  async upsert(table, record) {
    const supabase = initializeDatabase();
    const { data, error } = await supabase
      .from(table)
      .upsert(record)
      .select();
      
    if (error) {
      console.error(`Error upserting into ${table}:`, error);
      return null;
    }
    
    return data[0];
  },
  
  async deleteOne(table, id) {
    const supabase = initializeDatabase();
    const { error } = await supabase
      .from(table)
      .delete()
      .eq('id', id);
      
    if (error) {
      console.error(`Error deleting from ${table}:`, error);
      return false;
    }
    
    return true;
  }
}; 


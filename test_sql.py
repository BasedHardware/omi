import psycopg
from psycopg.sql import SQL, Identifier

query = SQL('SELECT key FROM {} WHERE namespace = %s').format(Identifier('jobs'))
print(query.as_string(psycopg.connect("postgresql://postgres:postgres@localhost:5432/postgres")))

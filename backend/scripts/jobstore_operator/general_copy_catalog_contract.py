"""Fixed source/profile/catalog statements. No actual-host binding defaults."""

PROFILE = 'general-copy-catalog-v2.c282.schema8'
SOURCE = 'c2824362c2a52925def3ef83f13c3b58487a6aa0'
TREE = 'a5c8acbd193b6b85661c9fe91759b2ec0eb80608'
WRAPPER_SHA = '1b6a0a1ed5ca8dbc7f8087ae51441539a8aa9b4f4da2171932e2f08af9de699f'
GUARD_SHA = '6309e8242ad2469cfc2076379a61a79c5dbb89aa7faf5d26dba9aeade6b67400'
DATABASE_VECTOR = (
    (1, 'doc_mode_store', '4f121b4df8ffe9c8369cc5b920f94010d3ada94b11909c49318db9f49f6ba205'),
    (2, 'outbox', '6e53430b74b89c7a2e3b031faec7766f0374fed8aefa4e916fb19e27950d4e6e'),
    (3, 'outbox_wake_pending', '8b97c1aa851f9801fff6a214184d74f6606fc4a0613b1a1deb7117fec7d9d4b4'),
    (4, 'merge_and_projection_hints', 'b6ff0b0093c7ae8f89bc8bc30648048d03e5f07683c73ddc3bcd0d246cbd4500'),
    (5, 'byte_order_key_indexes', '650f78f15a49de950f05b6e3c361a9ebf257e36fdb1f7f58860cca2d7af32620'),
    (6, 'transactional_fresh_gate', '6e9baf9cd37300a3d134f9354df72786548efdd35b48f7b6f0a8833834660cdd'),
    (7, 'ready_owners', '9963c19a3d8c4c87578937c3b2b3cdf4635fc3211209e6a23b4a08f5ebb76cfa'),
    (8, 'allowance_holds', 'b89f731ff1f45ba0a9922e8cf0377a7b05054c76df74de9c67825f0606b6acdb'),
)
SOURCE_VECTOR = DATABASE_VECTOR + (
    (9, 'protected_share', '8d7fd181ca9f6ad4d05da782014f8876b2ddefc9065622a2eb42d0da9624e5ea'),
)
APP = ('control', 'docs', 'jobs', 'results')
RELATIONS = ('control', 'docs', 'jobs', 'results', 'schema_migrations')
APP_COLUMNS = ('namespace', 'key', 'tbl', 'doc')
META_COLUMNS = ('version', 'name', 'checksum')
INDEXES = ('jobs_due_leased_c', 'jobs_due_result_c', 'jobs_due_retry_c')
ABSENT_INDEXES = ('jobs_protected_retry', 'jobs_protected_ready')
COLUMNS = {name: ('namespace', 'key', 'doc') for name in APP}
COLUMNS['docs'] = ('namespace', 'tbl', 'key', 'doc')
SQL = {
    'B01': 'BEGIN READ ONLY',
    'B02': "SET LOCAL statement_timeout = '5s'",
    'B03': "SET LOCAL lock_timeout = '5s'",
    'I01': "SELECT pg_catalog.current_database(), current_user, session_user, pg_catalog.host(pg_catalog.inet_server_addr()), pg_catalog.inet_server_port(), pg_catalog.current_setting('server_version_num'), pg_catalog.current_setting('transaction_read_only')",
    'I02': "SELECT ssl,version,cipher FROM pg_catalog.pg_stat_ssl WHERE pid=pg_catalog.pg_backend_pid()",
    'R01': "SELECT n.nspname,c.relname,c.oid,c.relkind,c.relrowsecurity,c.relforcerowsecurity,pg_catalog.row_security_active(c.oid),pg_catalog.pg_get_userbyid(c.relowner),pg_catalog.pg_has_role(current_user,c.relowner,'USAGE') FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY(%s) ORDER BY c.relname LIMIT 6",
    'R02': "SELECT c.relname,a.attname,tn.nspname,t.typname,a.attnotnull,a.attnum,a.attgenerated,pg_catalog.pg_get_expr(d.adbin,d.adrelid) FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_type t ON t.oid=a.atttypid JOIN pg_catalog.pg_namespace tn ON tn.oid=t.typnamespace LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE n.nspname='public' AND c.relname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum LIMIT 257",
    'R03': "SELECT c.relname,k.conkey,i.indisprimary,i.indisunique,i.indisready,i.indisvalid,k.condeferrable,k.condeferred,i.indimmediate FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid=k.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_index i ON i.indexrelid=k.conindid WHERE n.nspname='public' AND c.relname=ANY(%s) AND k.contype='p' ORDER BY c.relname LIMIT 6",
    'X01': "SELECT c.relname,t.relname,i.indisready,i.indisvalid,pg_catalog.pg_get_indexdef(c.oid) FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid JOIN pg_catalog.pg_class t ON t.oid=i.indrelid JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='public' AND c.relname=ANY(%s) ORDER BY c.relname LIMIT 6",
    'P01': "SELECT pg_catalog.has_database_privilege(current_user,pg_catalog.current_database(),'CONNECT'),pg_catalog.has_schema_privilege(current_user,'public','USAGE')",
    'P02': "SELECT rolname,rolsuper,rolinherit,rolbypassrls FROM pg_catalog.pg_roles WHERE rolname=current_user",
    'P03': "SELECT c.relname,pg_catalog.has_table_privilege(current_user,c.oid,'SELECT'),pg_catalog.has_table_privilege(current_user,c.oid,'INSERT'),pg_catalog.has_table_privilege(current_user,c.oid,'UPDATE'),pg_catalog.has_table_privilege(current_user,c.oid,'DELETE') FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY(%s) ORDER BY c.relname LIMIT 5",
    'P04': "SELECT c.relname,a.attname,pg_catalog.has_column_privilege(current_user,c.oid,a.attnum,'SELECT'),pg_catalog.has_column_privilege(current_user,c.oid,a.attnum,'INSERT'),pg_catalog.has_column_privilege(current_user,c.oid,a.attnum,'UPDATE') FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY(%s) AND a.attname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum LIMIT 257",
    'P05': "SELECT a.attname,pg_catalog.has_column_privilege(current_user,c.oid,a.attnum,'SELECT') FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname='schema_migrations' AND a.attname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum LIMIT 4",
    'V01': 'SELECT version,name,checksum FROM public.schema_migrations ORDER BY version LIMIT 10',
    'F01': 'ROLLBACK',
}
PARAMS = {
    'R01': (list(RELATIONS),),
    'R02': (list(RELATIONS),),
    'R03': (list(RELATIONS),),
    'X01': (list(INDEXES + ABSENT_INDEXES),),
    'P03': (list(APP),),
    'P04': (list(APP), list(APP_COLUMNS)),
    'P05': (list(META_COLUMNS),),
}
ORDER = tuple(SQL)
BINDING_KEYS = {
    'version',
    'profile',
    'source_sha',
    'source_tree',
    'image_digest',
    'probe_sha256',
    'contract_sha256',
    'structure_sha256',
    'wrapper_sha256',
    'guard_sha256',
    'uid',
    'home',
    'namespace',
    'ksa',
    'pod_uid',
    'pod_name',
    'hostname',
    'target_host',
    'target_port',
    'database',
    'current_role',
    'session_role',
    'server_address',
    'server_port',
    'server_major',
    'role_flags',
    'git_path',
    'git_sha256',
    'python_path',
    'python_sha256',
    'source_root',
    'wrapper_path',
    'guard_path',
    'structure_path',
}

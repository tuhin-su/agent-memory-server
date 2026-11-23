import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

from .config import settings

pool: ConnectionPool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    name        text PRIMARY KEY,
    template    text,
    created_at  timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agents (
    name        text PRIMARY KEY,
    token_hash  text UNIQUE NOT NULL,
    is_admin    boolean DEFAULT false,
    created_at  timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS permissions (
    agent    text REFERENCES agents(name) ON DELETE CASCADE,
    project  text NOT NULL,                 -- project name or '*' for all
    role     text NOT NULL CHECK (role IN ('read', 'write')),
    PRIMARY KEY (agent, project)
);

-- The "hash map": path -> sha256 -> version. Unchanged hash = skip write and skip re-embedding.
CREATE TABLE IF NOT EXISTS files (
    id             bigserial PRIMARY KEY,
    project        text NOT NULL REFERENCES projects(name) ON DELETE CASCADE,
    path           text NOT NULL,
    sha256         text NOT NULL,
    size           bigint,
    version        int DEFAULT 1,
    updated_by     text,
    updated_at     timestamptz DEFAULT now(),
    indexed_sha256 text,
    UNIQUE (project, path)
);

CREATE TABLE IF NOT EXISTS chunks (
    id         bigserial PRIMARY KEY,
    file_id    bigint NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    idx        int NOT NULL,
    text       text NOT NULL,
    sha256     text NOT NULL,
    embedding  vector({dim}),
    tsv        tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);
CREATE INDEX IF NOT EXISTS chunks_file ON chunks(file_id);
CREATE INDEX IF NOT EXISTS chunks_tsv  ON chunks USING gin(tsv);
CREATE INDEX IF NOT EXISTS chunks_emb  ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS audit_log (
    id       bigserial PRIMARY KEY,
    at       timestamptz DEFAULT now(),
    agent    text,
    action   text,
    project  text,
    path     text
);
"""


def _configure(conn):
    register_vector(conn)
    conn.commit()  # pool requires the connection to be idle after configure


def init_db():
    global pool
    with psycopg.connect(settings.database_url, autocommit=True) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
    pool = ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=10,
        configure=_configure,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    pool.wait()
    with pool.connection() as conn:
        conn.execute(SCHEMA.replace("{dim}", str(settings.embed_dim)))


def close_db():
    if pool:
        pool.close()

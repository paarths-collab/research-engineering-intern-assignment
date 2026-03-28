-- ============================================================
-- Cross-Platform Catalyst Attribution Engine — Neon Schema
-- Run once in Neon SQL editor
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── CORE REDDIT DATA ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS posts (
    id              TEXT PRIMARY KEY,
    subreddit       TEXT NOT NULL,
    title           TEXT NOT NULL,
    author          TEXT,
    score           INT  DEFAULT 0,
    num_comments    INT  DEFAULT 0,
    created_utc     TIMESTAMP NOT NULL,
    source          TEXT DEFAULT 'historical',  -- 'historical' | 'reddit_api'
    embedding       VECTOR(384),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_posts_date      ON posts(created_utc);
CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit);
CREATE INDEX IF NOT EXISTS idx_posts_source    ON posts(source);

-- ── COMMENTS ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS comments (
    id          TEXT PRIMARY KEY,
    post_id     TEXT REFERENCES posts(id) ON DELETE CASCADE,
    author      TEXT,
    body        TEXT,
    score       INT DEFAULT 0,
    created_utc TIMESTAMP,
    embedding   VECTOR(384),
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_date ON comments(created_utc);

-- ── VOLUME ANALYTICS ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS daily_volume (
    date         DATE PRIMARY KEY,
    post_count   INT,
    rolling_mean FLOAT,
    rolling_std  FLOAT,
    z_score      FLOAT
);

-- ── NETWORK / ECHO CHAMBER ───────────────────────────────────

CREATE TABLE IF NOT EXISTS echo_chamber_scores (
    subreddit          TEXT PRIMARY KEY,
    echo_score         FLOAT,
    polarization_score FLOAT,
    created_at         TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subreddit_domain_flow (
    subreddit  TEXT,
    domain     TEXT,
    post_count INT,
    PRIMARY KEY (subreddit, domain)
);

CREATE TABLE IF NOT EXISTS top_distinctive_domains (
    subreddit             TEXT,
    domain                TEXT,
    count                 INT,
    category              TEXT,
    lift                  FLOAT,
    p_domain_given_sub    FLOAT,
    p_domain_global       FLOAT,
    PRIMARY KEY (subreddit, domain)
);

CREATE TABLE IF NOT EXISTS bridge_authors (
    author      TEXT,
    subreddit_1 TEXT,
    subreddit_2 TEXT,
    bridge_score FLOAT,
    PRIMARY KEY (author, subreddit_1, subreddit_2)
);

-- ── SPIKE ANALYSIS SYSTEM ────────────────────────────────────

CREATE TABLE IF NOT EXISTS spike_jobs (
    job_id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    spike_date   DATE NOT NULL,
    status       TEXT CHECK (status IN ('processing','done','failed')) DEFAULT 'processing',
    error_msg    TEXT,
    created_at   TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_spike_date   ON spike_jobs(spike_date);
CREATE INDEX IF NOT EXISTS idx_spike_status ON spike_jobs(status);

-- ── TOPIC MODELING ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS topic_results (
    job_id       UUID REFERENCES spike_jobs(job_id) ON DELETE CASCADE,
    topic_id     INT,
    size         INT,
    size_percent FLOAT,
    keywords     JSONB,
    centroid     VECTOR(384),
    PRIMARY KEY (job_id, topic_id)
);

-- ── NEWS CACHE ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS news_cache (
    date      DATE,
    headline  TEXT,
    source    TEXT,
    url       TEXT,
    embedding VECTOR(384),
    PRIMARY KEY (date, headline)
);

-- ── COSINE MATCHES ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS news_matches (
    job_id     UUID REFERENCES spike_jobs(job_id) ON DELETE CASCADE,
    topic_id   INT,
    headline   TEXT,
    source     TEXT,
    url        TEXT,
    similarity FLOAT,
    PRIMARY KEY (job_id, topic_id, headline)
);

-- ── SENTIMENT EVOLUTION ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS sentiment_daily (
    job_id           UUID REFERENCES spike_jobs(job_id) ON DELETE CASCADE,
    date             DATE,
    negative_percent FLOAT,
    neutral_percent  FLOAT,
    positive_percent FLOAT,
    sample_count     INT,
    PRIMARY KEY (job_id, date)
);

-- ── VOLUME ACCELERATION ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS spike_metrics (
    job_id           UUID PRIMARY KEY REFERENCES spike_jobs(job_id) ON DELETE CASCADE,
    baseline_count   INT,
    spike_count      INT,
    acceleration_ratio FLOAT
);

-- ── LLM OUTPUT ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS catalyst_briefs (
    job_id     UUID PRIMARY KEY REFERENCES spike_jobs(job_id) ON DELETE CASCADE,
    brief_text TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ── AGENT DIAGNOSTICS ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_diagnostics (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id     UUID REFERENCES spike_jobs(job_id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    status     TEXT CHECK (status IN ('pass','warn','fail')),
    findings   JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_diag_job ON agent_diagnostics(job_id);

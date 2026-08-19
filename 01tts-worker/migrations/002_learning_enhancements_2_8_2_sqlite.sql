-- Listening Lab 2.8.2 Database Migration Script
-- Target: SQLite 3

CREATE TABLE IF NOT EXISTS user_vocabulary_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id VARCHAR(36) NOT NULL,
    word VARCHAR(120) NOT NULL,
    normalized_word VARCHAR(120) NOT NULL,
    phonetic_us VARCHAR(80) NULL,
    phonetic_uk VARCHAR(80) NULL,
    definition_cn TEXT NOT NULL,
    definition_en TEXT NULL,
    context_sentence TEXT NULL,
    content_uuid VARCHAR(36) NULL,
    sentence_start_ms INTEGER NULL,
    sentence_end_ms INTEGER NULL,
    fsrs_state VARCHAR(20) NOT NULL DEFAULT 'NEW',
    stability REAL NOT NULL DEFAULT 0.0,
    difficulty REAL NOT NULL DEFAULT 0.0,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    due_time DATETIME NOT NULL,
    last_review DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_vocabulary_client_word UNIQUE (client_id, normalized_word)
);

CREATE INDEX IF NOT EXISTS ix_user_vocab_client_id ON user_vocabulary_cards (client_id);
CREATE INDEX IF NOT EXISTS ix_user_vocab_norm_word ON user_vocabulary_cards (normalized_word);
CREATE INDEX IF NOT EXISTS ix_user_vocab_due_time ON user_vocabulary_cards (due_time);
CREATE INDEX IF NOT EXISTS ix_user_vocab_content_uuid ON user_vocabulary_cards (content_uuid);

CREATE TABLE IF NOT EXISTS speaking_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL,
    content_uuid VARCHAR(36) NOT NULL,
    scenario VARCHAR(64) NOT NULL,
    role VARCHAR(64) NOT NULL DEFAULT 'TECH_LEAD',
    status VARCHAR(20) NOT NULL DEFAULT 'IN_PROGRESS',
    current_turn INTEGER NOT NULL DEFAULT 1,
    total_turns INTEGER NOT NULL DEFAULT 4,
    topic VARCHAR(255) NULL,
    final_report_json TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_speaking_sessions_client_id ON speaking_sessions (client_id);
CREATE INDEX IF NOT EXISTS ix_speaking_sessions_content_uuid ON speaking_sessions (content_uuid);

CREATE TABLE IF NOT EXISTS speaking_session_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id VARCHAR(64) NOT NULL,
    turn_index INTEGER NOT NULL,
    ai_prompt_text TEXT NOT NULL,
    ai_audio_url VARCHAR(255) NULL,
    user_audio_url VARCHAR(255) NULL,
    user_transcript TEXT NULL,
    pronunciation_score INTEGER NULL,
    grammar_score INTEGER NULL,
    quick_feedback TEXT NULL,
    evaluation_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    evaluation_error TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_speaking_session_turn UNIQUE (session_id, turn_index)
);

CREATE INDEX IF NOT EXISTS ix_speaking_turns_session_id ON speaking_session_turns (session_id);

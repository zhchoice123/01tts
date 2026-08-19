-- Listening Lab 2.8.2 Database Migration Script
-- Target: MySQL 8.0+
-- SQLite uses 002_learning_enhancements_2_8_2_sqlite.sql.

-- 1. Create user_vocabulary_cards table
CREATE TABLE IF NOT EXISTS user_vocabulary_cards (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL,
    word VARCHAR(120) NOT NULL,
    normalized_word VARCHAR(120) NOT NULL,
    phonetic_us VARCHAR(80) NULL,
    phonetic_uk VARCHAR(80) NULL,
    definition_cn TEXT NOT NULL,
    definition_en TEXT NULL,
    context_sentence TEXT NULL,
    content_uuid VARCHAR(36) NULL,
    sentence_start_ms INT NULL,
    sentence_end_ms INT NULL,
    fsrs_state VARCHAR(20) NOT NULL DEFAULT 'NEW',
    stability DOUBLE NOT NULL DEFAULT 0.0,
    difficulty DOUBLE NOT NULL DEFAULT 0.0,
    reps INT NOT NULL DEFAULT 0,
    lapses INT NOT NULL DEFAULT 0,
    due_time DATETIME NOT NULL,
    last_review DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_vocabulary_client_word UNIQUE (client_id, normalized_word),
    INDEX ix_user_vocab_client_id (client_id),
    INDEX ix_user_vocab_norm_word (normalized_word),
    INDEX ix_user_vocab_due_time (due_time),
    INDEX ix_user_vocab_content_uuid (content_uuid)
);


-- 2. Create speaking_sessions table
CREATE TABLE IF NOT EXISTS speaking_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL,
    content_uuid VARCHAR(36) NOT NULL,
    scenario VARCHAR(64) NOT NULL,
    role VARCHAR(64) NOT NULL DEFAULT 'TECH_LEAD',
    status VARCHAR(20) NOT NULL DEFAULT 'IN_PROGRESS',
    current_turn INT NOT NULL DEFAULT 1,
    total_turns INT NOT NULL DEFAULT 4,
    topic VARCHAR(255) NULL,
    final_report_json TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_speaking_sessions_client_id (client_id),
    INDEX ix_speaking_sessions_content_uuid (content_uuid)
);


-- 3. Create speaking_session_turns table
CREATE TABLE IF NOT EXISTS speaking_session_turns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    turn_index INT NOT NULL,
    ai_prompt_text TEXT NOT NULL,
    ai_audio_url VARCHAR(255) NULL,
    user_audio_url VARCHAR(255) NULL,
    user_transcript TEXT NULL,
    pronunciation_score INT NULL,
    grammar_score INT NULL,
    quick_feedback TEXT NULL,
    evaluation_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    evaluation_error TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_speaking_session_turn UNIQUE (session_id, turn_index),
    INDEX ix_speaking_turns_session_id (session_id)
);

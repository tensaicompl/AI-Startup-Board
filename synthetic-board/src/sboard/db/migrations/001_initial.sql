-- 001_initial.sql
-- Append-only schema. No UPDATE or DELETE ever.

CREATE TABLE IF NOT EXISTS petitions (
    petition_id   TEXT PRIMARY KEY,
    submitted_at  TEXT NOT NULL,
    meeting_type  TEXT NOT NULL,
    data          TEXT NOT NULL,   -- full Petition JSON
    inserted_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS transcripts (
    transcript_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    petition_id    TEXT NOT NULL,
    meeting_seed   INTEGER NOT NULL,
    data           TEXT NOT NULL,  -- full transcript JSON (list of TranscriptEntry dicts)
    inserted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (petition_id) REFERENCES petitions(petition_id)
);

CREATE TABLE IF NOT EXISTS memos (
    memo_id       TEXT PRIMARY KEY,
    petition_id   TEXT NOT NULL,
    source        TEXT NOT NULL,   -- 'board' or 'baseline'
    data          TEXT NOT NULL,   -- full Memo JSON
    inserted_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (petition_id) REFERENCES petitions(petition_id)
);

CREATE INDEX IF NOT EXISTS idx_transcripts_petition_id ON transcripts(petition_id);
CREATE INDEX IF NOT EXISTS idx_memos_petition_id ON memos(petition_id);

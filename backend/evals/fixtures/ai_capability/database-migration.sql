-- Migration: add conversation ownership and audit status
ALTER TABLE conversations
  ADD COLUMN owner_username TEXT;

ALTER TABLE conversations
  ADD COLUMN archived BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX idx_conversations_owner_username
  ON conversations(owner_username);

CREATE TABLE audit_events (
  id TEXT PRIMARY KEY,
  actor_username TEXT,
  action TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Rollback note:
-- Drop idx_conversations_owner_username before removing owner_username.

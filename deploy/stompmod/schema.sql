-- The D1 database "stompmod-feedback" (binding DB in wrangler.jsonc). Apply it once:
--   npx wrangler d1 execute stompmod-feedback --remote --file deploy/stompmod/schema.sql -c deploy/stompmod/wrangler.jsonc

CREATE TABLE IF NOT EXISTS feedback (
  id         TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,          -- ISO 8601, UTC
  type       TEXT NOT NULL CHECK (type IN ('bug', 'idea', 'other')),
  message    TEXT NOT NULL,
  email      TEXT NOT NULL DEFAULT '',   -- only if the person gave one, to reply
  lang       TEXT NOT NULL DEFAULT '',
  version    TEXT NOT NULL DEFAULT '',   -- the page's release
  ua         TEXT NOT NULL DEFAULT '',
  details    TEXT NOT NULL DEFAULT ''    -- the technical details, if the person included them
);
CREATE INDEX IF NOT EXISTS feedback_created ON feedback (created_at);

-- The rate limit: a hash of the IP with a daily salt and the hour, never the IP; the Worker deletes a row when its hour has passed.
CREATE TABLE IF NOT EXISTS ratelimit (
  key   TEXT PRIMARY KEY,
  n     INTEGER NOT NULL,
  until INTEGER NOT NULL             -- ms since the epoch
);

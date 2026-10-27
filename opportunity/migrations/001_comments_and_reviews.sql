-- Comment threads and reviews on cards and research reports.
-- card_or_report is a card id ("OPP-10") or "research/<slug>".

CREATE TABLE comments (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    card_or_report TEXT NOT NULL,
    anchor         TEXT NOT NULL DEFAULT '',   -- "" (all of it), "f:<field>" or "s:<heading id>"
    commit_sha     TEXT NOT NULL,              -- the commit the page showed
    author_email   TEXT NOT NULL,
    body           TEXT NOT NULL,
    parent_id      BIGINT REFERENCES comments (id),  -- the thread's first comment; NULL for that one
    resolved_by    TEXT,                       -- set on a thread's first comment
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX comments_by_subject ON comments (card_or_report, created_at);

CREATE TABLE reviews (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    card_or_report TEXT NOT NULL,
    verdict        TEXT NOT NULL CHECK (verdict IN ('reviewed', 'concerns', 'not-convinced')),
    note           TEXT NOT NULL DEFAULT '',
    commit_sha     TEXT NOT NULL,
    author_email   TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX reviews_by_subject ON reviews (card_or_report, created_at);

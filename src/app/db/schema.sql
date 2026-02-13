CREATE TABLE IF NOT EXISTS card_mappings (
    short_id SERIAL PRIMARY KEY,
    planka_card_id TEXT UNIQUE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_planka_card_id ON card_mappings(planka_card_id);

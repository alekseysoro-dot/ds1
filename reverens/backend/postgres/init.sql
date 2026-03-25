CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS products (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name        TEXT NOT NULL,
    wb_article  TEXT,
    wb_url      TEXT NOT NULL,
    group_name  TEXT,
    is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sellers (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    product_id  TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    seller_name TEXT NOT NULL,
    seller_id   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    seller_id   TEXT NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    price       INTEGER NOT NULL,
    recorded_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notification_settings (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    email       TEXT,
    tg_chat_id  TEXT,
    threshold   INTEGER NOT NULL DEFAULT 5
);

CREATE INDEX IF NOT EXISTS idx_price_history_seller_recorded
    ON price_history (seller_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_price_history_recorded
    ON price_history (recorded_at);

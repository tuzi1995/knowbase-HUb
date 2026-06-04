-- Create kb_scores table
CREATE TABLE IF NOT EXISTS kb_scores (
    id SERIAL PRIMARY KEY,
    kb_id TEXT NOT NULL UNIQUE,
    product_name TEXT,
    question_content TEXT,
    answer_content TEXT,
    status TEXT DEFAULT 'unscored', -- 'unscored', 'scored', 'outdated'
    total_score INTEGER,
    remarks TEXT,
    score_data JSONB, -- Storing detailed score breakdown
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add index on kb_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_kb_scores_kb_id ON kb_scores(kb_id);

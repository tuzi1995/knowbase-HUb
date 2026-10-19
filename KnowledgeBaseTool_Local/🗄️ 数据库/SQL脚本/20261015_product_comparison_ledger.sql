-- SQLite additive migration; KB V1 content is never modified here.

BEGIN;

CREATE TABLE IF NOT EXISTS comparison_image_batch (
	id VARCHAR(36) NOT NULL,
	name TEXT NOT NULL,
	note TEXT,
	actor TEXT NOT NULL,
	created_at TEXT NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS comparison_image_asset (
	id VARCHAR(36) NOT NULL,
	url TEXT NOT NULL,
	link_id TEXT,
	batch_id VARCHAR(36),
	category TEXT,
	models_json TEXT,
	confirmed_by TEXT,
	confirmed_at TEXT,
	historical BOOLEAN,
	created_at TEXT NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (url)
);

CREATE TABLE IF NOT EXISTS comparison_image_cell (
	id VARCHAR(64) NOT NULL,
	category TEXT NOT NULL,
	pair_json TEXT NOT NULL,
	active_asset_id VARCHAR(36),
	latest_decision_id VARCHAR(36),
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS comparison_image_decision (
	id VARCHAR(36) NOT NULL,
	cell_id VARCHAR(64) NOT NULL,
	asset_id VARCHAR(36),
	action VARCHAR(20) NOT NULL,
	targets_json TEXT,
	status VARCHAR(30) NOT NULL,
	actor TEXT NOT NULL,
	created_at TEXT NOT NULL,
	started BOOLEAN,
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_comparison_image_decision_cell_id ON comparison_image_decision (cell_id);

CREATE TABLE IF NOT EXISTS comparison_image_execution (
	id VARCHAR(64) NOT NULL,
	kb_id TEXT NOT NULL,
	payload_json TEXT NOT NULL,
	decision_ids_json TEXT NOT NULL,
	status VARCHAR(30) NOT NULL,
	result_json TEXT,
	actor TEXT NOT NULL,
	created_at TEXT NOT NULL,
	updated_at TEXT NOT NULL,
	PRIMARY KEY (id)
);

COMMIT;

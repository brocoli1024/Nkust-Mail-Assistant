-- Generated from frozen Alembic0011; additive only. Backup and verify target before Run.
SET search_path = public;
BEGIN;
DO $$ BEGIN IF (SELECT version_num FROM public.alembic_version) IS DISTINCT FROM '0010' THEN RAISE EXCEPTION 'PUSH_SCHEMA_PRECHECK_FAILED'; END IF; END $$;

-- Running upgrade 0010 -> 0011

CREATE TABLE push_devices (
    id VARCHAR(36) NOT NULL, 
    epoch VARCHAR(36) NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    endpoint_hash VARCHAR(64), 
    subscription_cipher TEXT, 
    subscription_version INTEGER NOT NULL, 
    enabled BOOLEAN NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_push_devices PRIMARY KEY (id), 
    CONSTRAINT uq_push_devices_token_hash UNIQUE (token_hash), 
    CONSTRAINT uq_push_devices_endpoint_hash UNIQUE (endpoint_hash)
);

CREATE TABLE push_reminders (
    id VARCHAR(36) NOT NULL, 
    device_id VARCHAR(36) NOT NULL, 
    todo_id VARCHAR(36) NOT NULL, 
    public_id INTEGER, 
    source_ref TEXT NOT NULL, 
    source_version VARCHAR(64) NOT NULL, 
    client_revision INTEGER NOT NULL, 
    server_revision INTEGER NOT NULL, 
    subscription_version INTEGER NOT NULL, 
    deadline JSON, 
    remind_at TIMESTAMP WITH TIME ZONE, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    status VARCHAR(32) NOT NULL, 
    attempts INTEGER NOT NULL, 
    next_attempt_at TIMESTAMP WITH TIME ZONE, 
    claim VARCHAR(36), 
    claim_expires_at TIMESTAMP WITH TIME ZONE, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_push_reminders PRIMARY KEY (id), 
    CONSTRAINT uq_push_reminders_device_id_todo_id UNIQUE (device_id, todo_id), 
    CONSTRAINT ck_push_reminders_client_revision CHECK (client_revision >= 1), 
    CONSTRAINT fk_push_reminders_device_id_push_devices FOREIGN KEY(device_id) REFERENCES push_devices (id) ON DELETE CASCADE, 
    CONSTRAINT fk_push_reminders_public_id_public_announcements FOREIGN KEY(public_id) REFERENCES public_announcements (id) ON DELETE CASCADE
);

CREATE INDEX ix_push_reminders_remind_at ON push_reminders (remind_at);

CREATE INDEX ix_push_reminders_device_id ON push_reminders (device_id);

CREATE TABLE push_operations (
    device_id VARCHAR(36) NOT NULL, 
    operation_id VARCHAR(36) NOT NULL, 
    request_hash VARCHAR(64) NOT NULL, 
    result JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_push_operations PRIMARY KEY (device_id, operation_id), 
    CONSTRAINT fk_push_operations_device_id_push_devices FOREIGN KEY(device_id) REFERENCES push_devices (id) ON DELETE CASCADE
);

CREATE TABLE push_leases (
    name VARCHAR(64) NOT NULL, 
    owner VARCHAR(36), 
    expires_at TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_push_leases PRIMARY KEY (name)
);

CREATE TABLE push_rate_buckets (
    key VARCHAR(128) NOT NULL, 
    count INTEGER NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_push_rate_buckets PRIMARY KEY (key)
);

INSERT INTO push_leases (name) VALUES ('mutations');

INSERT INTO push_leases (name) VALUES ('dispatcher');

REVOKE ALL ON TABLE push_devices FROM PUBLIC;

REVOKE ALL ON TABLE push_reminders FROM PUBLIC;

REVOKE ALL ON TABLE push_operations FROM PUBLIC;

REVOKE ALL ON TABLE push_leases FROM PUBLIC;

REVOKE ALL ON TABLE push_rate_buckets FROM PUBLIC;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='nkust_public_sync') THEN REVOKE ALL ON TABLE push_devices FROM nkust_public_sync; END IF; END $$;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='nkust_public_sync') THEN REVOKE ALL ON TABLE push_reminders FROM nkust_public_sync; END IF; END $$;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='nkust_public_sync') THEN REVOKE ALL ON TABLE push_operations FROM nkust_public_sync; END IF; END $$;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='nkust_public_sync') THEN REVOKE ALL ON TABLE push_leases FROM nkust_public_sync; END IF; END $$;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='nkust_public_sync') THEN REVOKE ALL ON TABLE push_rate_buckets FROM nkust_public_sync; END IF; END $$;

UPDATE alembic_version SET version_num='0011' WHERE alembic_version.version_num = '0010';

COMMIT;


-- Run as the table owner after creating the dedicated LOGIN role in Neon.
-- No passwords belong in this file. Only recent public-feed sync is permitted.
GRANT CONNECT ON DATABASE neondb TO nkust_public_sync;
GRANT USAGE ON SCHEMA public TO nkust_public_sync;
GRANT SELECT ON public.alembic_version TO nkust_public_sync;
GRANT SELECT, INSERT, UPDATE ON public.public_announcements,
    public.public_source_states, public.public_sync_runs, public.public_source_versions TO nkust_public_sync;
GRANT USAGE, SELECT ON SEQUENCE public.public_announcements_id_seq,
    public.public_sync_runs_id_seq, public.public_source_versions_id_seq TO nkust_public_sync;

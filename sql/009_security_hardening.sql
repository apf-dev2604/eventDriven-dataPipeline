-- Nexus V2 - Database security hardening baseline
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_owner') THEN CREATE ROLE nexus_owner NOLOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_dumper') THEN CREATE ROLE nexus_dumper LOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_worker') THEN CREATE ROLE nexus_worker LOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_readonly') THEN CREATE ROLE nexus_readonly LOGIN; END IF;
END $$;

REVOKE ALL ON SCHEMA etl FROM PUBLIC;
REVOKE ALL ON SCHEMA raw FROM PUBLIC;
REVOKE ALL ON SCHEMA staging FROM PUBLIC;
REVOKE ALL ON SCHEMA rejected FROM PUBLIC;
REVOKE ALL ON SCHEMA final_history FROM PUBLIC;

GRANT USAGE ON SCHEMA etl TO nexus_dumper;
GRANT SELECT ON etl.api_pull_config, etl.api_watermark, etl.reconciliation_scope TO nexus_dumper;
GRANT INSERT, UPDATE, SELECT ON etl.batch_run, etl.api_pull_run, etl.api_watermark, etl.api_backfill_request, etl.worker_log TO nexus_dumper;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA etl TO nexus_dumper;

GRANT USAGE ON SCHEMA etl, raw, staging, rejected, final_history TO nexus_worker;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA etl TO nexus_worker;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA raw TO nexus_worker;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA staging TO nexus_worker;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA rejected TO nexus_worker;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA final_history TO nexus_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA etl, raw, staging, rejected, final_history TO nexus_worker;
GRANT USAGE ON SCHEMA final_consolidated TO nexus_worker;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA final_consolidated TO nexus_worker;

GRANT USAGE ON SCHEMA final_consolidated, final_history TO nexus_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA final_consolidated TO nexus_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA final_history TO nexus_readonly;

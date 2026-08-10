DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stockoutops_app') THEN
        CREATE ROLE stockoutops_app LOGIN NOINHERIT;
    END IF;
END;
$$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO stockoutops_app;
GRANT SELECT, INSERT, UPDATE ON investigation_run TO stockoutops_app;
GRANT SELECT, INSERT ON workflow_event TO stockoutops_app;
GRANT SELECT, INSERT ON idempotency_key TO stockoutops_app;
GRANT SELECT, INSERT, UPDATE ON tool_invocation TO stockoutops_app;
GRANT SELECT, INSERT ON review_decision TO stockoutops_app;
GRANT SELECT ON inventory_fixture, demand_fixture, supplier_fixture TO stockoutops_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO stockoutops_app;

REVOKE UPDATE, DELETE ON workflow_event FROM stockoutops_app;
REVOKE INSERT, UPDATE, DELETE ON
    inventory_fixture, demand_fixture, supplier_fixture
FROM stockoutops_app;

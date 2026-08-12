ALTER TABLE investigation_run
    ADD COLUMN IF NOT EXISTS run_mode text NOT NULL DEFAULT 'human_review'
    CHECK (run_mode IN ('human_review', 'shadow'));

CREATE TABLE IF NOT EXISTS shadow_run (
    shadow_run_id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    case_id text NOT NULL CHECK (length(case_id) > 0),
    case_version text NOT NULL CHECK (length(case_version) > 0),
    case_pack_version text NOT NULL CHECK (length(case_pack_version) > 0),
    processor_version text NOT NULL CHECK (length(processor_version) > 0),
    prompt_version text NOT NULL CHECK (length(prompt_version) > 0),
    tool_schema_version text NOT NULL CHECK (tool_schema_version = 'v1'),
    execute boolean NOT NULL DEFAULT false CHECK (execute = false),
    status text NOT NULL CHECK (status IN ('started', 'completed', 'escalated')),
    investigation_run_id uuid REFERENCES investigation_run(run_id),
    provider_label text,
    output_json jsonb,
    diff_json jsonb,
    output_hash text CHECK (output_hash IS NULL OR output_hash ~ '^[0-9a-f]{64}$'),
    diff_hash text CHECK (diff_hash IS NULL OR diff_hash ~ '^[0-9a-f]{64}$'),
    latency_ms numeric CHECK (latency_ms IS NULL OR latency_ms >= 0),
    estimated_cost_usd numeric CHECK (estimated_cost_usd IS NULL OR estimated_cost_usd >= 0),
    cost_evidence_label text CHECK (
        cost_evidence_label IS NULL OR cost_evidence_label IN ('SIMULATED', 'UNMEASURED')
    ),
    external_action_count integer NOT NULL DEFAULT 0 CHECK (external_action_count = 0),
    created_by text NOT NULL,
    created_at timestamptz NOT NULL,
    completed_at timestamptz,
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, case_id, case_version, processor_version),
    UNIQUE (shadow_run_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS shadow_run_tenant_idx
    ON shadow_run (tenant_id, shadow_run_id);

CREATE TABLE IF NOT EXISTS shadow_diff (
    shadow_diff_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shadow_run_id uuid NOT NULL,
    tenant_id text NOT NULL,
    field_name text NOT NULL CHECK (length(field_name) > 0),
    agreement text NOT NULL CHECK (agreement IN ('exact', 'partial', 'disagree')),
    expected_json jsonb NOT NULL,
    actual_json jsonb NOT NULL,
    category text NOT NULL CHECK (length(category) > 0),
    created_at timestamptz NOT NULL,
    UNIQUE (shadow_run_id, field_name),
    FOREIGN KEY (shadow_run_id, tenant_id)
        REFERENCES shadow_run(shadow_run_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS shadow_diff_tenant_idx
    ON shadow_diff (tenant_id, shadow_run_id, shadow_diff_id);

CREATE TABLE IF NOT EXISTS shadow_control_event (
    shadow_event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shadow_run_id uuid NOT NULL,
    tenant_id text NOT NULL,
    event_type text NOT NULL,
    actor_id text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL,
    FOREIGN KEY (shadow_run_id, tenant_id)
        REFERENCES shadow_run(shadow_run_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS shadow_control_event_tenant_idx
    ON shadow_control_event (tenant_id, shadow_run_id, shadow_event_id);

CREATE OR REPLACE FUNCTION enforce_shadow_run_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'shadow_run is mutation-controlled; DELETE is forbidden'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'started' OR NEW.status NOT IN ('completed', 'escalated') THEN
        RAISE EXCEPTION 'shadow_run may transition only once from started to a terminal status'
            USING ERRCODE = '55000';
    END IF;
    IF (NEW.shadow_run_id, NEW.tenant_id, NEW.idempotency_key, NEW.payload_hash,
        NEW.case_id, NEW.case_version, NEW.case_pack_version, NEW.processor_version,
        NEW.prompt_version, NEW.tool_schema_version, NEW."execute", NEW.external_action_count,
        NEW.created_by, NEW.created_at)
       IS DISTINCT FROM
       (OLD.shadow_run_id, OLD.tenant_id, OLD.idempotency_key, OLD.payload_hash,
        OLD.case_id, OLD.case_version, OLD.case_pack_version, OLD.processor_version,
        OLD.prompt_version, OLD.tool_schema_version, OLD."execute", OLD.external_action_count,
        OLD.created_by, OLD.created_at) THEN
        RAISE EXCEPTION 'shadow_run immutable control fields cannot change'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.completed_at IS NULL THEN
        RAISE EXCEPTION 'terminal shadow_run requires completed_at'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.investigation_run_id IS NULL OR NEW.provider_label IS NULL
       OR NEW.output_json IS NULL OR NEW.diff_json IS NULL
       OR NEW.output_hash IS NULL OR NEW.diff_hash IS NULL
       OR NEW.latency_ms IS NULL OR NEW.cost_evidence_label IS NULL THEN
        RAISE EXCEPTION 'terminal shadow_run requires a complete result contract'
            USING ERRCODE = '55000';
    END IF;
    PERFORM 1 FROM investigation_run
    WHERE run_id = NEW.investigation_run_id AND tenant_id = NEW.tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'shadow_run investigation tenant binding is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION reject_shadow_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only; % is forbidden', TG_TABLE_NAME, TG_OP
        USING ERRCODE = '55000';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'shadow_run_mutation_control'
          AND tgrelid = 'shadow_run'::regclass
    ) THEN
        CREATE TRIGGER shadow_run_mutation_control
        BEFORE UPDATE OR DELETE ON shadow_run
        FOR EACH ROW EXECUTE FUNCTION enforce_shadow_run_mutation();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'shadow_diff_no_mutation'
          AND tgrelid = 'shadow_diff'::regclass
    ) THEN
        CREATE TRIGGER shadow_diff_no_mutation
        BEFORE UPDATE OR DELETE ON shadow_diff
        FOR EACH ROW EXECUTE FUNCTION reject_shadow_append_only_mutation();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'shadow_control_event_no_mutation'
          AND tgrelid = 'shadow_control_event'::regclass
    ) THEN
        CREATE TRIGGER shadow_control_event_no_mutation
        BEFORE UPDATE OR DELETE ON shadow_control_event
        FOR EACH ROW EXECUTE FUNCTION reject_shadow_append_only_mutation();
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON shadow_run TO stockoutops_app;
GRANT SELECT, INSERT ON shadow_diff, shadow_control_event TO stockoutops_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO stockoutops_app;

REVOKE DELETE ON shadow_run FROM stockoutops_app;
REVOKE UPDATE, DELETE ON shadow_diff, shadow_control_event FROM stockoutops_app;

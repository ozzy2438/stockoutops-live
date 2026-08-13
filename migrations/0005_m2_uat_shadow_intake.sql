ALTER TABLE shadow_run
    ADD COLUMN IF NOT EXISTS provenance_label text NOT NULL DEFAULT 'SIMULATED'
        CHECK (provenance_label IN ('SIMULATED', 'GENUINE_UAT_ANALYST_LABELLED'));

ALTER TABLE shadow_run
    ADD COLUMN IF NOT EXISTS baseline_source text NOT NULL DEFAULT 'controlled_synthetic_reference'
        CHECK (baseline_source IN ('controlled_synthetic_reference', 'analyst_reference'));

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'shadow_run_provenance_baseline_consistent'
    ) THEN
        ALTER TABLE shadow_run
            ADD CONSTRAINT shadow_run_provenance_baseline_consistent CHECK (
                (
                    provenance_label = 'SIMULATED'
                    AND baseline_source = 'controlled_synthetic_reference'
                )
                OR (
                    provenance_label = 'GENUINE_UAT_ANALYST_LABELLED'
                    AND baseline_source = 'analyst_reference'
                )
            );
    END IF;
END;
$$;

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
        NEW.prompt_version, NEW.tool_schema_version, NEW.provenance_label, NEW.baseline_source,
        NEW."execute", NEW.external_action_count, NEW.created_by, NEW.created_at)
       IS DISTINCT FROM
       (OLD.shadow_run_id, OLD.tenant_id, OLD.idempotency_key, OLD.payload_hash,
        OLD.case_id, OLD.case_version, OLD.case_pack_version, OLD.processor_version,
        OLD.prompt_version, OLD.tool_schema_version, OLD.provenance_label, OLD.baseline_source,
        OLD."execute", OLD.external_action_count, OLD.created_by, OLD.created_at) THEN
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

CREATE TABLE IF NOT EXISTS shadow_case_intake (
    intake_id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    case_id text NOT NULL CHECK (length(case_id) > 0),
    case_version text NOT NULL CHECK (length(case_version) > 0),
    case_contract_version text NOT NULL CHECK (case_contract_version = 'm2-shadow-case-contract-v2'),
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    provenance_label text NOT NULL CHECK (provenance_label = 'GENUINE_UAT_ANALYST_LABELLED'),
    baseline_source text NOT NULL CHECK (baseline_source = 'analyst_reference'),
    deidentification_status text NOT NULL CHECK (
        deidentification_status = 'deidentified_owner_attested'
    ),
    consent_data_use_status text NOT NULL CHECK (
        consent_data_use_status = 'owner_attested_consent_held_offline'
    ),
    consent_data_use_reference text NOT NULL CHECK (
        consent_data_use_reference ~ '^OFFLINE-CONSENT-[A-Z0-9-]{8,64}$'
    ),
    category text NOT NULL CHECK (length(category) > 0),
    execute boolean NOT NULL DEFAULT false CHECK (execute = false),
    external_action_count integer NOT NULL DEFAULT 0 CHECK (external_action_count = 0),
    case_json jsonb NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (tenant_id, case_id, case_version),
    UNIQUE (intake_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS shadow_case_intake_tenant_idx
    ON shadow_case_intake (tenant_id, case_id, case_version);

CREATE TABLE IF NOT EXISTS shadow_case_intake_event (
    intake_event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    intake_id uuid NOT NULL,
    tenant_id text NOT NULL,
    event_type text NOT NULL,
    actor_id text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL,
    FOREIGN KEY (intake_id, tenant_id)
        REFERENCES shadow_case_intake(intake_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS shadow_case_intake_event_tenant_idx
    ON shadow_case_intake_event (tenant_id, intake_id, intake_event_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'shadow_case_intake_no_mutation'
          AND tgrelid = 'shadow_case_intake'::regclass
    ) THEN
        CREATE TRIGGER shadow_case_intake_no_mutation
        BEFORE UPDATE OR DELETE ON shadow_case_intake
        FOR EACH ROW EXECUTE FUNCTION reject_shadow_append_only_mutation();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'shadow_case_intake_event_no_mutation'
          AND tgrelid = 'shadow_case_intake_event'::regclass
    ) THEN
        CREATE TRIGGER shadow_case_intake_event_no_mutation
        BEFORE UPDATE OR DELETE ON shadow_case_intake_event
        FOR EACH ROW EXECUTE FUNCTION reject_shadow_append_only_mutation();
    END IF;
END;
$$;

GRANT SELECT, INSERT ON shadow_case_intake, shadow_case_intake_event TO stockoutops_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO stockoutops_app;
REVOKE UPDATE, DELETE ON shadow_case_intake, shadow_case_intake_event FROM stockoutops_app;

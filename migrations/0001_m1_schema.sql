CREATE TABLE IF NOT EXISTS investigation_run (
    run_id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    requested_by text NOT NULL,
    assigned_reviewer_id text NOT NULL,
    sku_id text NOT NULL CHECK (length(sku_id) > 0),
    store_id text NOT NULL CHECK (length(store_id) > 0),
    supplier_id text NOT NULL CHECK (length(supplier_id) > 0),
    as_of_ts timestamptz NOT NULL,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    state text NOT NULL CHECK (
        state IN (
            'created', 'validating', 'gathering_evidence', 'quality_checks',
            'reasoning', 'drafting_recommendation', 'awaiting_human',
            'approved', 'edited_and_approved', 'rejected', 'escalated',
            'closed', 'failed_authz'
        )
    ),
    state_version integer NOT NULL DEFAULT 0 CHECK (state_version >= 0),
    draft_json jsonb,
    draft_hash text CHECK (draft_hash IS NULL OR draft_hash ~ '^[0-9a-f]{64}$'),
    draft_created_at timestamptz,
    review_expires_at timestamptz,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS investigation_run_tenant_idx
    ON investigation_run (tenant_id, run_id);

CREATE TABLE IF NOT EXISTS workflow_event (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES investigation_run(run_id),
    tenant_id text NOT NULL,
    event_type text NOT NULL,
    from_state text,
    to_state text,
    actor_id text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS workflow_event_run_idx
    ON workflow_event (tenant_id, run_id, event_id);

CREATE OR REPLACE FUNCTION reject_workflow_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'workflow_event is append-only; % is forbidden', TG_OP
        USING ERRCODE = '55000';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'workflow_event_no_mutation'
          AND tgrelid = 'workflow_event'::regclass
    ) THEN
        CREATE TRIGGER workflow_event_no_mutation
        BEFORE UPDATE OR DELETE ON workflow_event
        FOR EACH ROW EXECUTE FUNCTION reject_workflow_event_mutation();
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS idempotency_key (
    tenant_id text NOT NULL,
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    run_id uuid NOT NULL REFERENCES investigation_run(run_id),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS tool_invocation (
    invocation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES investigation_run(run_id),
    tenant_id text NOT NULL,
    tool_name text NOT NULL CHECK (
        tool_name IN ('T1_inventory', 'T2_sales_demand', 'T3_supplier', 'reasoning')
    ),
    tool_schema_version text NOT NULL,
    request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN ('started', 'completed', 'failed')),
    result_json jsonb,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    completed_at timestamptz,
    UNIQUE (run_id, tool_name)
);

CREATE INDEX IF NOT EXISTS tool_invocation_tenant_idx
    ON tool_invocation (tenant_id, run_id);

CREATE TABLE IF NOT EXISTS review_decision (
    decision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES investigation_run(run_id),
    tenant_id text NOT NULL,
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    action text NOT NULL CHECK (action IN ('approve', 'edit_approve', 'reject', 'escalate')),
    reviewer_id text NOT NULL,
    original_draft jsonb NOT NULL,
    original_draft_hash text NOT NULL CHECK (original_draft_hash ~ '^[0-9a-f]{64}$'),
    edited_payload jsonb,
    edited_payload_hash text CHECK (
        edited_payload_hash IS NULL OR edited_payload_hash ~ '^[0-9a-f]{64}$'
    ),
    reason text,
    decided_at timestamptz NOT NULL,
    UNIQUE (run_id, idempotency_key),
    UNIQUE (run_id)
);

CREATE TABLE IF NOT EXISTS inventory_fixture (
    tenant_id text NOT NULL,
    sku_id text NOT NULL,
    store_id text NOT NULL,
    on_hand numeric NOT NULL CHECK (on_hand >= 0),
    reserved numeric NOT NULL CHECK (reserved >= 0),
    on_order numeric NOT NULL CHECK (on_order >= 0),
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, sku_id, store_id)
);

CREATE TABLE IF NOT EXISTS demand_fixture (
    tenant_id text NOT NULL,
    sku_id text NOT NULL,
    store_id text NOT NULL,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    units_sold numeric NOT NULL CHECK (units_sold >= 0),
    average_daily_units numeric NOT NULL CHECK (average_daily_units >= 0),
    demand_signal text NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, sku_id, store_id, window_start, window_end)
);

CREATE TABLE IF NOT EXISTS supplier_fixture (
    tenant_id text NOT NULL,
    sku_id text NOT NULL,
    supplier_id text NOT NULL,
    open_order_quantity numeric NOT NULL CHECK (open_order_quantity >= 0),
    expected_receipt_at timestamptz NOT NULL,
    historical_lead_time_days numeric NOT NULL CHECK (historical_lead_time_days >= 0),
    status text NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, sku_id, supplier_id)
);

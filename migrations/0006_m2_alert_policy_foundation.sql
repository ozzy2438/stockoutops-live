CREATE TABLE IF NOT EXISTS alert_evaluation_event (
    alert_evaluation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alert_fingerprint text NOT NULL CHECK (alert_fingerprint ~ '^[0-9a-f]{64}$'),
    tenant_id text NOT NULL CHECK (length(tenant_id) > 0),
    policy_id text NOT NULL CHECK (length(policy_id) > 0),
    policy_version text NOT NULL CHECK (length(policy_version) > 0),
    metric_name text NOT NULL CHECK (
        metric_name IN (
            'external_action_count',
            'escalation_disagreement_rate',
            'missing_required_evidence_count',
            'unsupported_claim_count',
            'shadow_processing_error_rate'
        )
    ),
    severity text NOT NULL CHECK (severity IN ('SEV1', 'SEV2', 'SEV3')),
    state text CHECK (state IS NULL OR state IN ('OK', 'FIRING', 'RESOLVED')),
    previous_state text CHECK (
        previous_state IS NULL OR previous_state IN ('OK', 'FIRING', 'RESOLVED')
    ),
    transition text NOT NULL CHECK (
        transition IN (
            'INITIAL_OK', 'FIRED', 'STILL_FIRING', 'RESOLVED', 'STILL_OK', 'UNMEASURED'
        )
    ),
    measurement_status text NOT NULL CHECK (
        measurement_status IN ('EVALUATED', 'UNMEASURED')
    ),
    threshold_classification text NOT NULL CHECK (
        threshold_classification IN ('TARGET', 'ENGINEERING TEST THRESHOLD')
    ),
    threshold_value numeric NOT NULL,
    comparator text NOT NULL CHECK (comparator = '>'),
    observed_value numeric,
    window_label text NOT NULL CHECK (length(window_label) > 0),
    window_id text NOT NULL CHECK (length(window_id) BETWEEN 1 AND 200),
    evidence_label text NOT NULL CHECK (evidence_label = 'SIMULATED'),
    source_report_sha256 text NOT NULL CHECK (source_report_sha256 ~ '^[0-9a-f]{64}$'),
    correlation_json jsonb NOT NULL,
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 500),
    live_slo_evidence_eligible boolean NOT NULL DEFAULT false
        CHECK (live_slo_evidence_eligible = false),
    execute boolean NOT NULL DEFAULT false CHECK (execute = false),
    external_alert_delivery_count integer NOT NULL DEFAULT 0
        CHECK (external_alert_delivery_count = 0),
    actor_id text NOT NULL CHECK (length(actor_id) > 0),
    evaluated_at timestamptz NOT NULL,
    CHECK (
        (
            measurement_status = 'EVALUATED'
            AND state IS NOT NULL
            AND observed_value IS NOT NULL
            AND transition <> 'UNMEASURED'
        )
        OR (
            measurement_status = 'UNMEASURED'
            AND state IS NULL
            AND observed_value IS NULL
            AND transition = 'UNMEASURED'
        )
    ),
    UNIQUE (tenant_id, alert_fingerprint, idempotency_key),
    UNIQUE (tenant_id, alert_fingerprint, payload_hash)
);

CREATE INDEX IF NOT EXISTS alert_evaluation_tenant_fingerprint_idx
    ON alert_evaluation_event (tenant_id, alert_fingerprint, alert_evaluation_id);

CREATE OR REPLACE FUNCTION reject_alert_evaluation_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'alert_evaluation_event is append-only; % is forbidden', TG_OP
        USING ERRCODE = '55000';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'alert_evaluation_event_no_mutation'
          AND tgrelid = 'alert_evaluation_event'::regclass
    ) THEN
        CREATE TRIGGER alert_evaluation_event_no_mutation
        BEFORE UPDATE OR DELETE ON alert_evaluation_event
        FOR EACH ROW EXECUTE FUNCTION reject_alert_evaluation_mutation();
    END IF;
END;
$$;

GRANT SELECT, INSERT ON alert_evaluation_event TO stockoutops_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO stockoutops_app;
REVOKE UPDATE, DELETE ON alert_evaluation_event FROM stockoutops_app;

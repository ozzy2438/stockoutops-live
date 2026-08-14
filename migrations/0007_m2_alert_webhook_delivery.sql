CREATE TABLE IF NOT EXISTS alert_delivery_attempt (
    delivery_attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id text NOT NULL CHECK (length(tenant_id) > 0),
    evaluation_id bigint NOT NULL REFERENCES alert_evaluation_event (alert_evaluation_id),
    alert_fingerprint text NOT NULL CHECK (alert_fingerprint ~ '^[0-9a-f]{64}$'),
    transition text NOT NULL CHECK (transition IN ('FIRED', 'RESOLVED')),
    destination_host text NOT NULL CHECK (
        length(destination_host) BETWEEN 1 AND 253
    ),
    status text NOT NULL CHECK (status IN ('CLAIMED', 'DELIVERED', 'FAILED')),
    attempt_count integer NOT NULL CHECK (attempt_count >= 0 AND attempt_count <= 2),
    http_status integer CHECK (
        http_status IS NULL OR (http_status >= 100 AND http_status <= 599)
    ),
    error_class text CHECK (
        error_class IS NULL OR length(error_class) BETWEEN 1 AND 100
    ),
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    claimed_at timestamptz NOT NULL,
    completed_at timestamptz,
    UNIQUE (tenant_id, evaluation_id)
);

CREATE INDEX IF NOT EXISTS alert_delivery_attempt_tenant_eval_idx
    ON alert_delivery_attempt (tenant_id, evaluation_id);

CREATE OR REPLACE FUNCTION reject_alert_delivery_attempt_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'alert_delivery_attempt deletes are forbidden'
        USING ERRCODE = '55000';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'alert_delivery_attempt_no_delete'
          AND tgrelid = 'alert_delivery_attempt'::regclass
    ) THEN
        CREATE TRIGGER alert_delivery_attempt_no_delete
        BEFORE DELETE ON alert_delivery_attempt
        FOR EACH ROW EXECUTE FUNCTION reject_alert_delivery_attempt_delete();
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON alert_delivery_attempt TO stockoutops_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO stockoutops_app;
REVOKE DELETE ON alert_delivery_attempt FROM stockoutops_app;

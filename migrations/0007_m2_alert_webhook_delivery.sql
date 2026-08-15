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
    UNIQUE (tenant_id, evaluation_id),
    CONSTRAINT alert_delivery_attempt_terminal_evidence_ck CHECK (
        status = 'CLAIMED'
        OR (
            attempt_count BETWEEN 1 AND 2
            AND completed_at IS NOT NULL
            AND (
                (
                    status = 'DELIVERED'
                    AND http_status IS NOT NULL
                    AND http_status BETWEEN 200 AND 299
                    AND error_class IS NULL
                )
                OR (
                    status = 'FAILED'
                    AND error_class IS NOT NULL
                    AND btrim(error_class) <> ''
                    AND (http_status IS NULL OR http_status NOT BETWEEN 200 AND 299)
                )
            )
        )
    )
);

CREATE INDEX IF NOT EXISTS alert_delivery_attempt_tenant_eval_idx
    ON alert_delivery_attempt (tenant_id, evaluation_id);

CREATE OR REPLACE FUNCTION guard_alert_delivery_attempt_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    evaluation_tenant_id text;
    evaluation_fingerprint text;
    evaluation_transition text;
BEGIN
    IF NEW.status IS DISTINCT FROM 'CLAIMED'
       OR NEW.attempt_count IS DISTINCT FROM 0
       OR NEW.http_status IS NOT NULL
       OR NEW.error_class IS NOT NULL
       OR NEW.completed_at IS NOT NULL THEN
        RAISE EXCEPTION
            'alert_delivery_attempt must begin as an uncompleted CLAIMED row'
            USING ERRCODE = '55000';
    END IF;

    -- alert_evaluation_event is append-only (0006 rejects UPDATE and DELETE), so the
    -- referenced identity cannot change after this check.
    SELECT tenant_id, alert_fingerprint, transition
    INTO evaluation_tenant_id, evaluation_fingerprint, evaluation_transition
    FROM alert_evaluation_event
    WHERE alert_evaluation_id = NEW.evaluation_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'alert_delivery_attempt must reference an existing alert_evaluation_event'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.tenant_id IS DISTINCT FROM evaluation_tenant_id
       OR NEW.alert_fingerprint IS DISTINCT FROM evaluation_fingerprint
       OR NEW.transition IS DISTINCT FROM evaluation_transition THEN
        RAISE EXCEPTION
            'alert_delivery_attempt identity must match the referenced alert_evaluation_event'
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION reject_alert_delivery_attempt_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'alert_delivery_attempt deletes are forbidden'
        USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION guard_alert_delivery_attempt_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('DELIVERED', 'FAILED') THEN
        RAISE EXCEPTION 'alert_delivery_attempt terminal row cannot be modified'
            USING ERRCODE = '55000';
    END IF;

    IF OLD.status IS DISTINCT FROM 'CLAIMED'
       OR NEW.status NOT IN ('DELIVERED', 'FAILED') THEN
        RAISE EXCEPTION
            'alert_delivery_attempt status may only change from CLAIMED to DELIVERED or FAILED'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.delivery_attempt_id IS DISTINCT FROM OLD.delivery_attempt_id
       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.evaluation_id IS DISTINCT FROM OLD.evaluation_id
       OR NEW.alert_fingerprint IS DISTINCT FROM OLD.alert_fingerprint
       OR NEW.transition IS DISTINCT FROM OLD.transition
       OR NEW.destination_host IS DISTINCT FROM OLD.destination_host
       OR NEW.payload_hash IS DISTINCT FROM OLD.payload_hash
       OR NEW.claimed_at IS DISTINCT FROM OLD.claimed_at THEN
        RAISE EXCEPTION 'alert_delivery_attempt identity fields are immutable'
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'alert_delivery_attempt_guard_insert'
          AND tgrelid = 'alert_delivery_attempt'::regclass
    ) THEN
        CREATE TRIGGER alert_delivery_attempt_guard_insert
        BEFORE INSERT ON alert_delivery_attempt
        FOR EACH ROW EXECUTE FUNCTION guard_alert_delivery_attempt_insert();
    END IF;
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

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'alert_delivery_attempt_guard_update'
          AND tgrelid = 'alert_delivery_attempt'::regclass
    ) THEN
        CREATE TRIGGER alert_delivery_attempt_guard_update
        BEFORE UPDATE ON alert_delivery_attempt
        FOR EACH ROW EXECUTE FUNCTION guard_alert_delivery_attempt_update();
    END IF;
END;
$$;

GRANT SELECT, INSERT ON alert_delivery_attempt TO stockoutops_app;
GRANT UPDATE (
    status, attempt_count, http_status, error_class, completed_at
) ON alert_delivery_attempt TO stockoutops_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO stockoutops_app;
REVOKE DELETE ON alert_delivery_attempt FROM stockoutops_app;
REVOKE UPDATE (
    tenant_id, evaluation_id, alert_fingerprint, transition, destination_host,
    payload_hash, claimed_at, delivery_attempt_id
) ON alert_delivery_attempt FROM stockoutops_app;

-- Durable alert delivery outbox and append-only per-attempt evidence.
--
-- Replaces the ADR-0008 claim-before-send path. Delivery intent is committed in
-- the same transaction as the alert evaluation append; a separate leased worker
-- performs HTTP outside any transaction.

CREATE TABLE IF NOT EXISTS alert_outbox (
    outbox_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id text NOT NULL CHECK (length(tenant_id) > 0),
    evaluation_id bigint NOT NULL REFERENCES alert_evaluation_event (alert_evaluation_id),
    alert_fingerprint text NOT NULL CHECK (alert_fingerprint ~ '^[0-9a-f]{64}$'),
    transition text NOT NULL CHECK (transition IN ('FIRED', 'RESOLVED')),
    destination_host text NOT NULL CHECK (length(destination_host) BETWEEN 1 AND 253),
    payload_json jsonb NOT NULL,
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 500),
    state text NOT NULL CHECK (state IN ('PENDING', 'IN_FLIGHT', 'DELIVERED', 'DEAD_LETTER')),
    attempt_count integer NOT NULL CHECK (attempt_count >= 0 AND attempt_count <= 100),
    max_attempts integer NOT NULL CHECK (max_attempts >= 1 AND max_attempts <= 100),
    redrive_count integer NOT NULL DEFAULT 0 CHECK (redrive_count >= 0 AND redrive_count <= 100),
    next_attempt_at timestamptz NOT NULL,
    lease_owner text CHECK (lease_owner IS NULL OR length(lease_owner) BETWEEN 1 AND 200),
    lease_expires_at timestamptz,
    last_error_class text CHECK (last_error_class IS NULL OR length(last_error_class) BETWEEN 1 AND 100),
    last_http_status integer CHECK (
        last_http_status IS NULL OR (last_http_status >= 100 AND last_http_status <= 599)
    ),
    enqueued_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    completed_at timestamptz,
    -- Deterministic dedup: one delivery intent per tenant lifecycle evaluation.
    UNIQUE (tenant_id, evaluation_id),
    UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT alert_outbox_lease_ck CHECK (
        (state = 'IN_FLIGHT' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR (state <> 'IN_FLIGHT' AND lease_owner IS NULL AND lease_expires_at IS NULL)
    ),
    CONSTRAINT alert_outbox_terminal_ck CHECK (
        (state IN ('DELIVERED', 'DEAD_LETTER') AND completed_at IS NOT NULL)
        OR (state IN ('PENDING', 'IN_FLIGHT') AND completed_at IS NULL)
    ),
    CONSTRAINT alert_outbox_delivered_evidence_ck CHECK (
        state <> 'DELIVERED'
        OR (
            attempt_count >= 1
            AND last_http_status IS NOT NULL
            AND last_http_status BETWEEN 200 AND 299
            AND last_error_class IS NULL
        )
    ),
    CONSTRAINT alert_outbox_dead_letter_evidence_ck CHECK (
        state <> 'DEAD_LETTER'
        OR (attempt_count >= 1 AND last_error_class IS NOT NULL AND btrim(last_error_class) <> '')
    )
);

-- Claim scan: eligible rows ordered by due time.
CREATE INDEX IF NOT EXISTS alert_outbox_claimable_idx
    ON alert_outbox (next_attempt_at, outbox_id)
    WHERE state IN ('PENDING', 'IN_FLIGHT');

CREATE INDEX IF NOT EXISTS alert_outbox_tenant_idx
    ON alert_outbox (tenant_id, evaluation_id);

-- Append-only per-attempt evidence. One row per HTTP attempt.
CREATE TABLE IF NOT EXISTS alert_delivery_attempt_event (
    attempt_event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    outbox_id bigint NOT NULL REFERENCES alert_outbox (outbox_id),
    tenant_id text NOT NULL CHECK (length(tenant_id) > 0),
    evaluation_id bigint NOT NULL REFERENCES alert_evaluation_event (alert_evaluation_id),
    attempt_number integer NOT NULL CHECK (attempt_number >= 1 AND attempt_number <= 100),
    outcome text NOT NULL CHECK (
        outcome IN ('DELIVERED', 'RETRYABLE_FAILURE', 'PERMANENT_FAILURE', 'AMBIGUOUS')
    ),
    http_status integer CHECK (
        http_status IS NULL OR (http_status >= 100 AND http_status <= 599)
    ),
    error_class text CHECK (error_class IS NULL OR length(error_class) BETWEEN 1 AND 100),
    lease_owner text NOT NULL CHECK (length(lease_owner) BETWEEN 1 AND 200),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 500),
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    UNIQUE (outbox_id, attempt_number),
    CONSTRAINT alert_delivery_attempt_event_outcome_ck CHECK (
        (
            outcome = 'DELIVERED'
            AND http_status IS NOT NULL
            AND http_status BETWEEN 200 AND 299
            AND error_class IS NULL
        )
        OR (
            outcome = 'AMBIGUOUS'
            AND http_status IS NULL
            AND error_class IS NOT NULL
        )
        OR (
            outcome IN ('RETRYABLE_FAILURE', 'PERMANENT_FAILURE')
            AND error_class IS NOT NULL
            AND (http_status IS NULL OR http_status NOT BETWEEN 200 AND 299)
        )
    )
);

CREATE INDEX IF NOT EXISTS alert_delivery_attempt_event_outbox_idx
    ON alert_delivery_attempt_event (outbox_id, attempt_number);

-- The merged 0007 terminal ledger capped attempts at the synchronous adapter's
-- two tries. A bounded outbox retries more, so widen the bound and keep every
-- other 0007 guard untouched.
ALTER TABLE alert_delivery_attempt
    DROP CONSTRAINT IF EXISTS alert_delivery_attempt_attempt_count_check;

ALTER TABLE alert_delivery_attempt
    ADD CONSTRAINT alert_delivery_attempt_attempt_count_check
    CHECK (attempt_count >= 0 AND attempt_count <= 100);

-- Same widening for the terminal-evidence guard. Every other clause is the
-- 0007 text verbatim so the merged integrity rules keep holding.
ALTER TABLE alert_delivery_attempt
    DROP CONSTRAINT IF EXISTS alert_delivery_attempt_terminal_evidence_ck;

ALTER TABLE alert_delivery_attempt
    ADD CONSTRAINT alert_delivery_attempt_terminal_evidence_ck CHECK (
        status = 'CLAIMED'
        OR (
            attempt_count BETWEEN 1 AND 100
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
    );

CREATE OR REPLACE FUNCTION reject_alert_outbox_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'alert_outbox deletes are forbidden'
        USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION guard_alert_outbox_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    evaluation_tenant_id text;
    evaluation_fingerprint text;
    evaluation_transition text;
BEGIN
    IF NEW.state IS DISTINCT FROM 'PENDING'
       OR NEW.attempt_count IS DISTINCT FROM 0
       OR NEW.redrive_count IS DISTINCT FROM 0
       OR NEW.lease_owner IS NOT NULL
       OR NEW.lease_expires_at IS NOT NULL
       OR NEW.last_error_class IS NOT NULL
       OR NEW.last_http_status IS NOT NULL
       OR NEW.completed_at IS NOT NULL THEN
        RAISE EXCEPTION 'alert_outbox must begin as an unattempted PENDING row'
            USING ERRCODE = '55000';
    END IF;

    -- alert_evaluation_event is append-only (0006 rejects UPDATE and DELETE), so the
    -- referenced identity cannot change after this check.
    SELECT tenant_id, alert_fingerprint, transition
    INTO evaluation_tenant_id, evaluation_fingerprint, evaluation_transition
    FROM alert_evaluation_event
    WHERE alert_evaluation_id = NEW.evaluation_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'alert_outbox must reference an existing alert_evaluation_event'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.tenant_id IS DISTINCT FROM evaluation_tenant_id
       OR NEW.alert_fingerprint IS DISTINCT FROM evaluation_fingerprint
       OR NEW.transition IS DISTINCT FROM evaluation_transition THEN
        RAISE EXCEPTION 'alert_outbox identity must match its alert_evaluation_event'
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION guard_alert_outbox_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    attempt_outcome text;
    attempt_http_status integer;
    attempt_error_class text;
    attempt_lease_owner text;
    attempt_completed_at timestamptz;
    ledger_status text;
    ledger_attempt_count integer;
    ledger_http_status integer;
    ledger_error_class text;
    ledger_completed_at timestamptz;
    ledger_alert_fingerprint text;
    ledger_transition text;
    ledger_destination_host text;
    ledger_payload_hash text;
BEGIN
    IF NEW.outbox_id IS DISTINCT FROM OLD.outbox_id
       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.evaluation_id IS DISTINCT FROM OLD.evaluation_id
       OR NEW.alert_fingerprint IS DISTINCT FROM OLD.alert_fingerprint
       OR NEW.transition IS DISTINCT FROM OLD.transition
       OR NEW.destination_host IS DISTINCT FROM OLD.destination_host
       OR NEW.payload_json IS DISTINCT FROM OLD.payload_json
       OR NEW.payload_hash IS DISTINCT FROM OLD.payload_hash
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.enqueued_at IS DISTINCT FROM OLD.enqueued_at THEN
        RAISE EXCEPTION 'alert_outbox identity and payload fields are immutable'
            USING ERRCODE = '55000';
    END IF;

    IF OLD.state = 'DELIVERED' THEN
        RAISE EXCEPTION 'alert_outbox DELIVERED is final'
            USING ERRCODE = '55000';
    END IF;

    -- Permitted transitions:
    --   PENDING     -> IN_FLIGHT                     (lease)
    --   IN_FLIGHT   -> DELIVERED                     (success)
    --   IN_FLIGHT   -> PENDING                       (bounded retry)
    --   IN_FLIGHT   -> DEAD_LETTER                   (retry exhausted / permanent)
    --   IN_FLIGHT   -> IN_FLIGHT                     (stale-lease takeover)
    --   DEAD_LETTER -> PENDING                       (explicit re-drive)
    IF NOT (
        (OLD.state = 'PENDING' AND NEW.state = 'IN_FLIGHT')
        OR (OLD.state = 'IN_FLIGHT' AND NEW.state IN ('DELIVERED', 'PENDING', 'DEAD_LETTER', 'IN_FLIGHT'))
        OR (OLD.state = 'DEAD_LETTER' AND NEW.state = 'PENDING')
    ) THEN
        RAISE EXCEPTION 'alert_outbox transition % -> % is forbidden', OLD.state, NEW.state
            USING ERRCODE = '55000';
    END IF;

    IF NEW.attempt_count < OLD.attempt_count THEN
        RAISE EXCEPTION 'alert_outbox attempt_count must not decrease'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.redrive_count < OLD.redrive_count THEN
        RAISE EXCEPTION 'alert_outbox redrive_count must not decrease'
            USING ERRCODE = '55000';
    END IF;

    IF OLD.state = 'PENDING' AND NEW.state = 'IN_FLIGHT' THEN
        IF NEW.attempt_count <> OLD.attempt_count + 1
           OR OLD.next_attempt_at > NEW.updated_at
           OR NEW.lease_expires_at <= NEW.updated_at THEN
            RAISE EXCEPTION 'alert_outbox lease must claim one due active attempt'
                USING ERRCODE = '55000';
        END IF;
    END IF;

    IF OLD.state = 'IN_FLIGHT' AND NEW.state = 'IN_FLIGHT' THEN
        IF NEW.attempt_count <> OLD.attempt_count + 1
           OR OLD.lease_expires_at > NEW.updated_at
           OR NEW.lease_expires_at <= NEW.updated_at THEN
            RAISE EXCEPTION 'alert_outbox takeover requires an expired lease and next attempt'
                USING ERRCODE = '55000';
        END IF;
    END IF;

    IF OLD.state = 'IN_FLIGHT'
       AND NEW.state IN ('DELIVERED', 'PENDING', 'DEAD_LETTER') THEN
        IF NEW.attempt_count <> OLD.attempt_count THEN
            RAISE EXCEPTION 'alert_outbox outcome must preserve the active attempt number'
                USING ERRCODE = '55000';
        END IF;

        SELECT outcome, http_status, error_class, lease_owner, completed_at
        INTO attempt_outcome, attempt_http_status, attempt_error_class,
             attempt_lease_owner, attempt_completed_at
        FROM alert_delivery_attempt_event
        WHERE outbox_id = OLD.outbox_id
          AND attempt_number = OLD.attempt_count;

        IF NOT FOUND
           OR attempt_lease_owner IS DISTINCT FROM OLD.lease_owner
           OR attempt_http_status IS DISTINCT FROM NEW.last_http_status
           OR attempt_error_class IS DISTINCT FROM NEW.last_error_class
           OR attempt_completed_at IS DISTINCT FROM NEW.updated_at THEN
            RAISE EXCEPTION
                'alert_outbox outcome requires matching active-lease attempt evidence'
                USING ERRCODE = '55000';
        END IF;

        IF NEW.state = 'DELIVERED' AND attempt_outcome IS DISTINCT FROM 'DELIVERED' THEN
            RAISE EXCEPTION 'alert_outbox DELIVERED requires successful attempt evidence'
                USING ERRCODE = '55000';
        ELSIF NEW.state = 'PENDING'
              AND attempt_outcome NOT IN ('RETRYABLE_FAILURE', 'AMBIGUOUS') THEN
            RAISE EXCEPTION 'alert_outbox retry requires retryable or ambiguous evidence'
                USING ERRCODE = '55000';
        ELSIF NEW.state = 'PENDING' AND NEW.attempt_count >= NEW.max_attempts THEN
            RAISE EXCEPTION 'alert_outbox retry cannot exceed its attempt budget'
                USING ERRCODE = '55000';
        ELSIF NEW.state = 'DEAD_LETTER'
              AND attempt_outcome NOT IN (
                  'RETRYABLE_FAILURE', 'PERMANENT_FAILURE', 'AMBIGUOUS'
              ) THEN
            RAISE EXCEPTION 'alert_outbox DEAD_LETTER requires failure or ambiguous evidence'
                USING ERRCODE = '55000';
        ELSIF NEW.state = 'DEAD_LETTER'
              AND attempt_outcome IN ('RETRYABLE_FAILURE', 'AMBIGUOUS')
              AND NEW.attempt_count < NEW.max_attempts THEN
            RAISE EXCEPTION
                'alert_outbox retryable or ambiguous evidence must exhaust the attempt budget'
                USING ERRCODE = '55000';
        END IF;

        IF NEW.state IN ('DELIVERED', 'DEAD_LETTER') THEN
            SELECT status, attempt_count, http_status, error_class, completed_at,
                   alert_fingerprint, transition, destination_host, payload_hash
            INTO ledger_status, ledger_attempt_count, ledger_http_status,
                 ledger_error_class, ledger_completed_at, ledger_alert_fingerprint,
                 ledger_transition, ledger_destination_host, ledger_payload_hash
            FROM alert_delivery_attempt
            WHERE tenant_id = OLD.tenant_id
              AND evaluation_id = OLD.evaluation_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'alert_outbox terminal outcome requires terminal delivery ledger evidence'
                    USING ERRCODE = '55000';
            END IF;

            -- The PR #25 ledger is one immutable row per evaluation. On the
            -- initial terminal outcome it must match exactly. After an explicit
            -- re-drive it remains the immutable FAILED record of the earlier
            -- dead letter; the current attempt event is the new outcome record.
            IF ledger_alert_fingerprint IS DISTINCT FROM OLD.alert_fingerprint
                OR ledger_transition IS DISTINCT FROM OLD.transition
                OR ledger_destination_host IS DISTINCT FROM OLD.destination_host
                OR ledger_payload_hash IS DISTINCT FROM OLD.payload_hash THEN
                RAISE EXCEPTION
                    'alert_outbox identity must match terminal delivery ledger evidence'
                    USING ERRCODE = '55000';
            END IF;

            IF OLD.redrive_count = 0 AND (
                ledger_status IS DISTINCT FROM
                    CASE WHEN NEW.state = 'DELIVERED' THEN 'DELIVERED' ELSE 'FAILED' END
                OR ledger_attempt_count IS DISTINCT FROM NEW.attempt_count
                OR ledger_http_status IS DISTINCT FROM NEW.last_http_status
                OR ledger_error_class IS DISTINCT FROM NEW.last_error_class
                OR ledger_completed_at IS DISTINCT FROM NEW.completed_at
            ) THEN
                RAISE EXCEPTION
                    'alert_outbox terminal outcome must match terminal delivery ledger evidence'
                    USING ERRCODE = '55000';
            ELSIF OLD.redrive_count > 0 AND ledger_status IS DISTINCT FROM 'FAILED' THEN
                RAISE EXCEPTION
                    'alert_outbox re-drive requires its immutable prior FAILED ledger evidence'
                    USING ERRCODE = '55000';
            END IF;
        END IF;
    END IF;

    -- Only an explicit re-drive may raise the attempt ceiling, and only while
    -- leaving DEAD_LETTER.
    IF NEW.max_attempts IS DISTINCT FROM OLD.max_attempts
       AND NOT (OLD.state = 'DEAD_LETTER' AND NEW.state = 'PENDING') THEN
        RAISE EXCEPTION 'alert_outbox max_attempts may only change on re-drive'
            USING ERRCODE = '55000';
    END IF;

    IF OLD.state = 'DEAD_LETTER' AND NEW.state = 'PENDING'
       AND NEW.redrive_count <> OLD.redrive_count + 1 THEN
        RAISE EXCEPTION 'alert_outbox re-drive must increment redrive_count exactly once'
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION reject_alert_delivery_attempt_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'alert_delivery_attempt_event is append-only; % is forbidden', TG_OP
        USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION guard_alert_delivery_attempt_event_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    outbox_tenant_id text;
    outbox_evaluation_id bigint;
    outbox_idempotency_key text;
    outbox_state text;
    outbox_attempt_count integer;
    outbox_lease_owner text;
BEGIN
    SELECT tenant_id, evaluation_id, idempotency_key, state, attempt_count, lease_owner
    INTO outbox_tenant_id, outbox_evaluation_id, outbox_idempotency_key,
         outbox_state, outbox_attempt_count, outbox_lease_owner
    FROM alert_outbox
    WHERE outbox_id = NEW.outbox_id
    FOR KEY SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'alert_delivery_attempt_event must reference an existing alert_outbox row'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.tenant_id IS DISTINCT FROM outbox_tenant_id
       OR NEW.evaluation_id IS DISTINCT FROM outbox_evaluation_id
       OR NEW.idempotency_key IS DISTINCT FROM outbox_idempotency_key THEN
        RAISE EXCEPTION 'alert_delivery_attempt_event identity must match its alert_outbox row'
            USING ERRCODE = '55000';
    END IF;

    IF outbox_state IS DISTINCT FROM 'IN_FLIGHT'
       OR NEW.attempt_number IS DISTINCT FROM outbox_attempt_count
       OR NEW.lease_owner IS DISTINCT FROM outbox_lease_owner THEN
        RAISE EXCEPTION
            'alert_delivery_attempt_event must match the active IN_FLIGHT attempt and lease'
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'alert_outbox_no_delete'
          AND tgrelid = 'alert_outbox'::regclass
    ) THEN
        CREATE TRIGGER alert_outbox_no_delete
        BEFORE DELETE ON alert_outbox
        FOR EACH ROW EXECUTE FUNCTION reject_alert_outbox_delete();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'alert_outbox_guard_insert'
          AND tgrelid = 'alert_outbox'::regclass
    ) THEN
        CREATE TRIGGER alert_outbox_guard_insert
        BEFORE INSERT ON alert_outbox
        FOR EACH ROW EXECUTE FUNCTION guard_alert_outbox_insert();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'alert_outbox_guard_update'
          AND tgrelid = 'alert_outbox'::regclass
    ) THEN
        CREATE TRIGGER alert_outbox_guard_update
        BEFORE UPDATE ON alert_outbox
        FOR EACH ROW EXECUTE FUNCTION guard_alert_outbox_update();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'alert_delivery_attempt_event_no_mutation'
          AND tgrelid = 'alert_delivery_attempt_event'::regclass
    ) THEN
        CREATE TRIGGER alert_delivery_attempt_event_no_mutation
        BEFORE UPDATE OR DELETE ON alert_delivery_attempt_event
        FOR EACH ROW EXECUTE FUNCTION reject_alert_delivery_attempt_event_mutation();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'alert_delivery_attempt_event_guard_insert'
          AND tgrelid = 'alert_delivery_attempt_event'::regclass
    ) THEN
        CREATE TRIGGER alert_delivery_attempt_event_guard_insert
        BEFORE INSERT ON alert_delivery_attempt_event
        FOR EACH ROW EXECUTE FUNCTION guard_alert_delivery_attempt_event_insert();
    END IF;
END;
$$;

GRANT SELECT, INSERT ON alert_outbox TO stockoutops_app;
GRANT UPDATE (
    state, attempt_count, max_attempts, redrive_count, next_attempt_at,
    lease_owner, lease_expires_at, last_error_class, last_http_status,
    updated_at, completed_at
) ON alert_outbox TO stockoutops_app;
GRANT SELECT, INSERT ON alert_delivery_attempt_event TO stockoutops_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO stockoutops_app;

REVOKE DELETE ON alert_outbox FROM stockoutops_app;
REVOKE UPDATE (
    outbox_id, tenant_id, evaluation_id, alert_fingerprint, transition,
    destination_host, payload_json, payload_hash, idempotency_key, enqueued_at
) ON alert_outbox FROM stockoutops_app;
REVOKE UPDATE, DELETE ON alert_delivery_attempt_event FROM stockoutops_app;

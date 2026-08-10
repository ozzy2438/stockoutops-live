from stockoutops.state_machine import RunState, can_transition


def test_allowed_m1_path_and_failure_edges() -> None:
    assert can_transition(RunState.CREATED, RunState.VALIDATING)
    assert can_transition(RunState.QUALITY_CHECKS, RunState.REASONING)
    assert can_transition(RunState.AWAITING_HUMAN, RunState.APPROVED)
    assert can_transition(RunState.APPROVED, RunState.CLOSED)
    assert can_transition(RunState.GATHERING_EVIDENCE, RunState.ESCALATED)


def test_forbidden_states_and_transitions_are_absent() -> None:
    assert not can_transition(RunState.CREATED, RunState.REASONING)
    assert not can_transition(RunState.CLOSED, RunState.CREATED)
    assert "executing_write" not in {state.value for state in RunState}
    assert "recording_outcome" not in {state.value for state in RunState}

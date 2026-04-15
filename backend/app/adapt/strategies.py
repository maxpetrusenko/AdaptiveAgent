"""Update strategies for the adaptation loop."""

# Minimum absolute improvement required to accept
MIN_IMPROVEMENT_THRESHOLD = 0.05  # 5%


def should_accept(
    before_pass_rate: float,
    after_pass_rate: float,
    before_halluc_count: int = 0,
    after_halluc_count: int = 0,
    before_protected_pass: int = 0,
    after_protected_pass: int = 0,
    protected_total: int = 0,
) -> tuple[bool, str]:
    """Determine if an adaptation should be accepted.

    Returns (accepted, reason) tuple.
    """
    improvement = after_pass_rate - before_pass_rate

    # Gate 1: Minimum improvement threshold
    if improvement < MIN_IMPROVEMENT_THRESHOLD:
        return False, (
            f"Improvement {improvement:.1%} below threshold"
            f" {MIN_IMPROVEMENT_THRESHOLD:.0%}"
        )

    # Gate 2: Hallucination regression
    if after_halluc_count > before_halluc_count:
        return False, (
            f"Hallucination regression: {before_halluc_count} -> {after_halluc_count}"
        )

    # Gate 3: Protected cases must not regress
    if protected_total > 0 and after_protected_pass < before_protected_pass:
        return False, (
            f"Protected case regression: {before_protected_pass}/{protected_total} "
            f"-> {after_protected_pass}/{protected_total}"
        )

    return True, f"Pass rate improved by {improvement:.1%}"


def should_continue_adapting(pass_rate: float, max_pass_rate: float = 1.0) -> bool:
    """Determine if we should continue running adaptation loops."""
    return pass_rate < max_pass_rate

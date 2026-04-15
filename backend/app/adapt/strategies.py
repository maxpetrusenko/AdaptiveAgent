"""Update strategies for the adaptation loop."""


def should_accept(before_pass_rate: float, after_pass_rate: float) -> bool:
    """Determine if an adaptation should be accepted.

    Simple strategy: accept if pass rate improved.
    """
    return after_pass_rate > before_pass_rate


def should_continue_adapting(pass_rate: float, max_pass_rate: float = 1.0) -> bool:
    """Determine if we should continue running adaptation loops."""
    return pass_rate < max_pass_rate

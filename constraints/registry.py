from __future__ import annotations

from typing import Callable, List

from constraints.base import apply_base_constraints
from constraints.delay import apply_delay_constraints
from constraints.interruption import apply_interruption_constraints
from constraints.objective_modes import apply_objective_mode
from constraints.speed_limit import apply_speed_limit_constraints
from core.builder import BuildContext

ConstraintModule = Callable[[BuildContext], None]


def get_constraint_modules() -> List[ConstraintModule]:
    return [
        apply_base_constraints,
        apply_delay_constraints,
        apply_speed_limit_constraints,
        apply_interruption_constraints,
        apply_objective_mode,
    ]

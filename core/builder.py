from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from core.types import AppConfig, EventKey, LinearConstraint, LinearModel, OrderKey, TranslatedData


class MutableLinearModel:
    def __init__(self, name: str) -> None:
        self.name = name
        self.variables: Dict[str, Tuple[float, Optional[float], str]] = {}
        self.objective: Dict[str, float] = {}
        self.objective_sense = "min"
        self.constraints: list[LinearConstraint] = []
        self._constraint_counter = 0

    def add_variable(self, name: str, lb: float = 0.0, ub: Optional[float] = None, vtype: str = "C") -> None:
        if name in self.variables:
            return
        self.variables[name] = (lb, ub, vtype)

    def add_objective_term(self, var_name: str, coefficient: float) -> None:
        self.objective[var_name] = self.objective.get(var_name, 0.0) + coefficient

    def add_constraint(self, name: str, coefficients: Dict[str, float], sense: str, rhs: float) -> None:
        self._constraint_counter += 1
        safe_name = f"{name}_{self._constraint_counter}"
        self.constraints.append(
            LinearConstraint(
                name=safe_name,
                coefficients=coefficients,
                sense=sense,
                rhs=rhs,
            )
        )

    def freeze(self) -> LinearModel:
        return LinearModel(
            name=self.name,
            variables=dict(self.variables),
            objective=dict(self.objective),
            objective_sense=self.objective_sense,
            constraints=list(self.constraints),
        )


@dataclass(frozen=True)
class BuildContext:
    model: MutableLinearModel
    translated: TranslatedData
    config: AppConfig
    event_id: Dict[EventKey, str]
    time_var: Dict[EventKey, str]
    delay_var: Dict[EventKey, str]
    arr_order_var: Dict[OrderKey, str]
    dep_order_var: Dict[OrderKey, str]


def build_model(translated: TranslatedData, config: AppConfig) -> LinearModel:
    model = MutableLinearModel(name="timetable_translation_model")

    event_id: Dict[EventKey, str] = {}
    time_var: Dict[EventKey, str] = {}
    delay_var: Dict[EventKey, str] = {}
    arr_order_var: Dict[OrderKey, str] = {}
    dep_order_var: Dict[OrderKey, str] = {}

    for index, event_key in enumerate(translated.event_keys, start=1):
        event_token = f"e{index}"
        event_id[event_key] = event_token

        t_name = f"t_{event_token}"
        d_name = f"d_{event_token}"

        time_var[event_key] = t_name
        delay_var[event_key] = d_name

        model.add_variable(t_name, lb=0.0, ub=float(86400 * 2), vtype="I")
        model.add_variable(d_name, lb=0.0, ub=float(86400 * 2), vtype="I")

    for index, key in enumerate(translated.arr_order_pair, start=1):
        var_name = f"oa_{index}"
        arr_order_var[key] = var_name
        model.add_variable(var_name, lb=0.0, ub=1.0, vtype="B")

    for index, key in enumerate(translated.dep_order_pair, start=1):
        var_name = f"od_{index}"
        dep_order_var[key] = var_name
        model.add_variable(var_name, lb=0.0, ub=1.0, vtype="B")

    ctx = BuildContext(
        model=model,
        translated=translated,
        config=config,
        event_id=event_id,
        time_var=time_var,
        delay_var=delay_var,
        arr_order_var=arr_order_var,
        dep_order_var=dep_order_var,
    )

    from constraints.registry import get_constraint_modules

    for module in get_constraint_modules():
        module(ctx)

    return model.freeze()

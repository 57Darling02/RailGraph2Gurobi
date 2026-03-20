from __future__ import annotations

from typing import Dict

from core.builder import BuildContext
from core.types import EventKey


def _build_abs_delay_mode(ctx: BuildContext) -> None:
    abs_var: Dict[EventKey, str] = {}
    for event_key in ctx.translated.event_keys:
        var_name = f"a_{ctx.event_id[event_key]}"
        abs_var[event_key] = var_name
        ctx.model.add_variable(var_name, lb=0.0, ub=float(86400 * 2), vtype="I")

    for event_key in ctx.translated.event_keys:
        t_var = ctx.time_var[event_key]
        d_var = ctx.delay_var[event_key]
        a_var = abs_var[event_key]
        planned = float(ctx.translated.event_time[event_key])

        # delay == actual - planned
        ctx.model.add_constraint(
            name=f"abs_delay_eq_{ctx.event_id[event_key]}",
            coefficients={d_var: 1.0, t_var: -1.0},
            sense="=",
            rhs=-planned,
        )
        # abs >= delay
        ctx.model.add_constraint(
            name=f"abs_bound_pos_{ctx.event_id[event_key]}",
            coefficients={a_var: 1.0, d_var: -1.0},
            sense=">=",
            rhs=0.0,
        )
        # abs >= -delay
        ctx.model.add_constraint(
            name=f"abs_bound_neg_{ctx.event_id[event_key]}",
            coefficients={a_var: 1.0, d_var: 1.0},
            sense=">=",
            rhs=0.0,
        )
        ctx.model.add_objective_term(a_var, 1.0)


def _build_cal_delay_plus_cancel_mode(ctx: BuildContext) -> None:
    abs_var: Dict[EventKey, str] = {}
    cancellation_var: Dict[EventKey, str] = {}
    cal_var: Dict[EventKey, str] = {}

    for event_key in ctx.translated.event_keys:
        abs_name = f"a_{ctx.event_id[event_key]}"
        c_name = f"c_{ctx.event_id[event_key]}"
        cal_name = f"cd_{ctx.event_id[event_key]}"
        abs_var[event_key] = abs_name
        cancellation_var[event_key] = c_name
        cal_var[event_key] = cal_name
        ctx.model.add_variable(abs_name, lb=0.0, ub=float(86400 * 2), vtype="I")
        ctx.model.add_variable(c_name, lb=0.0, ub=1.0, vtype="B")
        ctx.model.add_variable(cal_name, lb=0.0, ub=float(86400), vtype="I")

    for event_key in ctx.translated.event_keys:
        t_var = ctx.time_var[event_key]
        d_var = ctx.delay_var[event_key]
        a_var = abs_var[event_key]
        c_var = cancellation_var[event_key]
        cd_var = cal_var[event_key]
        planned = float(ctx.translated.event_time[event_key])

        # delay == actual - planned
        ctx.model.add_constraint(
            name=f"cal_eq_{ctx.event_id[event_key]}",
            coefficients={d_var: 1.0, t_var: -1.0},
            sense="=",
            rhs=-planned,
        )
        # abs linearization
        ctx.model.add_constraint(
            name=f"cal_abs_pos_{ctx.event_id[event_key]}",
            coefficients={a_var: 1.0, d_var: -1.0},
            sense=">=",
            rhs=0.0,
        )
        ctx.model.add_constraint(
            name=f"cal_abs_neg_{ctx.event_id[event_key]}",
            coefficients={a_var: 1.0, d_var: 1.0},
            sense=">=",
            rhs=0.0,
        )

        # cal_delays linearization
        # cd <= (1-c)*M3  -> cd + M3*c <= M3
        m3 = float(86400 * 2)
        ctx.model.add_constraint(
            name=f"cal_active_0_{ctx.event_id[event_key]}",
            coefficients={cd_var: 1.0, c_var: m3},
            sense="<=",
            rhs=m3,
        )
        # cd <= abs
        ctx.model.add_constraint(
            name=f"cal_active_1_{ctx.event_id[event_key]}",
            coefficients={cd_var: 1.0, a_var: -1.0},
            sense="<=",
            rhs=0.0,
        )
        # cd >= abs - c*M3 -> cd - abs + c*M3 >= 0
        ctx.model.add_constraint(
            name=f"cal_active_2_{ctx.event_id[event_key]}",
            coefficients={cd_var: 1.0, a_var: -1.0, c_var: m3},
            sense=">=",
            rhs=0.0,
        )

        # objective
        ctx.model.add_objective_term(cd_var, 1.0)
        ctx.model.add_objective_term(c_var, 1000.0)

    # cancellation departure constraints and consistency
    m1 = float(86400)
    m2 = float(ctx.config.solver.big_m)
    tolerance = float(ctx.config.solver.tolerance_delay_seconds)

    for train_id in ctx.translated.train_ids:
        origin = ctx.translated.train_origins[train_id]
        origin_dep = (train_id, origin, "dep")
        if origin_dep not in cancellation_var:
            continue
        origin_c = cancellation_var[origin_dep]
        origin_abs = abs_var[origin_dep]

        # abs(origin_dep) - tolerance >= (c-1)M2
        # abs - M2*c >= tolerance - M2
        ctx.model.add_constraint(
            name=f"cancel_tol_{ctx.event_id[origin_dep]}",
            coefficients={origin_abs: 1.0, origin_c: -m2},
            sense=">=",
            rhs=tolerance - m2,
        )

        dep_events = [origin_dep]
        for stop in ctx.translated.train_stops[train_id]:
            dep_key = (train_id, stop, "dep")
            if dep_key in cancellation_var:
                dep_events.append(dep_key)

        for dep_key in dep_events:
            # t_dep - planned_dep >= c_dep * M1
            # t_dep - M1*c_dep >= planned_dep
            ctx.model.add_constraint(
                name=f"cancel_dep_{ctx.event_id[dep_key]}",
                coefficients={ctx.time_var[dep_key]: 1.0, cancellation_var[dep_key]: -m1},
                sense=">=",
                rhs=float(ctx.translated.event_time[dep_key]),
            )

        for station in ctx.translated.train_routes[train_id]:
            arr_key = (train_id, station, "arr")
            dep_key = (train_id, station, "dep")
            if arr_key in cancellation_var:
                ctx.model.add_constraint(
                    name=f"cancel_sync_arr_{ctx.event_id[arr_key]}",
                    coefficients={cancellation_var[arr_key]: 1.0, origin_c: -1.0},
                    sense="=",
                    rhs=0.0,
                )
            if dep_key in cancellation_var:
                ctx.model.add_constraint(
                    name=f"cancel_sync_dep_{ctx.event_id[dep_key]}",
                    coefficients={cancellation_var[dep_key]: 1.0, origin_c: -1.0},
                    sense="=",
                    rhs=0.0,
                )


def apply_objective_mode(ctx: BuildContext) -> None:
    mode = ctx.config.solver.objective_mode
    if mode == "delay":
        return
    if mode == "abs":
        _build_abs_delay_mode(ctx)
        return
    if mode == "cal_delay_plus_cancel":
        _build_cal_delay_plus_cancel_mode(ctx)
        return
    raise ValueError(f"Unsupported objective_mode: {mode}")

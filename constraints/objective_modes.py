from __future__ import annotations

from typing import Dict

from core.builder import BuildContext
from core.types import EventKey


def _build_abs_delay_mode(ctx: BuildContext, add_objective: bool) -> Dict[EventKey, str]:
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
        if add_objective:
            ctx.model.add_objective_term(a_var, 1.0)

    return abs_var


def _build_cancellation_overlay(
    ctx: BuildContext,
    base_metric_var: Dict[EventKey, str],
    base_metric_weight: float,
) -> None:
    # cancellation per event with train-level sync, so one train is canceled consistently.
    cancellation_var: Dict[EventKey, str] = {}
    active_metric_var: Dict[EventKey, str] = {}

    for event_key in ctx.translated.event_keys:
        c_name = f"c_{ctx.event_id[event_key]}"
        m_name = f"m_{ctx.event_id[event_key]}"
        cancellation_var[event_key] = c_name
        active_metric_var[event_key] = m_name
        ctx.model.add_variable(c_name, lb=0.0, ub=1.0, vtype="B")
        ctx.model.add_variable(m_name, lb=0.0, ub=float(86400 * 2), vtype="I")

    metric_big_m = float(86400 * 2)
    for event_key in ctx.translated.event_keys:
        c_var = cancellation_var[event_key]
        base_var = base_metric_var[event_key]
        active_var = active_metric_var[event_key]

        # active <= base
        ctx.model.add_constraint(
            name=f"cancel_active_ub_base_{ctx.event_id[event_key]}",
            coefficients={active_var: 1.0, base_var: -1.0},
            sense="<=",
            rhs=0.0,
        )
        # active <= (1-c)*M  => active + M*c <= M
        ctx.model.add_constraint(
            name=f"cancel_active_ub_switch_{ctx.event_id[event_key]}",
            coefficients={active_var: 1.0, c_var: metric_big_m},
            sense="<=",
            rhs=metric_big_m,
        )
        # active >= base - c*M => active - base + c*M >= 0
        ctx.model.add_constraint(
            name=f"cancel_active_lb_{ctx.event_id[event_key]}",
            coefficients={active_var: 1.0, base_var: -1.0, c_var: metric_big_m},
            sense=">=",
            rhs=0.0,
        )
        ctx.model.add_objective_term(active_var, base_metric_weight)

    # cancellation threshold and consistency constraints
    time_big_m = float(ctx.config.solver.big_m)
    departure_big_m = float(86400)
    tolerance = float(ctx.config.solver.tolerance_delay_seconds)
    cancel_penalty = float(ctx.config.solver.cancellation_penalty_weight)

    for train_id in ctx.translated.train_ids:
        origin = ctx.translated.train_origins[train_id]
        origin_dep = (train_id, origin, "dep")
        if origin_dep not in cancellation_var:
            continue

        origin_c = cancellation_var[origin_dep]
        origin_metric = base_metric_var[origin_dep]

        # If canceled, origin metric must exceed tolerance.
        ctx.model.add_constraint(
            name=f"cancel_tol_{ctx.event_id[origin_dep]}",
            coefficients={origin_metric: 1.0, origin_c: -time_big_m},
            sense=">=",
            rhs=tolerance - time_big_m,
        )

        # penalize cancellation once per train (origin dep event).
        ctx.model.add_objective_term(origin_c, cancel_penalty)

        dep_events = [origin_dep]
        for stop in ctx.translated.train_stops[train_id]:
            dep_key = (train_id, stop, "dep")
            if dep_key in cancellation_var:
                dep_events.append(dep_key)

        for dep_key in dep_events:
            # c=1 => t_dep can be shifted by large-M.
            ctx.model.add_constraint(
                name=f"cancel_dep_{ctx.event_id[dep_key]}",
                coefficients={ctx.time_var[dep_key]: 1.0, cancellation_var[dep_key]: -departure_big_m},
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
    if mode not in {"delay", "abs"}:
        raise ValueError(f"Unsupported objective_mode: {mode}")

    if mode == "abs":
        abs_var = _build_abs_delay_mode(
            ctx,
            add_objective=not ctx.config.solver.cancellation_enabled,
        )
        if ctx.config.solver.cancellation_enabled:
            _build_cancellation_overlay(ctx, abs_var, base_metric_weight=1.0)
        return

    # delay mode
    if ctx.config.solver.cancellation_enabled:
        _build_cancellation_overlay(
            ctx,
            ctx.delay_var,
            base_metric_weight=float(ctx.config.solver.objective_delay_weight),
        )


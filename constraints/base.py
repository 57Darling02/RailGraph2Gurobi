from __future__ import annotations

from typing import List, Tuple

from core.builder import BuildContext

Section = Tuple[str, str]


def _get_same_sub_route(route1: List[str], route2: List[str]) -> List[Section]:
    same_sub_route: List[Section] = []
    sub_route: List[str] = [station for station in route1 if station in route2]
    for i in range(len(sub_route) - 1):
        s = sub_route[i]
        s_next = sub_route[i + 1]
        index_s_r1 = route1.index(s)
        index_s_next_r1 = route1.index(s_next)
        index_s_r2 = route2.index(s)
        index_s_next_r2 = route2.index(s_next)
        if (index_s_next_r1 - index_s_r1 == 1) and (index_s_next_r2 - index_s_r2 == 1):
            same_sub_route.append((s, s_next))
    return same_sub_route


def apply_base_constraints(ctx: BuildContext) -> None:
    big_m = float(ctx.config.solver.big_m)
    arr_headway = float(ctx.config.solver.arr_arr_headway_seconds)
    dep_headway = float(ctx.config.solver.dep_dep_headway_seconds)
    min_stop_dwell = float(ctx.config.solver.dwell_seconds_at_stops)

    for event_key in ctx.translated.event_keys:
        t_var = ctx.time_var[event_key]
        d_var = ctx.delay_var[event_key]
        planned = float(ctx.translated.event_time[event_key])

        # Legacy-compatible delay lower bounds:
        # delay >= actual - planned, delay >= 0
        ctx.model.add_constraint(
            name=f"delay_lb_{ctx.event_id[event_key]}",
            coefficients={d_var: 1.0, t_var: -1.0},
            sense=">=",
            rhs=-planned,
        )
        ctx.model.add_constraint(
            name=f"delay_nonneg_{ctx.event_id[event_key]}",
            coefficients={d_var: 1.0},
            sense=">=",
            rhs=0.0,
        )

        if ctx.config.solver.objective_mode == "delay" and not ctx.config.solver.cancellation_enabled:
            ctx.model.add_objective_term(d_var, ctx.config.solver.objective_delay_weight)

    for train_id, route in ctx.translated.train_routes.items():
        origin = ctx.translated.train_origins[train_id]
        origin_dep_key = (train_id, origin, "dep")
        if origin_dep_key in ctx.time_var:
            ctx.model.add_constraint(
                name=f"origin_dep_{ctx.event_id[origin_dep_key]}",
                coefficients={ctx.time_var[origin_dep_key]: 1.0},
                sense=">=",
                rhs=float(ctx.translated.event_time[origin_dep_key]),
            )

        for station in ctx.translated.train_stops[train_id]:
            dep_key = (train_id, station, "dep")
            if dep_key in ctx.time_var:
                ctx.model.add_constraint(
                    name=f"stop_dep_{ctx.event_id[dep_key]}",
                    coefficients={ctx.time_var[dep_key]: 1.0},
                    sense=">=",
                    rhs=float(ctx.translated.event_time[dep_key]),
                )

        # dep >= arr (logical) and legacy stop-dwell lower bound on stops only
        for station in route:
            arr_key = (train_id, station, "arr")
            dep_key = (train_id, station, "dep")
            if arr_key in ctx.time_var and dep_key in ctx.time_var:
                ctx.model.add_constraint(
                    name=f"logical_dep_arr_{ctx.event_id[dep_key]}",
                    coefficients={ctx.time_var[dep_key]: 1.0, ctx.time_var[arr_key]: -1.0},
                    sense=">=",
                    rhs=0.0,
                )
            if station in ctx.translated.train_stops[train_id] and arr_key in ctx.time_var and dep_key in ctx.time_var:
                ctx.model.add_constraint(
                    name=f"dwell_stop_{ctx.event_id[dep_key]}",
                    coefficients={ctx.time_var[dep_key]: 1.0, ctx.time_var[arr_key]: -1.0},
                    sense=">=",
                    rhs=min_stop_dwell,
                )

    for train_id, sections in ctx.translated.train_sections.items():
        for start_station, end_station in sections:
            dep_key = (train_id, start_station, "dep")
            arr_key = (train_id, end_station, "arr")
            runtime_min = float(ctx.translated.section_min_runtime[(start_station, end_station)])
            ctx.model.add_constraint(
                name=f"runtime_{ctx.event_id[arr_key]}",
                coefficients={ctx.time_var[arr_key]: 1.0, ctx.time_var[dep_key]: -1.0},
                sense=">=",
                rhs=runtime_min,
            )

    for pair_key in ctx.translated.arr_order_pair:
        tr1, tr2, station, event_type = pair_key
        if station == ctx.translated.train_origins[tr1] or station == ctx.translated.train_origins[tr2]:
            continue

        e1 = (tr1, station, event_type)
        e2 = (tr2, station, event_type)
        if e1 not in ctx.time_var or e2 not in ctx.time_var:
            continue

        oa = ctx.arr_order_var[pair_key]
        # t2 - t1 >= h + (oa - 1)M
        ctx.model.add_constraint(
            name=f"arr_headway_0_{station}",
            coefficients={ctx.time_var[e2]: 1.0, ctx.time_var[e1]: -1.0, oa: -big_m},
            sense=">=",
            rhs=arr_headway - big_m,
        )
        # t1 - t2 >= h - oa*M
        ctx.model.add_constraint(
            name=f"arr_headway_1_{station}",
            coefficients={ctx.time_var[e1]: 1.0, ctx.time_var[e2]: -1.0, oa: big_m},
            sense=">=",
            rhs=arr_headway,
        )

    for pair_key in ctx.translated.dep_order_pair:
        tr1, tr2, station, event_type = pair_key
        if station == ctx.translated.train_destinations[tr1] or station == ctx.translated.train_destinations[tr2]:
            continue

        e1 = (tr1, station, event_type)
        e2 = (tr2, station, event_type)
        if e1 not in ctx.time_var or e2 not in ctx.time_var:
            continue

        od = ctx.dep_order_var[pair_key]
        # t2 - t1 >= h + (od - 1)M
        ctx.model.add_constraint(
            name=f"dep_headway_0_{station}",
            coefficients={ctx.time_var[e2]: 1.0, ctx.time_var[e1]: -1.0, od: -big_m},
            sense=">=",
            rhs=dep_headway - big_m,
        )
        # t1 - t2 >= h - od*M
        ctx.model.add_constraint(
            name=f"dep_headway_1_{station}",
            coefficients={ctx.time_var[e1]: 1.0, ctx.time_var[e2]: -1.0, od: big_m},
            sense=">=",
            rhs=dep_headway,
        )

    for pair_key in ctx.translated.arr_order_single:
        tr1, tr2, station, event_type = pair_key
        reverse = (tr2, tr1, station, event_type)
        if pair_key not in ctx.arr_order_var or reverse not in ctx.arr_order_var:
            continue
        ctx.model.add_constraint(
            name=f"arr_order_binary_{station}",
            coefficients={ctx.arr_order_var[pair_key]: 1.0, ctx.arr_order_var[reverse]: 1.0},
            sense="=",
            rhs=1.0,
        )

    for pair_key in ctx.translated.dep_order_single:
        tr1, tr2, station, event_type = pair_key
        reverse = (tr2, tr1, station, event_type)
        if pair_key not in ctx.dep_order_var or reverse not in ctx.dep_order_var:
            continue
        ctx.model.add_constraint(
            name=f"dep_order_binary_{station}",
            coefficients={ctx.dep_order_var[pair_key]: 1.0, ctx.dep_order_var[reverse]: 1.0},
            sense="=",
            rhs=1.0,
        )

    for pair_key in ctx.translated.arr_order_pair:
        tr1, tr2, station, _ = pair_key
        if station == ctx.translated.train_origins[tr1] or station == ctx.translated.train_origins[tr2]:
            continue

        route1 = ctx.translated.train_routes[tr1]
        route2 = ctx.translated.train_routes[tr2]
        before_station = station
        same_sub_route = _get_same_sub_route(route1, route2)
        for section in same_sub_route:
            if station == section[1]:
                before_station = section[0]
                break
        if before_station == station:
            continue

        dep_pair = (tr1, tr2, before_station, "dep")
        if dep_pair not in ctx.dep_order_var:
            continue

        ctx.model.add_constraint(
            name=f"overtake_{tr1}_{tr2}_{before_station}_{station}",
            coefficients={
                ctx.arr_order_var[pair_key]: 1.0,
                ctx.dep_order_var[dep_pair]: -1.0,
            },
            sense="=",
            rhs=0.0,
        )

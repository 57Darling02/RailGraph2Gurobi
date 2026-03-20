from __future__ import annotations

from core.builder import BuildContext


def apply_interruption_constraints(ctx: BuildContext) -> None:
    big_m = float(ctx.config.solver.big_m)

    for interruption in ctx.config.scenarios.interruptions:
        section = (interruption.start_station, interruption.end_station)

        for train_id, sections in ctx.translated.train_sections.items():
            if section not in sections:
                continue

            dep_key = (train_id, interruption.start_station, "dep")
            arr_key = (train_id, interruption.end_station, "arr")

            # z=1: pass before interruption start, z=0: depart after interruption end.
            z_var = f"z_interrupt_{ctx.event_id[dep_key]}"
            ctx.model.add_variable(z_var, lb=0.0, ub=1.0, vtype="B")

            start_time = float(interruption.start_time)
            end_time = float(interruption.end_time)

            # AT_arr(s2) <= T_start + M * (1 - z)
            ctx.model.add_constraint(
                name=f"interrupt_before_{ctx.event_id[arr_key]}",
                coefficients={ctx.time_var[arr_key]: 1.0, z_var: big_m},
                sense="<=",
                rhs=start_time + big_m,
            )

            # AT_dep(s1) >= T_end - M * z
            ctx.model.add_constraint(
                name=f"interrupt_after_{ctx.event_id[dep_key]}",
                coefficients={ctx.time_var[dep_key]: 1.0, z_var: big_m},
                sense=">=",
                rhs=end_time,
            )

from __future__ import annotations

from core.builder import BuildContext


def apply_delay_constraints(ctx: BuildContext) -> None:
    for delay in ctx.config.scenarios.delays:
        event_key = (delay.train_id, delay.station, delay.event_type)
        t_var = ctx.time_var[event_key]
        planned = ctx.translated.event_time[event_key]
        rhs = float(planned + delay.seconds)

        ctx.model.add_constraint(
            name=f"primary_delay_{ctx.event_id[event_key]}",
            coefficients={t_var: 1.0},
            sense=">=",
            rhs=rhs,
        )

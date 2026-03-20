from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple


def solve_lp(lp_path: Path, solution_path: Path) -> Tuple[float, Dict[str, float]]:
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency: gurobipy") from exc

    model = gp.read(str(lp_path))
    model.optimize()

    if model.status != GRB.OPTIMAL:
        raise RuntimeError(f"Gurobi optimize failed, status={model.status}")

    solution_path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(solution_path))

    values = {var.VarName: float(var.X) for var in model.getVars()}
    return float(model.objVal), values


def load_solution_values(solution_path: Path) -> Dict[str, float]:
    values: Dict[str, float] = {}
    if not solution_path.exists():
        raise FileNotFoundError(f"Solution file not found: {solution_path}")

    with solution_path.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            parts = text.split()
            if len(parts) < 2:
                continue
            var_name = parts[0]
            try:
                var_value = float(parts[1])
            except ValueError:
                continue
            values[var_name] = var_value
    return values

from __future__ import annotations

from pathlib import Path
from typing import Dict

from core.types import LinearModel


def _format_linear_expression(coefficients: Dict[str, float]) -> str:
    if not coefficients:
        return "0"

    terms = []
    for var_name in sorted(coefficients.keys()):
        coefficient = coefficients[var_name]
        if coefficient == 0:
            continue
        sign = "+" if coefficient >= 0 else "-"
        abs_coef = abs(coefficient)
        if abs_coef == 1:
            term = f" {sign} {var_name}"
        else:
            term = f" {sign} {abs_coef:g} {var_name}"
        terms.append(term)

    if not terms:
        return "0"

    expression = "".join(terms).strip()
    if expression.startswith("+"):
        expression = expression[1:].strip()
    return expression


def export_lp(model: LinearModel, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("Minimize" if model.objective_sense == "min" else "Maximize")
    lines.append(f" obj: {_format_linear_expression(model.objective)}")

    lines.append("Subject To")
    for constraint in model.constraints:
        left = _format_linear_expression(constraint.coefficients)
        lines.append(f" {constraint.name}: {left} {constraint.sense} {constraint.rhs:g}")

    lines.append("Bounds")
    for var_name in sorted(model.variables.keys()):
        lb, ub, _ = model.variables[var_name]
        if ub is None:
            lines.append(f" {lb:g} <= {var_name}")
        else:
            lines.append(f" {lb:g} <= {var_name} <= {ub:g}")

    binary_vars = [name for name, (_, _, vtype) in model.variables.items() if vtype == "B"]
    integer_vars = [name for name, (_, _, vtype) in model.variables.items() if vtype == "I"]

    if binary_vars:
        lines.append("Binary")
        for var_name in sorted(binary_vars):
            lines.append(f" {var_name}")

    if integer_vars:
        lines.append("General")
        for var_name in sorted(integer_vars):
            lines.append(f" {var_name}")

    lines.append("End")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

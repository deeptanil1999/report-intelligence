from datetime import date


def run_flags(sample_set: dict, cylinders: list[dict]) -> list[dict]:
    """
    Run all compliance rules against a sample set and its cylinders.
    Returns a list of flag dicts.
    """
    flags = []

    def add_flag(code, severity, description, reference=None, field_name=None, field_value=None, spec_value=None, cylinder_id=None):
        flags.append({
            "flag_code": code,
            "severity": severity,
            "description": description,
            "standard_reference": reference,
            "field_name": field_name,
            "field_value": str(field_value) if field_value is not None else None,
            "spec_value": str(spec_value) if spec_value is not None else None,
            "cylinder_id": cylinder_id,
        })

    slump = sample_set.get("slump_result")
    slump_min = sample_set.get("slump_spec_min")
    slump_max = sample_set.get("slump_spec_max")

    # Rule 1 — SLUMP_OUT_OF_SPEC
    if slump is not None and slump_min is not None and slump_max is not None:
        if slump < slump_min or slump > slump_max:
            add_flag(
                "SLUMP_OUT_OF_SPEC",
                "critical",
                f'Slump {slump}" is outside specified range {slump_min}" to {slump_max}"',
                "Project specification",
                "slump_result",
                slump,
                f'{slump_min}" to {slump_max}"',
            )

    # Rule 2 — AIR_CONTENT_OUT_OF_SPEC
    air = sample_set.get("air_content_result")
    air_min = sample_set.get("air_content_spec_min")
    air_max = sample_set.get("air_content_spec_max")
    if air is not None and air_min is not None and air_max is not None:
        if air < air_min or air > air_max:
            add_flag(
                "AIR_CONTENT_OUT_OF_SPEC",
                "warning",
                f"Air content {air}% is outside specified range {air_min}% to {air_max}%",
                "Project specification",
                "air_content_result",
                air,
                f"{air_min}% to {air_max}%",
            )

    # Rule 3 — CONCRETE_TEMP_EXCEEDED
    temp = sample_set.get("concrete_temp_result")
    temp_max = sample_set.get("concrete_temp_spec_max")
    if temp is not None and temp_max is not None:
        if temp > temp_max:
            add_flag(
                "CONCRETE_TEMP_EXCEEDED",
                "critical",
                f"Concrete temperature {temp}°F exceeds maximum allowable {temp_max}°F",
                "ACI 305R / Project specification",
                "concrete_temp_result",
                temp,
                f"MAX {temp_max}°F",
            )

    # Rule 4 — WATER_ADDED_AFTER_SAMPLING
    water_after = sample_set.get("water_added_after_gal") or 0
    if water_after and water_after > 0:
        add_flag(
            "WATER_ADDED_AFTER_SAMPLING",
            "critical",
            f"{water_after} gal of water added after sampling — invalidates test per ASTM C94",
            "ASTM C94",
            "water_added_after_gal",
            water_after,
            "0 gal",
        )

    # Rules 5 & 8 — per-cylinder rules
    specified_strength = sample_set.get("specified_strength_psi")

    for cyl in cylinders:
        cyl_id = cyl.get("id")
        spec_id = cyl.get("spec_id", "?")
        age = cyl.get("age_at_test_days")
        strength = cyl.get("comp_strength_psi")
        condition = cyl.get("cylinder_condition")

        # Rule 5 — STRENGTH_BELOW_MINIMUM_INDIVIDUAL
        if age == 28 and strength is not None and specified_strength:
            f_prime_c = specified_strength
            if f_prime_c <= 5000:
                minimum = f_prime_c - 500
            else:
                minimum = 0.90 * f_prime_c

            if strength < minimum:
                add_flag(
                    "STRENGTH_BELOW_MINIMUM_INDIVIDUAL",
                    "critical",
                    f"28-day result {strength} psi is below the minimum allowable {minimum:.0f} psi (f'c = {f_prime_c} psi)",
                    "ACI 318-19 Section 26.12.3.1",
                    "comp_strength_psi",
                    strength,
                    f"{minimum:.0f} psi",
                    cylinder_id=cyl_id,
                )

        # Rule 8 — CYLINDER_CONDITION_NOT_GOOD
        if condition and condition.strip() not in ("", "Good"):
            add_flag(
                "CYLINDER_CONDITION_NOT_GOOD",
                "warning",
                f"Cylinder {spec_id} condition recorded as '{condition}'",
                None,
                "cylinder_condition",
                condition,
                "Good",
                cylinder_id=cyl_id,
            )

        # Rule 9 — RESULT_PENDING_OVERDUE
        if strength is None and cyl.get("date_tested"):
            date_tested = cyl["date_tested"]
            if isinstance(date_tested, str):
                try:
                    from datetime import datetime
                    date_tested = datetime.fromisoformat(date_tested).date()
                except Exception:
                    date_tested = None
            if date_tested and date.today() > date_tested:
                add_flag(
                    "RESULT_PENDING_OVERDUE",
                    "info",
                    f"Cylinder {spec_id} was scheduled to be tested on {cyl['date_tested']} but no result has been recorded",
                    None,
                    "comp_strength_psi",
                    None,
                    None,
                    cylinder_id=cyl_id,
                )

    # Rule 6 — STRENGTH_28_DAY_AVERAGE_BELOW_FC
    avg_28 = sample_set.get("avg_28_day_strength_psi")
    if avg_28 is not None and specified_strength and avg_28 < specified_strength:
        add_flag(
            "STRENGTH_28_DAY_AVERAGE_BELOW_FC",
            "critical",
            f"28-day average {avg_28} psi is below specified strength {specified_strength} psi",
            "ACI 318-19 Section 26.12.3.1",
            "avg_28_day_strength_psi",
            avg_28,
            f"{specified_strength} psi",
        )

    # Rule 7 — PLASTIC_UNIT_WEIGHT_NOT_TESTED
    if sample_set.get("plastic_unit_weight") is None:
        add_flag(
            "PLASTIC_UNIT_WEIGHT_NOT_TESTED",
            "info",
            "Plastic unit weight was not tested",
            None,
            "plastic_unit_weight",
            None,
            None,
        )

    return flags

from utils.claude_client import classify_with_claude


def classify_report(raw_text: str) -> dict:
    text_upper = raw_text.upper()

    if "CONCRETE COMPRESSIVE STRENGTH TEST REPORT" in text_upper and "ASTM C39" in text_upper:
        return {"report_type": "concrete_compressive_strength", "confidence": 0.98}

    if "CONCRETE CORE TEST" in text_upper:
        return {"report_type": "concrete_core_test", "confidence": 0.95}

    if "GROUT COMPRESSIVE STRENGTH" in text_upper:
        return {"report_type": "grout_compressive_strength", "confidence": 0.95}

    if "POST-TENSION STRESSING" in text_upper:
        return {"report_type": "post_tension_stressing", "confidence": 0.95}

    if "FIELD DENSITY TEST" in text_upper:
        return {"report_type": "field_density", "confidence": 0.95}

    result = classify_with_claude(raw_text)
    if not result:
        result = {"report_type": "unknown", "confidence": 0.0}

    if result.get("confidence", 0) < 0.75:
        raise ValueError(
            f"Unknown report type (confidence {result.get('confidence', 0):.0%}) — manual review required"
        )

    return result

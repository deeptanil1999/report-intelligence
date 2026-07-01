import re
import logging
from datetime import datetime
from typing import Any
import pdfplumber
from utils.claude_client import extract_fields

logger = logging.getLogger(__name__)


# ── Spec string parser ────────────────────────────────────────────────────────

def parse_spec_string(s: str) -> tuple[float | None, float | None]:
    if not s:
        return None, None
    s = s.strip()

    # "X MAX" or "MAX X"
    max_match = re.match(r'^(\d+\.?\d*)\s*MAX$', s, re.IGNORECASE)
    if max_match:
        return 0.0, float(max_match.group(1))
    max_match2 = re.match(r'^MAX\s+(\d+\.?\d*)$', s, re.IGNORECASE)
    if max_match2:
        return 0.0, float(max_match2.group(1))

    # "X" to "Y" (with optional inch marks)
    range_match = re.match(r'"?(\d+\.?\d*)"?\s+to\s+"?(\d+\.?\d*)"?', s, re.IGNORECASE)
    if range_match:
        return float(range_match.group(1)), float(range_match.group(2))

    # "X +/- Y" or "X ± Y"
    pm_match = re.match(r'(\d+\.?\d*)\s*(?:\+/-|±)\s*(\d+\.?\d*)', s)
    if pm_match:
        center = float(pm_match.group(1))
        delta = float(pm_match.group(2))
        return round(center - delta, 4), round(center + delta, 4)

    # Single number — treat as minimum only
    single_match = re.match(r'^(\d+\.?\d*)$', s)
    if single_match:
        return float(single_match.group(1)), None

    return None, None


# ── Date parsing ──────────────────────────────────────────────────────────────

def _parse_date(s: str | None) -> str | None:
    if not s:
        return None
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        cleaned = str(val).replace(",", "").strip()
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


def _to_int(val: Any) -> int | None:
    f = _to_float(val)
    return int(f) if f is not None else None


# ── Header extraction ─────────────────────────────────────────────────────────

def _extract_header(full_text: str) -> dict:
    header = {}

    m = re.search(r'Report\s+(?:No|Number)[.:]?\s*([\w.\-]+(?:Rev\d+)?)', full_text, re.IGNORECASE)
    header["report_number"] = m.group(1).strip() if m else None

    m = re.search(r'Service\s+Date[:\s]+([\d]{1,2}/[\d]{2}/[\d]{2,4})', full_text, re.IGNORECASE)
    header["service_date"] = _parse_date(m.group(1)) if m else None

    m = re.search(r'Report\s+Date[:\s]+([\d]{1,2}/[\d]{2}/[\d]{2,4})', full_text, re.IGNORECASE)
    header["report_date"] = _parse_date(m.group(1)) if m else None

    m = re.search(r'Task[:\s]+(.+)', full_text, re.IGNORECASE)
    header["task"] = m.group(1).strip()[:200] if m else None

    m = re.search(
        r'Specified\s+Strength[:\s]+([\d,]+)\s*psi\s*@\s*(\d+)\s*days?',
        full_text,
        re.IGNORECASE,
    )
    if m:
        header["specified_strength_psi"] = _to_int(m.group(1))
        header["strength_age_days"] = _to_int(m.group(2))
    else:
        header["specified_strength_psi"] = None
        header["strength_age_days"] = None

    return header


# ── Field test data extraction ────────────────────────────────────────────────

def _extract_field_value_spec(text: str, label: str) -> tuple[float | None, float | None, float | None]:
    """Returns (result, spec_min, spec_max) for a given field label."""
    pattern = re.compile(
        label + r'[:\s]*([\d.]+)\s*(?:in|°F|%|pcf|yd[s³]?)?\s*'
        r'(?:Spec(?:ification)?[:\s]*([^\n]+))?',
        re.IGNORECASE,
    )
    m = pattern.search(text)
    result = _to_float(m.group(1)) if m else None
    spec_min, spec_max = None, None
    if m and m.group(2):
        spec_min, spec_max = parse_spec_string(m.group(2).strip())
    return result, spec_min, spec_max


def _extract_field_tests(page_text: str) -> dict:
    data = {}

    # Slump
    m = re.search(
        r'Slump[:\s]*([\d.]+)(?:\s*"|\s*in)?\s*(?:Spec(?:ification)?[.:\s]*)?"?([^"\n]+)"?',
        page_text,
        re.IGNORECASE,
    )
    if m:
        data["slump_result"] = _to_float(m.group(1))
        if m.group(2):
            mn, mx = parse_spec_string(m.group(2).strip())
            data["slump_spec_min"] = mn
            data["slump_spec_max"] = mx
    else:
        data["slump_result"] = None

    # Air content
    m = re.search(
        r'Air\s+Content[:\s]*([\d.]+)\s*%?\s*(?:Spec(?:ification)?[.:\s]*)?([\d.+/\-±%\s"MAX]+)',
        page_text,
        re.IGNORECASE,
    )
    if m:
        data["air_content_result"] = _to_float(m.group(1))
        mn, mx = parse_spec_string(m.group(2).strip())
        data["air_content_spec_min"] = mn
        data["air_content_spec_max"] = mx
    else:
        data["air_content_result"] = None

    # Concrete temperature
    m = re.search(
        r'Concrete\s+Temp(?:erature)?[:\s]*([\d.]+)\s*°?F?\s*(?:Spec(?:ification)?[.:\s]*)?([\d.+/\-±°F\s"MAX]+)?',
        page_text,
        re.IGNORECASE,
    )
    if m:
        data["concrete_temp_result"] = _to_float(m.group(1))
        if m.group(2):
            _, mx = parse_spec_string(m.group(2).strip())
            data["concrete_temp_spec_max"] = mx
        else:
            data["concrete_temp_spec_max"] = None
    else:
        data["concrete_temp_result"] = None

    # Ambient temp
    m = re.search(r'Ambient\s+Temp(?:erature)?[:\s]*([\d.]+)', page_text, re.IGNORECASE)
    data["ambient_temp"] = _to_float(m.group(1)) if m else None

    # Plastic unit weight
    m = re.search(r'(?:Plastic\s+)?Unit\s+Weight[:\s]*([\d.]+)', page_text, re.IGNORECASE)
    data["plastic_unit_weight"] = _to_float(m.group(1)) if m else None

    # Yield
    m = re.search(r'Yield[:\s]*([\d.]+)', page_text, re.IGNORECASE)
    data["yield_cu_yds"] = _to_float(m.group(1)) if m else None

    # Water added
    m = re.search(r'Water\s+Added\s+Before\s+(?:Sampling)?[:\s]*([\d.]+)', page_text, re.IGNORECASE)
    data["water_added_before_gal"] = _to_float(m.group(1)) if m else 0.0

    m = re.search(r'Water\s+Added\s+After\s+(?:Sampling)?[:\s]*([\d.]+)', page_text, re.IGNORECASE)
    data["water_added_after_gal"] = _to_float(m.group(1)) if m else 0.0

    return data


# ── Material / sample info extraction ────────────────────────────────────────

def _extract_material_info(page_text: str) -> dict:
    data = {}
    fields = {
        "mix_id": r'Mix\s+(?:ID|Design|No\.?)[:\s]*([\w\-/]+)',
        "supplier": r'Supplier[:\s]+(.+)',
        "batch_time": r'Batch\s+Time[:\s]*([\d:APMapm\s]+)',
        "truck_number": r'Truck\s+(?:No\.?|Number)[:\s]*([\w\-]+)',
        "plant": r'Plant[:\s]+(.+)',
        "ticket_number": r'Ticket\s+(?:No\.?|Number)[:\s]*([\w\-]+)',
    }
    for key, pattern in fields.items():
        m = re.search(pattern, page_text, re.IGNORECASE)
        data[key] = m.group(1).strip()[:200] if m else None
    return data


def _extract_sample_info(page_text: str) -> dict:
    data = {}

    m = re.search(r'Sample\s+Date[:\s]+([\d]{1,2}/[\d]{2}/[\d]{2,4})', page_text, re.IGNORECASE)
    data["sample_date"] = _parse_date(m.group(1)) if m else None

    m = re.search(r'Sample\s+Time[:\s]*([\d:APMapm\s]+)', page_text, re.IGNORECASE)
    data["sample_time"] = m.group(1).strip() if m else None

    m = re.search(r'Sampled\s+By[:\s]+(.+)', page_text, re.IGNORECASE)
    data["sampled_by"] = m.group(1).strip()[:200] if m else None

    m = re.search(r'Weather[:\s]+(.+)', page_text, re.IGNORECASE)
    data["weather_conditions"] = m.group(1).strip()[:200] if m else None

    m = re.search(r'Accumulative\s+(?:Yard|CY)[:\s]*([\d.]+)', page_text, re.IGNORECASE)
    data["accumulative_yards"] = _to_float(m.group(1)) if m else None

    m = re.search(r'Batch\s+Size[:\s]*([\d.]+)', page_text, re.IGNORECASE)
    data["batch_size_cy"] = _to_float(m.group(1)) if m else None

    m = re.search(r'Placement\s+Method[:\s]+(.+)', page_text, re.IGNORECASE)
    data["placement_method"] = m.group(1).strip()[:200] if m else None

    m = re.search(r'Sample\s+Location[:\s]+(.+)', page_text, re.IGNORECASE)
    data["sample_location"] = m.group(1).strip()[:500] if m else None

    m = re.search(r'Placement\s+Location[:\s]+(.+)', page_text, re.IGNORECASE)
    data["placement_location"] = m.group(1).strip()[:500] if m else None

    m = re.search(r'(?:Sample\s+)?Description[:\s]+(.+)', page_text, re.IGNORECASE)
    data["sample_description"] = m.group(1).strip()[:500] if m else None

    m = re.search(r'Initial\s+Cure[:\s]+(.+)', page_text, re.IGNORECASE)
    data["initial_cure"] = m.group(1).strip()[:200] if m else None

    m = re.search(r'Final\s+Cure[:\s]+(.+)', page_text, re.IGNORECASE)
    data["final_cure"] = m.group(1).strip()[:200] if m else None

    m = re.search(r'Comments?[:\s]+(.+)', page_text, re.IGNORECASE)
    data["comments"] = m.group(1).strip()[:1000] if m else None

    return data


# ── Cylinder table extraction ─────────────────────────────────────────────────

def _parse_cylinder_row(row: list[str | None]) -> dict | None:
    """Parse a single table row into a cylinder dict. Returns None if not a data row."""
    if not row or len(row) < 3:
        return None

    # Clean cells
    cells = [str(c).strip() if c is not None else "" for c in row]

    # Skip header rows
    header_keywords = {"set", "spec", "cyl", "diam", "area", "received", "tested", "age", "load", "strength", "frac", "type"}
    if any(kw in cells[0].lower() for kw in header_keywords):
        return None

    # Spec ID should be a short identifier like A, B, C, D, E, or number
    spec_id = cells[1] if len(cells) > 1 else ""
    if not spec_id or len(spec_id) > 5:
        return None

    try:
        return {
            "spec_id": spec_id or None,
            "cylinder_condition": cells[2] if len(cells) > 2 else None,
            "avg_diameter_in": _to_float(cells[3]) if len(cells) > 3 else None,
            "area_sq_in": _to_float(cells[4]) if len(cells) > 4 else None,
            "date_received": _parse_date(cells[5]) if len(cells) > 5 else None,
            "date_tested": _parse_date(cells[6]) if len(cells) > 6 else None,
            "age_at_test_days": _to_int(cells[7]) if len(cells) > 7 else None,
            "max_load_lbs": _to_float(cells[8]) if len(cells) > 8 else None,
            "comp_strength_psi": _to_float(cells[9]) if len(cells) > 9 else None,
            "frac_type": cells[10] if len(cells) > 10 else None,
            "tested_by": cells[11] if len(cells) > 11 else None,
        }
    except Exception:
        return None


def _extract_cylinders_from_tables(page) -> list[dict]:
    cylinders = []
    try:
        tables = page.extract_tables()
        for table in tables:
            for row in table:
                cyl = _parse_cylinder_row(row)
                if cyl and (cyl["spec_id"] or cyl["comp_strength_psi"]):
                    cylinders.append(cyl)
    except Exception as e:
        logger.warning(f"Table extraction error: {e}")
    return cylinders


# ── Claude fallback for missing fields ───────────────────────────────────────

def _fill_missing_with_claude(data: dict, page_text: str, required_fields: list[str]) -> dict:
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        claude_data = extract_fields(page_text, missing)
        for field in missing:
            if claude_data.get(field):
                data[field] = claude_data[field]
    return data


# ── Main parser ───────────────────────────────────────────────────────────────

def parse_concrete_compressive(raw_text: str, pages: list) -> dict:
    """
    Parse a Concrete Compressive Strength report.
    Returns a dict with keys: header (dict), sample_sets (list of dicts),
    where each sample_set contains: material, field_tests, sample_info,
    avg_28_day_strength_psi, cylinders (list).
    """
    header = _extract_header(raw_text)

    # Fill missing header fields via Claude
    required_header = ["report_number", "service_date", "specified_strength_psi"]
    header = _fill_missing_with_claude(header, raw_text[:3000], required_header)

    sample_sets = []

    # Detect page boundaries for multi-set PDFs
    # A new sample set starts when a new Ticket No. appears on a new page
    page_groups = _group_pages_by_sample_set(pages)

    for set_idx, page_group in enumerate(page_groups):
        page_text = "\n".join(p.extract_text() or "" for p in page_group)

        material = _extract_material_info(page_text)
        field_tests = _extract_field_tests(page_text)
        sample_info = _extract_sample_info(page_text)

        # Inherit header-level strength spec
        material["specified_strength_psi"] = (
            material.get("specified_strength_psi") or header.get("specified_strength_psi")
        )
        material["strength_age_days"] = (
            material.get("strength_age_days") or header.get("strength_age_days")
        )

        # Extract cylinders
        cylinders = []
        for page in page_group:
            cylinders.extend(_extract_cylinders_from_tables(page))

        # If table extraction yielded nothing, try text-based parse
        if not cylinders:
            cylinders = _extract_cylinders_from_text(page_text)

        # Compute 28-day average
        strengths_28 = [
            c["comp_strength_psi"]
            for c in cylinders
            if c.get("age_at_test_days") == 28 and c.get("comp_strength_psi") is not None
        ]
        avg_28 = round(sum(strengths_28) / len(strengths_28), 1) if strengths_28 else None

        # Claude fallback for critical sample set fields
        required_ss = ["ticket_number", "sample_date", "placement_location"]
        combined = {**material, **sample_info}
        combined = _fill_missing_with_claude(combined, page_text, required_ss)

        sample_sets.append({
            "set_number": set_idx + 1,
            **{k: v for k, v in combined.items() if k in {
                "mix_id", "supplier", "batch_time", "truck_number", "plant",
                "ticket_number", "specified_strength_psi", "strength_age_days",
                "sample_date", "sample_time", "sampled_by", "weather_conditions",
                "accumulative_yards", "batch_size_cy", "placement_method",
                "water_added_before_gal", "water_added_after_gal",
                "sample_location", "placement_location", "sample_description",
                "initial_cure", "final_cure", "comments",
            }},
            **field_tests,
            "avg_28_day_strength_psi": avg_28,
            "cylinders": cylinders,
        })

    return {"header": header, "sample_sets": sample_sets}


def _group_pages_by_sample_set(pages: list) -> list[list]:
    """Group pages into sample sets. A new set starts when a new Ticket No. appears."""
    if not pages:
        return []

    groups = [[pages[0]]]
    seen_tickets = set()

    first_text = pages[0].extract_text() or ""
    m = re.search(r'Ticket\s+(?:No\.?|Number)[:\s]*([\w\-]+)', first_text, re.IGNORECASE)
    if m:
        seen_tickets.add(m.group(1).strip())

    for page in pages[1:]:
        page_text = page.extract_text() or ""
        m = re.search(r'Ticket\s+(?:No\.?|Number)[:\s]*([\w\-]+)', page_text, re.IGNORECASE)
        if m and m.group(1).strip() not in seen_tickets:
            seen_tickets.add(m.group(1).strip())
            groups.append([page])
        else:
            groups[-1].append(page)

    return groups


def _extract_cylinders_from_text(page_text: str) -> list[dict]:
    """Fallback: extract cylinder data from raw text lines."""
    cylinders = []
    lines = page_text.split("\n")

    for line in lines:
        # Look for lines that start with a set number and spec id pattern
        m = re.match(
            r'^\s*(\d+)\s+([A-E])\s+(\w+)\s+([\d.]+)\s+([\d.]+)\s+'
            r'([\d/]+)\s+([\d/]+)\s+(\d+)\s+([\d,]+)\s+([\d,]+)\s+(\w+)',
            line,
        )
        if m:
            cylinders.append({
                "spec_id": m.group(2),
                "cylinder_condition": m.group(3),
                "avg_diameter_in": _to_float(m.group(4)),
                "area_sq_in": _to_float(m.group(5)),
                "date_received": _parse_date(m.group(6)),
                "date_tested": _parse_date(m.group(7)),
                "age_at_test_days": _to_int(m.group(8)),
                "max_load_lbs": _to_float(m.group(9)),
                "comp_strength_psi": _to_float(m.group(10)),
                "frac_type": m.group(11),
                "tested_by": None,
            })
    return cylinders


def extract_raw_text(pdf_bytes: bytes) -> tuple[str, list]:
    """Open PDF bytes and return (full_text, pages_list)."""
    import io
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = pdf.pages
        full_text = "\n".join(p.extract_text() or "" for p in pages)
        return full_text, list(pages)

import json
import logging
import streamlit as st

logger = logging.getLogger(__name__)


def _ai_enabled() -> bool:
    key = st.secrets.get("ANTHROPIC_API_KEY", "")
    return bool(key and not key.startswith("sk-ant-..."))


def classify_with_claude(raw_text: str) -> dict:
    if not _ai_enabled():
        logger.info("AI classification skipped — no API key configured")
        return {}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
        truncated = raw_text[:4000]
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=(
                "You are a construction QA document classifier. Identify the type of test report "
                "from the provided text. Respond with JSON only: "
                '{\"report_type\": string, \"confidence\": float}. '
                "Valid types: concrete_compressive_strength, concrete_core_test, "
                "grout_compressive_strength, post_tension_stressing, field_density, unknown."
            ),
            messages=[{"role": "user", "content": truncated}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        logger.error(f"Claude classify error: {e}")
        return {}


def extract_fields(page_text: str, field_names: list[str]) -> dict:
    if not field_names or not _ai_enabled():
        return {}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
        logger.info(f"Using Claude to extract fields: {field_names}")
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=(
                "You are a construction report data extractor. Extract the specified fields from "
                "the provided report text. Respond with JSON only, using null for fields you "
                f"cannot find. Field names: {field_names}"
            ),
            messages=[{"role": "user", "content": page_text[:4000]}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        logger.error(f"Claude extract_fields error: {e}")
        return {}

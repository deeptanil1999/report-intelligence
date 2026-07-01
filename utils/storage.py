import streamlit as st
from utils.auth import init_supabase_service


def get_bucket() -> str:
    return st.secrets.get("PDF_BUCKET", "reports")


def upload_pdf(file_bytes: bytes, storage_path: str) -> str:
    supabase = init_supabase_service()
    bucket = get_bucket()
    supabase.storage.from_(bucket).upload(
        storage_path,
        file_bytes,
        {"content-type": "application/pdf", "upsert": "true"},
    )
    return storage_path


def get_signed_url(path: str, expires_in: int = 3600) -> str:
    supabase = init_supabase_service()
    bucket = get_bucket()
    res = supabase.storage.from_(bucket).create_signed_url(path, expires_in)
    return res.get("signedURL") or res.get("signed_url") or ""


def delete_file(path: str):
    supabase = init_supabase_service()
    bucket = get_bucket()
    supabase.storage.from_(bucket).remove([path])

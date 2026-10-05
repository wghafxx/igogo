"""Validate the Roblox contact details required before creating a top-up."""
import re
from urllib.parse import urlsplit, parse_qs

from fastapi import HTTPException


def valid_profile_link(value):
    try:
        url = urlsplit(value)
        if url.scheme != "https" or url.netloc not in ("roblox.com", "www.roblox.com"):
            return False
        if re.fullmatch(r"/users/[1-9]\d*/profile/?", url.path):
            return True
        query = parse_qs(url.query)
        return (url.path == "/share" and query.get("type") == ["Profile"]
                and bool(re.fullmatch(r"[A-Za-z0-9]+", query.get("code", [""])[0])))
    except (ValueError, TypeError):
        return False


def profile_fields(display_name, username, link):
    display_name, username, link = display_name.strip(), username.strip().removeprefix("@"), link.strip()
    if not 3 <= len(display_name) <= 20 or re.search(r"[\x00-\x1f\x7f]", display_name):
        raise HTTPException(400, "Display Name Roblox: от 3 до 20 символов")
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username):
        raise HTTPException(400, "Имя пользователя Roblox: 3–20 латинских букв, цифр или символов подчёркивания")
    if not valid_profile_link(link):
        raise HTTPException(400, "Укажите ссылку на профиль Roblox: https://www.roblox.com/users/123/profile или ссылку «Поделиться профилем»")
    return {"roblox_display_name": display_name, "roblox_nick": username, "roblox_link": link}


def require_roblox_profile(user):
    try:
        profile_fields(user.get("roblox_display_name") or "", user.get("roblox_nick") or "", user.get("roblox_link") or "")
    except HTTPException:
        raise HTTPException(400, "Перед пополнением привяжите Roblox: Display Name, @username и ссылку на профиль") from None

"""Dane wspólne dla wszystkich szablonów."""

# Nazwy widoków, które należą do sekcji innej niż wynika z prefiksu nazwy.
_SECTION_OVERRIDES = {
    "home": "home",
    "report_dashboard": "report",
    "field_report": "report",
    "cultivation_report": "report",
    "password_change": "profile",
    "profile_edit": "profile",
}


def nav_section(request):
    """Zwraca sekcję menu, do której należy bieżąca strona (do podświetlenia linku)."""
    match = getattr(request, "resolver_match", None)
    name = match.url_name if match else None
    if not name:
        return {"nav_section": ""}
    if name in _SECTION_OVERRIDES:
        section = _SECTION_OVERRIDES[name]
    elif name.startswith("error_report"):
        section = "profile"
    else:
        section = name.split("_", 1)[0]
    return {"nav_section": section}

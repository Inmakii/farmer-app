"""Data shared by all templates."""

# View names that belong to a different section than their name prefix suggests.
_SECTION_OVERRIDES = {
    "home": "home",
    "report_dashboard": "report",
    "field_report": "report",
    "cultivation_report": "report",
    "password_change": "profile",
    "profile_edit": "profile",
}


def nav_section(request):
    """Return the menu section of the current page, used to highlight its link."""
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

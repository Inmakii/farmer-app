import re
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Crop, Cultivation, Field

TOGGLE_ID = 'id="theme-toggle"'
DARK_LABEL = "Włącz tryb ciemny"
LIGHT_LABEL = "Włącz tryb jasny"
THEME_FILES = ["core/theme-init.js", "core/theme.js", "core/styles.css"]
TEMPLATES_DIR = Path(settings.BASE_DIR) / "core" / "templates"


def read_static(path):
    return Path(finders.find(path)).read_text(encoding="utf-8")


class ThemeToggleMarkupTests(TestCase):
    def assert_toggle_present(self, response):
        content = response.content.decode()
        match = re.search(r"<button[^>]*" + TOGGLE_ID + r"[^>]*>", content)
        self.assertIsNotNone(match, "Brak przełącznika motywu.")
        button = match.group(0)
        self.assertIn('type="button"', button)
        self.assertIn(f'aria-label="{DARK_LABEL}"', button)
        self.assertIn(f'title="{DARK_LABEL}"', button)
        self.assertIn('id="theme-status"', content)
        self.assertIn('aria-live="polite"', content)

    def test_toggle_present_for_anonymous_user(self):
        for name in ["core:login", "core:register"]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))

                self.assertEqual(response.status_code, 200)
                self.assert_toggle_present(response)

    def test_toggle_present_for_logged_in_user(self):
        user = get_user_model().objects.create_user(
            username="theme_user", password="StrongPass!2026"
        )
        self.client.force_login(user)

        response = self.client.get(reverse("core:field_list"))

        self.assert_toggle_present(response)

    def test_toggle_is_in_navigation_outside_logout_form(self):
        user = get_user_model().objects.create_user(
            username="theme_form", password="StrongPass!2026"
        )
        self.client.force_login(user)
        content = self.client.get(reverse("core:field_list")).content.decode()

        nav = re.search(
            r'<nav class="main-nav"[^>]*>(.*?)</nav>', content, re.DOTALL
        ).group(1)
        logout_form = re.search(r"<form.*?</form>", nav, re.DOTALL).group(0)
        self.assertIn(TOGGLE_ID, nav)
        self.assertNotIn(TOGGLE_ID, logout_form)

    def test_icons_are_hidden_from_assistive_technology(self):
        content = self.client.get(reverse("core:login")).content.decode()

        for icon in ["theme-icon-moon", "theme-icon-sun"]:
            with self.subTest(icon=icon):
                svg = re.search(r'<svg class="theme-icon ' + icon + '"[^>]*>', content)
                self.assertIsNotNone(svg)
                self.assertIn('aria-hidden="true"', svg.group(0))

    def test_theme_assets_are_included_in_correct_order(self):
        content = self.client.get(reverse("core:login")).content.decode()
        head = content.split("</head>")[0]

        init_tag = '<script src="/static/core/theme-init.js"></script>'
        css_tag = '<link rel="stylesheet" href="/static/core/styles.css">'
        toggle_tag = '<script src="/static/core/theme.js" defer></script>'
        for tag in [init_tag, css_tag, toggle_tag]:
            with self.subTest(tag=tag):
                self.assertIn(tag, head)
        self.assertLess(head.index(init_tag), head.index(css_tag))

    def test_existing_navigation_links_are_kept(self):
        user = get_user_model().objects.create_user(
            username="theme_nav", password="StrongPass!2026"
        )
        self.client.force_login(user)

        response = self.client.get(reverse("core:field_list"))

        for name in [
            "core:profile",
            "core:field_list",
            "core:cultivation_list",
            "core:crop_list",
            "core:fieldwork_list",
            "core:spraying_list",
            "core:harvest_list",
            "core:report_dashboard",
            "core:error_report_create",
            "core:logout",
        ]:
            with self.subTest(name=name):
                self.assertContains(response, f'"{reverse(name)}"')

    def test_admin_is_not_themed(self):
        admin = get_user_model().objects.create_superuser(
            username="theme_admin", password="StrongPass!2026", email="a@example.com"
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, TOGGLE_ID)
        self.assertNotContains(response, "theme-init.js")


class ThemePagesRenderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="theme_pages", password="StrongPass!2026"
        )
        self.field = Field.objects.create(
            owner=self.user,
            name="Pole Motywu",
            area_ha="2.00",
            soil_type=Field.SoilType.LOAMY,
            location_method=Field.LocationMethod.ADDRESS,
            address="Gdańsk",
        )
        crop = Crop.objects.create(name="Owies motywowy")
        self.cultivation = Cultivation.objects.create(
            field=self.field,
            crop=crop,
            season_year=2026,
            status=Cultivation.Status.ACTIVE,
        )

    def test_user_pages_render_with_toggle(self):
        self.client.force_login(self.user)
        urls = [
            reverse("core:profile"),
            reverse("core:profile_edit"),
            reverse("core:password_change"),
            reverse("core:field_list"),
            reverse("core:field_create"),
            reverse("core:field_detail", kwargs={"pk": self.field.pk}),
            reverse("core:cultivation_list"),
            reverse("core:cultivation_create"),
            reverse("core:cultivation_detail", kwargs={"pk": self.cultivation.pk}),
            reverse("core:fieldwork_list"),
            reverse("core:fieldwork_create"),
            reverse("core:spraying_list"),
            reverse("core:spraying_create"),
            reverse("core:harvest_list"),
            reverse("core:harvest_create"),
            reverse("core:report_dashboard"),
            reverse("core:field_report", kwargs={"pk": self.field.pk}),
            reverse(
                "core:cultivation_report", kwargs={"pk": self.cultivation.pk}
            ),
            reverse("core:error_report_list"),
            reverse("core:error_report_create"),
            reverse("core:crop_list"),
            reverse("core:crop_create"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, TOGGLE_ID, count=1)


class ThemeStaticFilesTests(SimpleTestCase):
    def test_theme_static_files_exist(self):
        for path in THEME_FILES:
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path), path)

    def test_all_static_references_in_templates_resolve(self):
        pattern = re.compile(r"""{%\s*static\s+['"]([^'"]+)['"]\s*%}""")
        references = set()
        for template in TEMPLATES_DIR.rglob("*.html"):
            references.update(pattern.findall(template.read_text(encoding="utf-8")))

        self.assertTrue(references)
        for path in sorted(references):
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path), path)

    def test_scripts_have_polish_labels_and_safe_storage_access(self):
        init_script = read_static("core/theme-init.js")
        toggle_script = read_static("core/theme.js")

        self.assertIn(DARK_LABEL, toggle_script)
        self.assertIn(LIGHT_LABEL, toggle_script)
        for script in [init_script, toggle_script]:
            with self.subTest(script=script[:40]):
                self.assertIn('"farmer-theme"', script)
                self.assertIn("try {", script)
                self.assertIn("prefers-color-scheme: dark", script)
                self.assertIn('=== "light" || ', script)

    def test_stylesheet_defines_both_themes(self):
        css = read_static("core/styles.css")

        self.assertIn(':root[data-theme="dark"]', css)
        self.assertIn("color-scheme: light;", css)
        self.assertIn("color-scheme: dark;", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn(".theme-toggle", css)


def _css_tokens(css, selector):
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", css, re.DOTALL)
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", block.group(1)))


def _resolve_hex(tokens, name):
    value = tokens[name].strip()
    while value.startswith("var("):
        value = tokens[value[4:-1].strip()].strip()
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    return [int(value[i:i + 2], 16) for i in (0, 2, 4)]


def _contrast(first, second):
    def luminance(rgb):
        channels = []
        for value in rgb:
            value /= 255
            channels.append(
                value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
            )
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    high, low = sorted([luminance(first), luminance(second)], reverse=True)
    return (high + 0.05) / (low + 0.05)


class ThemeContrastTests(SimpleTestCase):
    NON_TEXT_PAIRS = [
        ("--input-border", "--input-bg"),
        ("--input-border", "--surface"),
        ("--input-border", "--page-bg"),
        ("--input-focus-border", "--input-bg"),
        ("--button-border", "--surface"),
        ("--button-border", "--page-bg"),
        ("--button-hover-border", "--surface"),
        ("--button-hover-border", "--page-bg"),
        ("--focus-outline", "--surface"),
        ("--focus-outline", "--page-bg"),
    ]
    TEXT_PAIRS = [
        ("--text", "--surface"),
        ("--text", "--page-bg"),
        ("--text", "--input-bg"),
        ("--muted", "--surface"),
        ("--muted", "--page-bg"),
        ("--link", "--surface"),
        ("--link", "--page-bg"),
        ("--button-text", "--button-bg"),
        ("--button-text", "--button-hover-bg"),
        ("--error-text", "--error-bg"),
        ("--success-text", "--success-bg"),
        ("--warning-text", "--warning-bg"),
    ]

    def setUp(self):
        css = read_static("core/styles.css")
        light = _css_tokens(css, ":root")
        dark = {**light, **_css_tokens(css, ':root[data-theme="dark"]')}
        self.themes = {"light": light, "dark": dark}

    def assert_pairs(self, pairs, minimum):
        for theme, tokens in self.themes.items():
            for foreground, background in pairs:
                with self.subTest(theme=theme, pair=(foreground, background)):
                    ratio = _contrast(
                        _resolve_hex(tokens, foreground),
                        _resolve_hex(tokens, background),
                    )
                    self.assertGreaterEqual(round(ratio, 2), minimum)

    def test_borders_and_focus_meet_non_text_contrast(self):
        self.assert_pairs(self.NON_TEXT_PAIRS, 3.0)

    def test_text_meets_normal_text_contrast(self):
        self.assert_pairs(self.TEXT_PAIRS, 4.5)


class ThemeJavaScriptSyntaxTests(SimpleTestCase):
    def test_javascript_syntax_with_node(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js nie jest dostępny.")
        for path in ["core/theme-init.js", "core/theme.js"]:
            with self.subTest(path=path):
                result = subprocess.run(
                    [node, "--check", finders.find(path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                self.assertEqual(result.returncode, 0, result.stderr)

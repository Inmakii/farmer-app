import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ..forms import ATTACHMENT_MAX_SIZE
from ..models import ErrorReport, ErrorReportAttachment

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"0" * 64


def upload(name, content, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class ErrorReportAttachmentTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media)
        self.settings_override.enable()
        users = get_user_model()
        self.user = users.objects.create_user(username="reporter", password="StrongPass!2026")
        self.other = users.objects.create_user(username="stranger", password="StrongPass!2026")
        self.client.force_login(self.user)

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def send(self, *files, **extra):
        data = {
            "category": ErrorReport.Category.INTERFACE,
            "description": "Przycisk zapisu nie reaguje na kliknięcie.",
            "attachments": list(files),
        }
        data.update(extra)
        return self.client.post(reverse("core:error_report_create"), data)

    def test_form_accepts_screenshots_and_pdf(self):
        response = self.client.get(reverse("core:error_report_create"))
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'type="file" name="attachments"')
        self.assertContains(response, "multiple")

    def test_report_is_saved_with_its_files(self):
        response = self.send(upload("ekran.png", PNG, "image/png"), upload("faktura.pdf", PDF))
        report = ErrorReport.objects.get(user=self.user)
        self.assertRedirects(response, reverse("core:error_report_detail", args=[report.pk]))
        attachments = list(report.attachments.order_by("original_name"))
        self.assertEqual([a.original_name for a in attachments], ["ekran.png", "faktura.pdf"])
        self.assertEqual([a.content_type for a in attachments], ["image/png", "application/pdf"])
        for attachment in attachments:
            stored = Path(attachment.file.path)
            self.assertTrue(stored.is_file())
            # The user's file name is not used on disk.
            self.assertNotIn("ekran", stored.name)
            self.assertNotIn("faktura", stored.name)

    def test_report_without_files_still_works(self):
        self.send()
        self.assertFalse(ErrorReportAttachment.objects.exists())
        self.assertTrue(ErrorReport.objects.filter(user=self.user).exists())

    def test_file_content_must_match_an_allowed_type(self):
        cases = {
            "script disguised as an image": upload("ekran.png", b"<script>alert(1)</script>"),
            "png content with pdf name": upload("raport.pdf", PNG),
            "svg image": upload("rysunek.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>"),
            "program": upload("setup.exe", b"MZ" + b"\x00" * 64),
        }
        for case, uploaded in cases.items():
            with self.subTest(case=case):
                response = self.send(uploaded)
                self.assertEqual(response.status_code, 200)
                self.assertIn("attachments", response.context["form"].errors)
        self.assertFalse(ErrorReport.objects.exists())

    def test_at_most_three_files(self):
        response = self.send(*(upload(f"ekran{i}.png", PNG) for i in range(4)))
        self.assertIn("attachments", response.context["form"].errors)
        self.assertFalse(ErrorReport.objects.exists())

    def test_files_over_the_size_limit_are_rejected(self):
        big = upload("duzy.pdf", PDF + b"0" * ATTACHMENT_MAX_SIZE)
        response = self.send(big)
        self.assertIn("attachments", response.context["form"].errors)

    def create_with_files(self):
        self.send(upload("ekran.jpg", JPEG), upload("raport.pdf", PDF))
        report = ErrorReport.objects.get(user=self.user)
        image = report.attachments.get(content_type="image/jpeg")
        pdf = report.attachments.get(content_type="application/pdf")
        return report, image, pdf

    def test_author_sees_files_on_the_report_page(self):
        report, image, pdf = self.create_with_files()
        response = self.client.get(reverse("core:error_report_detail", args=[report.pk]))
        image_url = reverse("core:error_report_attachment", args=[image.pk])
        self.assertContains(response, f'<img src="{image_url}"')
        self.assertContains(response, reverse("core:error_report_attachment", args=[pdf.pk]))

    def test_author_opens_image_and_downloads_pdf(self):
        _report, image, pdf = self.create_with_files()
        response = self.client.get(reverse("core:error_report_attachment", args=[image.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertTrue(response["Content-Disposition"].startswith("inline"))
        self.assertEqual(b"".join(response.streaming_content), JPEG)
        response = self.client.get(reverse("core:error_report_attachment", args=[pdf.pk]))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))

    def test_other_users_cannot_open_files(self):
        _report, image, _pdf = self.create_with_files()
        url = reverse("core:error_report_attachment", args=[image.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertRedirects(self.client.get(url), f"{reverse('core:login')}?next={url}")

    def test_staff_with_report_permission_can_open_files(self):
        _report, image, _pdf = self.create_with_files()
        url = reverse("core:error_report_attachment", args=[image.pk])
        staff = get_user_model().objects.create_user(
            username="helper", password="StrongPass!2026", is_staff=True
        )
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 404)
        staff.user_permissions.add(Permission.objects.get(codename="view_errorreport"))
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_admin_page_shows_page_and_files(self):
        report, image, _pdf = self.create_with_files()
        report.page = "/fields/"
        report.save()
        admin_user = get_user_model().objects.create_superuser(
            username="boss", password="StrongPass!2026"
        )
        self.client.force_login(admin_user)
        response = self.client.get(reverse("admin:core_errorreport_change", args=[report.pk]))
        self.assertContains(response, "/fields/")
        self.assertContains(response, 'class="fa-preview"')
        self.assertContains(response, reverse("core:error_report_attachment", args=[image.pk]))

    def test_deleting_a_report_removes_its_files(self):
        report, image, pdf = self.create_with_files()
        paths = [Path(image.file.path), Path(pdf.file.path)]
        report.delete()
        for path in paths:
            self.assertFalse(path.exists())

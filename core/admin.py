from django.contrib import admin, messages
from django.db.models import Count
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import number_format
from django.utils.html import format_html
from django.utils.text import Truncator
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from .models import (
    Crop,
    Cultivation,
    ErrorReport,
    ErrorReportAttachment,
    Field,
    FieldWork,
    Harvest,
    Spraying,
)

admin.site.site_header = _("Farmer App – administration")
admin.site.site_title = _("Farmer App administration")
admin.site.index_title = _("Farm data and user reports")
admin.site.empty_value_display = "—"


def money(value):
    return format_html(
        '<span class="fa-money">{}&nbsp;zł</span>', number_format(value, 2, force_grouping=True)
    )


def two_lines(main, sub=""):
    """A list cell with the main value and a quieter second line under it."""
    if not sub:
        return format_html('<span class="fa-main">{}</span>', main)
    return format_html('<span class="fa-main">{}</span><span class="fa-sub">{}</span>', main, sub)


def badge(value, label):
    """Coloured label for a status or category; the colour comes from admin.css."""
    return format_html('<span class="fa-badge fa-badge-{}">{}</span>', value.lower(), label)


# Related records shown on the parent's page. They are edited on their own pages,
# so these lists only link to them.
class ReadOnlyInline(admin.TabularInline):
    template = "admin/edit_inline/fa_records.html"
    extra = 0
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Crop)
class CropAdmin(admin.ModelAdmin):
    list_display = ("name", "cultivation_count", "created_at")
    search_fields = ("name", "description")
    list_filter = ("created_at",)
    readonly_fields = ("created_at",)
    fieldsets = ((_("Basic information"), {"fields": ("name", "description")}),)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(cultivation_total=Count("cultivations"))

    @admin.display(description=_("cultivations"), ordering="cultivation_total")
    def cultivation_count(self, crop):
        return crop.cultivation_total


class FieldCultivationInline(ReadOnlyInline):
    model = Cultivation
    fields = ("season_year", "crop", "status", "sowing_date", "planned_harvest_date")
    readonly_fields = fields
    ordering = ("-season_year",)


@admin.register(Field)
class FieldAdmin(admin.ModelAdmin):
    list_display = ("field_name", "owner", "soil_type", "area", "cultivation_count")
    list_display_links = ("field_name",)
    list_select_related = ("owner",)
    search_fields = ("name", "owner__username", "parcel_identifier", "address")
    list_filter = ("soil_type", "location_method", "created_at")
    autocomplete_fields = ("owner",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (FieldCultivationInline,)
    fieldsets = (
        (_("Basic information"), {
            "fields": ("owner", "name", ("area_ha", "soil_type"), "description"),
        }),
        (_("Location"), {
            "description": _("Choose how the field is found, then fill in the matching data: "
                             "an address, a parcel identifier or coordinates."),
            "fields": ("location_method", "address", "parcel_identifier", ("latitude", "longitude")),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(cultivation_total=Count("cultivations"))

    @admin.display(description=_("name"), ordering="name")
    def field_name(self, field):
        if field.location_method == Field.LocationMethod.ADDRESS:
            place = field.address
        elif field.location_method == Field.LocationMethod.PARCEL:
            place = field.parcel_identifier
        elif field.latitude is not None and field.longitude is not None:
            place = f"{number_format(field.latitude, 4)}, {number_format(field.longitude, 4)}"
        else:
            place = ""
        method = field.get_location_method_display()
        return two_lines(field.name, f"{method}: {place}" if place else method)

    @admin.display(description=_("area (ha)"), ordering="area_ha")
    def area(self, field):
        return format_html("{}&nbsp;ha", number_format(field.area_ha, 2, force_grouping=True))

    @admin.display(description=_("cultivations"), ordering="cultivation_total")
    def cultivation_count(self, field):
        return field.cultivation_total


class CultivationWorkInline(ReadOnlyInline):
    model = FieldWork
    fields = ("work_date", "work_type", "cost")
    readonly_fields = fields


class CultivationSprayingInline(ReadOnlyInline):
    model = Spraying
    fields = ("spraying_date", "product_name", "quantity", "unit", "cost")
    readonly_fields = fields


class CultivationHarvestInline(ReadOnlyInline):
    model = Harvest
    fields = ("harvest_date", "quantity", "unit", "disposition", "revenue", "harvest_cost")
    readonly_fields = fields


@admin.register(Cultivation)
class CultivationAdmin(admin.ModelAdmin):
    list_display = ("crop_cell", "field_owner", "season_year", "status_badge", "sowing_date",
                    "planned_harvest_date")
    list_display_links = ("crop_cell",)
    list_select_related = ("field__owner", "crop")
    search_fields = ("field__name", "crop__name", "notes", "field__owner__username")
    list_filter = ("status", "season_year", "crop")
    autocomplete_fields = ("field", "crop")
    readonly_fields = ("created_at",)
    inlines = (CultivationWorkInline, CultivationSprayingInline, CultivationHarvestInline)
    fieldsets = (
        (_("Basic information"), {"fields": (("field", "crop"), ("season_year", "status"))}),
        (_("Dates"), {
            "description": _("The sowing date must fall in the season year."),
            "fields": (("sowing_date", "planned_harvest_date"),),
        }),
        (_("Notes"), {"fields": ("notes",)}),
    )

    @admin.display(description=_("crop type"), ordering="crop__name")
    def crop_cell(self, cultivation):
        return two_lines(cultivation.crop.name, cultivation.field.name)

    @admin.display(description=_("owner"), ordering="field__owner__username")
    def field_owner(self, cultivation):
        return cultivation.field.owner

    @admin.display(description=_("status"), ordering="status")
    def status_badge(self, cultivation):
        return badge(cultivation.status, cultivation.get_status_display())


class CultivationRecordAdmin(admin.ModelAdmin):
    """Shared settings for works, sprayings and harvests, which all belong to a cultivation."""

    list_select_related = ("cultivation__field__owner", "cultivation__crop")
    autocomplete_fields = ("cultivation",)
    readonly_fields = ("created_at",)

    @admin.display(description=_("cultivation"), ordering="cultivation__field__name")
    def cultivation_cell(self, record):
        cultivation = record.cultivation
        return two_lines(cultivation.field.name,
                         f"{cultivation.crop.name} · {cultivation.season_year}")

    @admin.display(description=_("owner"), ordering="cultivation__field__owner__username")
    def owner(self, record):
        return record.cultivation.field.owner


@admin.register(FieldWork)
class FieldWorkAdmin(CultivationRecordAdmin):
    list_display = ("work_date", "work_type", "cultivation_cell", "owner", "cost_display")
    search_fields = ("cultivation__field__name", "cultivation__crop__name", "description")
    list_filter = ("work_type", "work_date")
    date_hierarchy = "work_date"
    fieldsets = (
        (_("Basic information"), {"fields": ("cultivation", ("work_type", "work_date"))}),
        (_("Cost and notes"), {"fields": ("cost", "description")}),
    )

    @admin.display(description=_("cost"), ordering="cost")
    def cost_display(self, work):
        return money(work.cost)


@admin.register(Spraying)
class SprayingAdmin(CultivationRecordAdmin):
    list_display = ("spraying_date", "product_name", "cultivation_cell", "dose", "cost_display")
    search_fields = ("product_name", "cultivation__field__name", "description")
    list_filter = ("unit", "spraying_date")
    date_hierarchy = "spraying_date"
    fieldsets = (
        (_("Basic information"), {"fields": ("cultivation", ("spraying_date", "product_name"))}),
        (_("Dose and cost"), {"fields": (("quantity", "unit"), "cost", "description")}),
    )

    @admin.display(description=_("quantity"), ordering="quantity")
    def dose(self, spraying):
        return f"{number_format(spraying.quantity, 2)} {spraying.get_unit_display()}"

    @admin.display(description=_("cost"), ordering="cost")
    def cost_display(self, spraying):
        return money(spraying.cost)


@admin.register(Harvest)
class HarvestAdmin(CultivationRecordAdmin):
    list_display = ("harvest_date", "cultivation_cell", "amount", "disposition_badge",
                    "revenue_display", "cost_display", "profit_display")
    search_fields = ("cultivation__field__name", "cultivation__crop__name", "notes")
    list_filter = ("disposition", "unit", "harvest_date")
    date_hierarchy = "harvest_date"
    fieldsets = (
        (_("Basic information"), {
            "fields": ("cultivation", ("harvest_date", "disposition"), ("quantity", "unit")),
        }),
        (_("Money"), {
            "description": _("Revenue stays 0 when the harvest was not sold."),
            "fields": (("revenue", "harvest_cost"),),
        }),
        (_("Notes"), {"fields": ("notes",)}),
    )

    @admin.display(description=_("quantity"), ordering="quantity")
    def amount(self, harvest):
        return f"{number_format(harvest.quantity, 2)} {harvest.get_unit_display()}"

    @admin.display(description=_("harvest disposition"), ordering="disposition")
    def disposition_badge(self, harvest):
        return badge(harvest.disposition, harvest.get_disposition_display())

    @admin.display(description=_("revenue"), ordering="revenue")
    def revenue_display(self, harvest):
        return money(harvest.revenue)

    @admin.display(description=_("harvest cost"), ordering="harvest_cost")
    def cost_display(self, harvest):
        return money(harvest.harvest_cost)

    @admin.display(description=_("profit"))
    def profit_display(self, harvest):
        css = "fa-loss" if harvest.profit < 0 else "fa-gain"
        return format_html('<strong class="{}">{}</strong>', css, money(harvest.profit))


class ErrorReportAttachmentInline(ReadOnlyInline):
    model = ErrorReportAttachment
    fields = ("preview", "original_name", "file_size")
    readonly_fields = fields

    @admin.display(description=_("preview"))
    def preview(self, attachment):
        url = reverse("core:error_report_attachment", args=[attachment.pk])
        if attachment.is_image:
            return format_html(
                '<a class="fa-preview" href="{}" target="_blank" rel="noopener">'
                '<img src="{}" alt="{}" loading="lazy"></a>',
                url, url, attachment.original_name,
            )
        return format_html('<a href="{}">{}</a>', url, gettext("Download PDF"))

    @admin.display(description=_("size"))
    def file_size(self, attachment):
        return filesizeformat(attachment.size)


@admin.register(ErrorReport)
class ErrorReportAdmin(admin.ModelAdmin):
    list_display = (
        "__str__", "user", "category_badge", "status_badge", "short_description", "created_at",
    )
    list_display_links = ("__str__",)
    list_select_related = ("user",)
    search_fields = ("user__username", "user__email", "description")
    list_filter = ("status", "category", "created_at")
    readonly_fields = ("page", "created_at", "updated_at")
    actions = ("mark_in_progress", "mark_resolved")
    inlines = (ErrorReportAttachmentInline,)
    fieldsets = (
        (_("Report"), {"fields": ("user", ("category", "status"), "page")}),
        (_("What the user wrote"), {"fields": ("description",)}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly_fields.append("user")
        return readonly_fields

    @admin.display(description=_("category"), ordering="category")
    def category_badge(self, report):
        return badge(report.category, report.get_category_display())

    @admin.display(description=_("status"), ordering="status")
    def status_badge(self, report):
        return badge(report.status, report.get_status_display())

    @admin.display(description=_("description"))
    def short_description(self, report):
        return Truncator(report.description).chars(80)

    def update_status(self, request, queryset, status):
        # update() skips auto_now, so the change time is set explicitly.
        updated = queryset.exclude(status=status).update(status=status, updated_at=timezone.now())
        self.message_user(
            request,
            gettext("Reports updated: %(count)s") % {"count": updated},
            messages.SUCCESS,
        )

    @admin.action(description=_("Mark selected reports as in progress"))
    def mark_in_progress(self, request, queryset):
        self.update_status(request, queryset, ErrorReport.Status.IN_PROGRESS)

    @admin.action(description=_("Mark selected reports as resolved"))
    def mark_resolved(self, request, queryset):
        self.update_status(request, queryset, ErrorReport.Status.RESOLVED)

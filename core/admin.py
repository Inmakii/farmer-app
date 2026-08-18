from django.contrib import admin

from .models import Crop, Cultivation, ErrorReport, Field, FieldWork, Harvest, Spraying


@admin.register(Crop)
class CropAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name", "description")
    list_filter = ("created_at",)


@admin.register(Field)
class FieldAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "area_ha", "soil_type", "location_method")
    search_fields = ("name", "owner__username", "parcel_identifier", "address")
    list_filter = ("soil_type", "location_method", "created_at")


@admin.register(Cultivation)
class CultivationAdmin(admin.ModelAdmin):
    list_display = ("field", "crop", "season_year", "status", "sowing_date")
    search_fields = ("field__name", "crop__name", "notes")
    list_filter = ("status", "season_year", "crop")


@admin.register(FieldWork)
class FieldWorkAdmin(admin.ModelAdmin):
    list_display = ("cultivation", "work_type", "work_date", "cost")
    search_fields = ("cultivation__field__name", "cultivation__crop__name", "description")
    list_filter = ("work_type", "work_date")


@admin.register(Spraying)
class SprayingAdmin(admin.ModelAdmin):
    list_display = (
        "product_name", "cultivation", "spraying_date", "quantity", "unit", "cost"
    )
    search_fields = ("product_name", "cultivation__field__name", "description")
    list_filter = ("unit", "spraying_date")


@admin.register(Harvest)
class HarvestAdmin(admin.ModelAdmin):
    list_display = (
        "cultivation", "harvest_date", "quantity", "unit", "revenue", "harvest_cost"
    )
    search_fields = ("cultivation__field__name", "cultivation__crop__name", "notes")
    list_filter = ("unit", "harvest_date")


@admin.register(ErrorReport)
class ErrorReportAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "status", "created_at", "updated_at")
    search_fields = ("user__username", "user__email", "description")
    list_filter = ("category", "status", "created_at")
    list_editable = ("status",)

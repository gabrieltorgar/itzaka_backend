"""Admin registration for accounts (Unfold)."""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.accounts.models import Organization, OtpCode, Subscription, User

admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    """Los grupos de Django con la apariencia del admin."""


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    """Cuentas por correo: sin nombre de usuario, con su verificación."""

    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    ordering = ("email",)
    list_display = ("email", "is_email_verified", "is_active", "is_staff", "created_at")
    list_filter = ("is_email_verified", "is_active", "is_staff")
    search_fields = ("email",)
    readonly_fields = ("created_at", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Verificación"), {"fields": ("is_email_verified", "pending_email")}),
        (
            _("Permisos"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Fechas"), {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = ("user", "plan", "status", "created_at")
    list_select_related = ("user",)


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = ("user", "name", "email", "phone", "color", "updated_at")
    search_fields = ("name", "email", "user__email")
    list_select_related = ("user",)


@admin.register(OtpCode)
class OtpCodeAdmin(ModelAdmin):
    list_display = (
        "user",
        "purpose",
        "expires_at",
        "used_at",
        "attempts",
        "created_at",
    )
    list_filter = ("purpose",)
    list_select_related = ("user",)
    # Sólo el hash del código vive aquí; no se edita a mano.
    readonly_fields = (
        "user",
        "purpose",
        "code_hash",
        "expires_at",
        "used_at",
        "attempts",
    )

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import ModelForm

from .models import Command, Terminal
from .services import enqueue, validate_enqueue_payload


class CommandInline(admin.TabularInline):
    model = Command
    extra = 0
    fields = ("command_id", "type", "status", "issued_at", "expires_at", "payload", "result")
    readonly_fields = ("command_id", "issued_at", "status", "result")
    can_delete = False


@admin.register(Terminal)
class TerminalAdmin(admin.ModelAdmin):
    list_display = ("serial_number", "terminal_id", "vendor", "model", "heartbeat_summary")
    search_fields = ("serial_number", "terminal_id")
    readonly_fields = ("terminal_id", "token", "identity", "last_heartbeat", "last_inventory")
    inlines = [CommandInline]

    @admin.display(description="vendor")
    def vendor(self, obj):
        return (obj.identity or {}).get("vendor", "-")

    @admin.display(description="model")
    def model(self, obj):
        return (obj.identity or {}).get("model", "-")

    @admin.display(description="last heartbeat")
    def heartbeat_summary(self, obj):
        hb = obj.last_heartbeat
        if not hb:
            return "-"
        return f"{hb.get('network', '?')} batt={hb.get('batteryPercent', '?')}"


class CommandAdminForm(ModelForm):
    class Meta:
        model = Command
        fields = ("terminal", "type", "payload", "expires_at")

    def clean(self):
        cleaned = super().clean()
        cmd_type = cleaned.get("type")
        payload = cleaned.get("payload") or {}
        err = validate_enqueue_payload(cmd_type, payload)
        if err:
            raise ValidationError(err)
        return cleaned


@admin.register(Command)
class CommandAdmin(admin.ModelAdmin):
    form = CommandAdminForm
    list_display = ("command_id", "terminal", "type", "status", "issued_at")
    list_filter = ("type", "status")
    readonly_fields = ("command_id", "issued_at", "status", "result")

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        cmd = enqueue(obj.terminal, obj.type, obj.payload, obj.expires_at or None)
        obj.pk = cmd.pk
        obj.command_id = cmd.command_id
        obj.issued_at = cmd.issued_at
        obj.expires_at = cmd.expires_at
        obj.status = cmd.status

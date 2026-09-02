import json
from datetime import timedelta

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.utils.html import format_html
from django.utils import timezone

from .models import Command, Terminal, TerminalEvent
from .services import (
    dt_to_ms,
    enqueue,
    format_expires_at,
    ms_to_dt,
    validate_enqueue_payload,
    validate_terminal_capability,
)


class CommandInline(admin.TabularInline):
    model = Command
    ordering = ("-issued_at", "-id")
    extra = 0
    fields = ("command_id", "type", "status", "expires_at_display", "payload", "result")
    readonly_fields = ("command_id", "status", "expires_at_display", "result")
    can_delete = False

    @admin.display(description="expires at")
    def expires_at_display(self, obj):
        return format_expires_at(obj.expires_at)


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
    expires_at_dt = forms.SplitDateTimeField(
        required=False,
        label="Expires at",
        help_text=(
            "Last moment the POS will run this command. "
            "Leave blank to use 24 hours after enqueue. "
            "After this time the agent reports failed / expired."
        ),
    )

    class Meta:
        model = Command
        fields = ("terminal", "type", "payload")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.expires_at:
            self.initial.setdefault("expires_at_dt", ms_to_dt(self.instance.expires_at))
        elif not self.instance.pk:
            self.initial.setdefault("expires_at_dt", timezone.now() + timedelta(hours=24))

    def clean(self):
        cleaned = super().clean()
        terminal = cleaned.get("terminal")
        cmd_type = cleaned.get("type")
        if terminal and cmd_type:
            cap_err = validate_terminal_capability(terminal, cmd_type)
            if cap_err:
                raise ValidationError(cap_err)
        payload = cleaned.get("payload") or {}
        err = validate_enqueue_payload(cmd_type, payload)
        if err:
            raise ValidationError(err)
        dt = cleaned.get("expires_at_dt")
        cleaned["_expires_at_ms"] = dt_to_ms(dt) if dt else None
        return cleaned


@admin.register(Command)
class CommandAdmin(admin.ModelAdmin):
    form = CommandAdminForm
    ordering = ("-issued_at", "-id")
    list_display = ("command_id", "terminal", "type", "status", "expires_at_display")
    list_filter = ("type", "status")
    readonly_fields = ("command_id", "issued_at", "status", "result", "expires_at_display", "terminal_events")

    @admin.display(description="expires at", ordering="expires_at")
    def expires_at_display(self, obj):
        return format_expires_at(obj.expires_at)

    @admin.display(description="terminal events")
    def terminal_events(self, obj):
        if not obj.pk:
            return "-"
        events = TerminalEvent.objects.filter(
            terminal=obj.terminal,
            command_id=obj.command_id,
        ).order_by("-event_at", "-id")
        if not events:
            return "-"
        lines = []
        for event in events:
            meta = json.dumps(event.meta, separators=(",", ":"))
            lines.append(
                f"{event.event_at} [{event.level}] {event.kind}: {event.message} meta={meta}"
            )
        return format_html("<pre>{}</pre>", "\n".join(lines))

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        cmd = enqueue(
            obj.terminal,
            obj.type,
            obj.payload,
            form.cleaned_data.get("_expires_at_ms"),
        )
        obj.pk = cmd.pk
        obj.command_id = cmd.command_id
        obj.issued_at = cmd.issued_at
        obj.expires_at = cmd.expires_at
        obj.status = cmd.status

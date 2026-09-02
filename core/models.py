import uuid

from django.db import models


class Terminal(models.Model):
    terminal_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    token = models.UUIDField(default=uuid.uuid4, editable=False)
    serial_number = models.CharField(max_length=255, unique=True)
    identity = models.JSONField(default=dict)
    last_heartbeat = models.JSONField(null=True, blank=True)
    last_inventory = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.serial_number} ({self.terminal_id})"


class Command(models.Model):
    command_id = models.CharField(max_length=64, unique=True)
    terminal = models.ForeignKey(Terminal, on_delete=models.CASCADE, related_name="commands")
    type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    issued_at = models.BigIntegerField()
    expires_at = models.BigIntegerField()
    status = models.CharField(max_length=32, default="pending")
    result = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["issued_at", "id"]

    def __str__(self):
        return f"{self.command_id} {self.type}"


class TerminalEvent(models.Model):
    terminal = models.ForeignKey(Terminal, on_delete=models.CASCADE, related_name="events")
    command_id = models.CharField(max_length=64, blank=True, default="")
    kind = models.CharField(max_length=64)
    level = models.CharField(max_length=16, default="info")
    message = models.TextField()
    meta = models.JSONField(default=dict)
    event_at = models.BigIntegerField()
    received_at = models.BigIntegerField()

    class Meta:
        ordering = ["event_at", "id"]

    def __str__(self):
        return f"{self.terminal.serial_number} {self.kind}"


class CommandSeq(models.Model):
    """ponytail: single-row counter for c-1, c-2 ids; upgrade: uuid if multi-process."""

    n = models.PositiveIntegerField(default=0)

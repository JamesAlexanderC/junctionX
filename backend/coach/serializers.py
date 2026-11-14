"""Request validation for the Saldo API (#64, #72, #54, P2.8)."""

from rest_framework import serializers

from . import services
from .models import Goal


class ChatRequest(serializers.Serializer):
    customer_id = serializers.CharField()
    message = serializers.CharField()
    history = serializers.ListField(child=serializers.DictField(), required=False)
    depth = serializers.IntegerField(min_value=1, max_value=4, required=False)


class GoalSerializer(serializers.ModelSerializer):
    """#64 form: amount > 0, date in the future."""

    amount = serializers.FloatField(source="target")
    date = serializers.DateField(source="target_date")

    class Meta:
        model = Goal
        fields = [
            "id",
            "customer_id",
            "name",
            "emoji",
            "type",
            "amount",
            "saved",
            "date",
            "priority",
            "paused",
            "status",
        ]
        read_only_fields = ["id"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value

    def validate_date(self, value):
        if value <= services.today():
            raise serializers.ValidationError("Date must be in the future.")
        return value

    def validate_customer_id(self, value):
        if self.instance is not None and value != self.instance.customer_id:
            raise serializers.ValidationError("customer_id cannot change.")
        return value

    def create(self, validated):
        validated.setdefault("start_date", services.today())
        return super().create(validated)

    def update(self, instance, validated):
        # #72: pausing freezes the dates used by #52 so it never shows off track.
        paused = validated.get("paused", instance.paused)
        if paused and not instance.paused:
            validated["paused_at"] = services.today()
        elif not paused and instance.paused and instance.paused_at:
            # Resume: shift the dates by the paused time.
            from datetime import timedelta

            gap = services.today() - instance.paused_at
            instance.start_date += timedelta(days=gap.days)
            instance.target_date += timedelta(days=gap.days)
            validated["paused_at"] = None
        return super().update(instance, validated)


class RateSerializer(serializers.Serializer):
    up = serializers.BooleanField()


class LoanSerializer(serializers.Serializer):
    """P2.8: balance > 0, rate 0-20 %, years 1-40."""

    customer_id = serializers.CharField()
    balance = serializers.FloatField()
    interest_rate = serializers.FloatField(min_value=0, max_value=20)
    years_left = serializers.IntegerField(min_value=1, max_value=40)

    def validate_balance(self, value):
        if value <= 0:
            raise serializers.ValidationError("Balance must be greater than 0.")
        return value


class SnoozeSerializer(serializers.Serializer):
    customer_id = serializers.CharField()
    days = serializers.IntegerField(min_value=1, max_value=90, default=7)

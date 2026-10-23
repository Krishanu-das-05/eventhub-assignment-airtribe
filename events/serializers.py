from rest_framework import serializers
from .models import Event, Reservation


class EventSerializer(serializers.ModelSerializer):
    reservations_count = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ['id', 'title', 'venue', 'date', 'total_seats',
                  'available_seats', 'status', 'created_at', 'reservations_count']

    def get_reservations_count(self, obj):
        return obj.reservations.filter(status='confirmed').count()

    def validate(self, data):
        total_seats = data.get('total_seats', getattr(self.instance, 'total_seats', 0))
        available_seats = data.get('available_seats', getattr(self.instance, 'available_seats', 0))
        if available_seats > total_seats:
            raise serializers.ValidationError('available_seats cannot exceed total_seats.')
        return data
class ReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservation
        fields = ['id', 'event', 'attendee_name', 'attendee_email',
                  'seats_reserved', 'status', 'created_at']
        read_only_fields = ['status', 'created_at']

    def validate_seats_reserved(self, value):
        if value < 1:
            raise serializers.ValidationError('Must reserve at least 1 seat.')
        return value

    def validate(self, data):
        reservation = self.instance
        if reservation is None:
            event = data['event']
            extra_seats = data['seats_reserved']
        else:
            event = reservation.event
            if data.get('event', event).pk != event.pk:
                raise serializers.ValidationError('A reservation cannot be moved to another event.')
            new_seats = data.get('seats_reserved', reservation.seats_reserved)
            if reservation.status == 'cancelled':
                if new_seats != reservation.seats_reserved:
                    raise serializers.ValidationError('Cannot change the seats of a cancelled reservation.')
                return data
            extra_seats = new_seats - reservation.seats_reserved
        if extra_seats > 0:
            if event.status not in ('upcoming', 'ongoing'):
                raise serializers.ValidationError(
                    f'Cannot reserve seats for a {event.status} event.'
                )
            if extra_seats > event.available_seats:
                raise serializers.ValidationError(
                    f'Only {event.available_seats} seat(s) available.'
                )
        return data

    def create(self, validated_data):
        event = validated_data['event']
        event.available_seats -= validated_data['seats_reserved']
        event.save()
        return Reservation.objects.create(**validated_data)

    def update(self, instance, validated_data):
        validated_data.pop('event', None)
        new_seats = validated_data.get('seats_reserved', instance.seats_reserved)
        if instance.status == 'confirmed' and new_seats != instance.seats_reserved:
            instance.event.available_seats -= new_seats - instance.seats_reserved
            instance.event.save()
        return super().update(instance, validated_data)
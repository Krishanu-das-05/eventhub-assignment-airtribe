from rest_framework.test import APITestCase

from .models import Event, Reservation

# Create your tests here.


class EventApiTests(APITestCase):
    def setUp(self):
        self.event = Event.objects.create(
            title='Meetup', venue='Pune', date='2025-10-01', total_seats=5, available_seats=5,
        )

    def test_patch_available_seats_only(self):
        response = self.client.patch(f'/api/events/{self.event.id}/', {'available_seats': 3}, format='json')
        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 3)

    def test_patch_available_seats_above_total_is_rejected(self):
        response = self.client.patch(f'/api/events/{self.event.id}/', {'available_seats': 6}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_patch_total_seats_below_available_is_rejected(self):
        response = self.client.patch(f'/api/events/{self.event.id}/', {'total_seats': 4}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_create_with_available_above_total_is_rejected(self):
        response = self.client.post('/api/events/', {
            'title': 'Big', 'venue': 'Pune', 'date': '2025-10-01', 'total_seats': 5, 'available_seats': 6,
        }, format='json')
        self.assertEqual(response.status_code, 400)


class ReservationApiTests(APITestCase):
    def setUp(self):
        self.event = Event.objects.create(
            title='Meetup', venue='Pune', date='2025-10-01', total_seats=5, available_seats=5,
        )
        self.other_event = Event.objects.create(
            title='Other', venue='Mumbai', date='2025-11-01', total_seats=5, available_seats=5,
        )

    def reserve(self, seats=2):
        response = self.client.post('/api/reservations/', {
            'event': self.event.id, 'attendee_name': 'Priya Sharma',
            'attendee_email': 'priya@example.com', 'seats_reserved': seats,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        return response.data['id']

    def available(self):
        self.event.refresh_from_db()
        return self.event.available_seats

    def test_create_deducts_seats(self):
        self.reserve(2)
        self.assertEqual(self.available(), 3)

    def test_overbooking_is_rejected(self):
        response = self.client.post('/api/reservations/', {
            'event': self.event.id, 'attendee_name': 'Rahul Verma',
            'attendee_email': 'rahul@example.com', 'seats_reserved': 6,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['non_field_errors'], ['Only 5 seat(s) available.'])

    def test_cancel_restores_seats(self):
        reservation_id = self.reserve(2)
        response = self.client.post(f'/api/reservations/{reservation_id}/cancel/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'cancelled')
        self.assertEqual(self.available(), 5)

    def test_patch_without_event_field(self):
        reservation_id = self.reserve(2)
        response = self.client.patch(f'/api/reservations/{reservation_id}/', {'attendee_name': 'Priya S'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['attendee_name'], 'Priya S')
        self.assertEqual(self.available(), 3)

    def test_patch_more_seats_deducts_difference(self):
        reservation_id = self.reserve(2)
        response = self.client.patch(f'/api/reservations/{reservation_id}/', {'seats_reserved': 4}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.available(), 1)

    def test_patch_fewer_seats_restores_difference(self):
        reservation_id = self.reserve(4)
        response = self.client.patch(f'/api/reservations/{reservation_id}/', {'seats_reserved': 1}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.available(), 4)

    def test_patch_can_use_all_remaining_seats(self):
        reservation_id = self.reserve(2)
        response = self.client.patch(f'/api/reservations/{reservation_id}/', {'seats_reserved': 5}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.available(), 0)

    def test_patch_overbooking_is_rejected(self):
        reservation_id = self.reserve(2)
        response = self.client.patch(f'/api/reservations/{reservation_id}/', {'seats_reserved': 6}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['non_field_errors'], ['Only 3 seat(s) available.'])
        self.assertEqual(self.available(), 3)

    def test_put_with_same_event(self):
        reservation_id = self.reserve(2)
        response = self.client.put(f'/api/reservations/{reservation_id}/', {
            'event': self.event.id, 'attendee_name': 'Priya Sharma',
            'attendee_email': 'priya@example.com', 'seats_reserved': 3,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.available(), 2)

    def test_moving_to_another_event_is_rejected(self):
        reservation_id = self.reserve(2)
        response = self.client.patch(f'/api/reservations/{reservation_id}/', {'event': self.other_event.id}, format='json')
        self.assertEqual(response.status_code, 400)
        self.other_event.refresh_from_db()
        self.assertEqual(self.other_event.available_seats, 5)
        self.assertEqual(self.available(), 3)

    def test_changing_seats_of_cancelled_reservation_is_rejected(self):
        reservation_id = self.reserve(2)
        self.client.post(f'/api/reservations/{reservation_id}/cancel/')
        response = self.client.patch(f'/api/reservations/{reservation_id}/', {'seats_reserved': 3}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.available(), 5)

    def test_editing_name_of_cancelled_reservation_is_allowed(self):
        reservation_id = self.reserve(2)
        self.client.post(f'/api/reservations/{reservation_id}/cancel/')
        response = self.client.patch(f'/api/reservations/{reservation_id}/', {'attendee_name': 'Priya S'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.available(), 5)

    def test_delete_confirmed_reservation_restores_seats(self):
        reservation_id = self.reserve(2)
        response = self.client.delete(f'/api/reservations/{reservation_id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Reservation.objects.filter(id=reservation_id).exists())
        self.assertEqual(self.available(), 5)

    def test_delete_cancelled_reservation_does_not_restore_twice(self):
        reservation_id = self.reserve(2)
        self.client.post(f'/api/reservations/{reservation_id}/cancel/')
        self.client.delete(f'/api/reservations/{reservation_id}/')
        self.assertEqual(self.available(), 5)

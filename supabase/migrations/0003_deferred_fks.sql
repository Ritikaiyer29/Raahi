-- Make every foreign key DEFERRABLE INITIALLY DEFERRED (checked at commit). Safe to re-run.
alter table public.conversations alter constraint conversations_user_id_fkey deferrable initially deferred;
alter table public.trip_requests alter constraint trip_requests_user_id_fkey deferrable initially deferred;
alter table public.trips alter constraint trips_user_id_fkey deferrable initially deferred;
alter table public.carts alter constraint carts_trip_id_fkey deferrable initially deferred;
alter table public.messages alter constraint messages_conversation_id_fkey deferrable initially deferred;
alter table public.trip_events alter constraint trip_events_trip_id_fkey deferrable initially deferred;
alter table public.trip_plans alter constraint trip_plans_request_id_fkey deferrable initially deferred;
alter table public.approvals alter constraint approvals_cart_id_fkey deferrable initially deferred;
alter table public.bookings alter constraint bookings_cart_id_fkey deferrable initially deferred;
alter table public.cart_items alter constraint cart_items_cart_id_fkey deferrable initially deferred;
alter table public.check_results alter constraint check_results_plan_id_fkey deferrable initially deferred;
alter table public.plan_legs alter constraint plan_legs_plan_id_fkey deferrable initially deferred;
alter table public.tickets alter constraint tickets_booking_id_fkey deferrable initially deferred;

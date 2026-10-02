/// Local-calendar constructors for hermetic tests.
///
/// `DateTime.utc(y, m, d, hour)` with a non-zero hour is not a same-day
/// fixture: at UTC+7 a 10:00 UTC and 18:00 UTC pair splits across local
/// midnight, so `grouped.values.single` throws. Use [localCalendarDay] (or
/// `conversationLocalDayKey`) whenever a test asserts one local-day bucket.
/// Prove new calendar assertions with `TZ=Pacific/Kiritimati` and
/// `TZ=Pacific/Pago_Pago`.
DateTime localCalendarDay(int year, int month, int day, [int hour = 12]) => DateTime(year, month, day, hour);

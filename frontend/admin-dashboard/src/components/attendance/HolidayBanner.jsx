import React from "react";

const formatLong = (iso) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

/**
 * Shown instead of the marking list when the selected date is a non-school
 * day.  `info` is the response of GET /school-calendar/check/.
 */
const HolidayBanner = ({ info, date }) => {
  if (!info || info.is_school_day) return null;
  const weekend = info.type === "weekend";
  return (
    <div
      role="status"
      className="mb-5 rounded-2xl border border-sky-200 bg-sky-50 px-5 py-6 text-center text-sky-900"
    >
      <p className="text-sm font-medium text-sky-700">{formatLong(info.date || date)}</p>
      <p className="mt-2 text-lg font-bold tracking-wide">
        <span aria-hidden="true">🏖 </span>
        {weekend ? "WEEKEND" : "HOLIDAY"}
        {!weekend && info.reason ? ` — ${info.reason}` : ""}
      </p>
      <p className="mt-1 text-sm text-sky-800">No attendance is required for this date.</p>
    </div>
  );
};

export default HolidayBanner;

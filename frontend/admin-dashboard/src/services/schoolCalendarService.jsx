import API from "./api";

const unwrap = (res) => res.data.results ?? res.data;

export const getHolidays = async (params = {}) =>
  unwrap(await API.get("school-calendar/", { params }));

export const createHoliday = async (payload) =>
  (await API.post("school-calendar/", payload)).data;

export const updateHoliday = async (id, payload) =>
  (await API.patch(`school-calendar/${id}/`, payload)).data;

export const deleteHoliday = async (id) => API.delete(`school-calendar/${id}/`);

// { date, is_school_day, reason, type, calendar_entry }
export const checkSchoolDay = async (date) =>
  (await API.get("school-calendar/check/", { params: { date } })).data;

// { school_days, non_school_days: [{ date, reason, type }] }
export const getSchoolDays = async (start, end) =>
  (await API.get("school-calendar/days/", { params: { start, end } })).data;

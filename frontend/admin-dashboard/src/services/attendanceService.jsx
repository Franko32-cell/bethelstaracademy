import API from "./api";

const unwrap = (res) => res.data.results ?? res.data;

// Original export — kept for backward compatibility.
export const getAttendance = async () => {
  const res = await API.get("attendance/");
  return res.data;
};

// Drops empty filter values so they are not sent as "?status=".
const clean = (params = {}) =>
  Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined)
  );

// Server-side filtered + paginated list.  Returns { results, count }.
export const listAttendance = async (params = {}) => {
  const res = await API.get("attendance/", { params: clean(params) });
  const data = res.data;
  return Array.isArray(data)
    ? { results: data, count: data.length }
    : { results: data.results ?? [], count: data.count ?? (data.results ?? []).length };
};

// Totals, per-student and per-class rows for the same filters.
export const getAttendanceSummary = async (params = {}) =>
  (await API.get("attendance/summary/", { params: clean(params) })).data;

export const updateAttendance = async (id, payload) =>
  (await API.patch(`attendance/${id}/`, payload)).data;

export const deleteAttendance = async (id) => API.delete(`attendance/${id}/`);

// Every record matching the filters (for CSV / print), 500 per request.
export const fetchAllAttendance = async (params = {}, maxPages = 20) => {
  const rows = [];
  for (let page = 1; page <= maxPages; page += 1) {
    const res = await API.get("attendance/", {
      params: { ...clean(params), page, page_size: 500 },
    });
    rows.push(...(res.data.results ?? res.data));
    if (!res.data.next) break;
  }
  return rows;
};

export const getClasses = async () => unwrap(await API.get("classes/"));
export const getTeachers = async () => unwrap(await API.get("teachers/"));
export const getClassStudents = async (classId) =>
  unwrap(await API.get("students/", { params: { school_class: classId } }));

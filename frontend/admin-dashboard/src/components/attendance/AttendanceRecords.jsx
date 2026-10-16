import React, { useEffect, useMemo, useState } from "react";
import {
  listAttendance,
  getAttendanceSummary,
  updateAttendance,
  deleteAttendance,
  fetchAllAttendance,
  getClasses,
  getTeachers,
  getClassStudents,
} from "../../services/attendanceService";
import { apiError } from "../../utils/apiError";

// ─── Config ──────────────────────────────────────────────────────────────────

const PAGE_SIZE = 25;

const STATUS_META = {
  present: { label: "Present", pill: "bg-emerald-100 text-emerald-700" },
  absent:  { label: "Absent",  pill: "bg-red-100 text-red-700" },
  late:    { label: "Late",    pill: "bg-amber-100 text-amber-700" },
  excused: { label: "Excused", pill: "bg-sky-100 text-sky-700" },
};

const TERMS = [
  { value: "term1", label: "Term 1" },
  { value: "term2", label: "Term 2" },
  { value: "term3", label: "Term 3" },
];

const PERIODS = [
  { value: "all",   label: "All dates" },
  { value: "today", label: "Today" },
  { value: "date",  label: "Specific date" },
  { value: "range", label: "Date range" },
];

const pad = (n) => String(n).padStart(2, "0");
const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const todayStr = () => isoDate(new Date());

const fmtDate = (iso) =>
  iso
    ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
        day: "numeric", month: "short", year: "numeric",
      })
    : "—";

const fmtDateTime = (iso) =>
  iso
    ? new Date(iso).toLocaleString(undefined, {
        day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
      })
    : "—";

const yearOptions = () => {
  const y = new Date().getFullYear();
  return Array.from({ length: 6 }, (_, i) => y + 1 - i);
};

const EMPTY_FILTERS = {
  period: "all", date: "", start: "", end: "",
  year: "", term: "", school_class: "", teacher: "", student: "", status: "", search: "",
};

const buildParams = (f, lockedClassId) => {
  const p = {
    year: f.year,
    term: f.term,
    school_class: lockedClassId || f.school_class,
    teacher: f.teacher,
    student: f.student,
    status: f.status,
    search: f.search.trim(),
  };
  if (f.period === "today") p.date = todayStr();
  if (f.period === "date" && f.date) p.date = f.date;
  if (f.period === "range") {
    if (f.start) p.date_after = f.start;
    if (f.end) p.date_before = f.end;
  }
  return p;
};

const rateColor = (r) =>
  r === null || r === undefined
    ? "text-gray-400"
    : r >= 80 ? "text-emerald-600" : r >= 60 ? "text-amber-600" : "text-red-600";

const fmtPct = (r) => (r === null || r === undefined ? "—" : `${Number(r).toFixed(1)}%`);

const esc = (v) =>
  String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const csvCell = (v) => {
  let s = String(v ?? "");
  // Neutralise spreadsheet formula injection.
  if (/^[=+\-@]/.test(s)) s = `'${s}`;
  return `"${s.replace(/"/g, '""')}"`;
};

const input =
  "w-full border border-gray-200 bg-white text-gray-800 px-3 py-2 rounded-xl text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-300 disabled:bg-gray-50 disabled:text-gray-400";
const labelCls = "text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1 block";

const StatusPill = ({ status }) => {
  const m = STATUS_META[status] || { label: status, pill: "bg-gray-100 text-gray-600" };
  return (
    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${m.pill}`}>
      {m.label}
    </span>
  );
};

const Tile = ({ label, value, tone = "text-gray-700", hint }) => (
  <div className="bg-gray-50 rounded-xl p-3">
    <div className="text-[11px] text-gray-400 uppercase tracking-wide">{label}</div>
    <div className={`text-2xl font-bold tabular-nums ${tone}`}>{value}</div>
    {hint && <div className="text-[10px] text-gray-400 mt-0.5">{hint}</div>}
  </div>
);

// ─── Component ───────────────────────────────────────────────────────────────

/**
 * Filterable attendance history + school-day-based summaries.
 *
 * role            "admin" | "teacher"
 * lockedClassId   teachers: the class they manage; the class filter is fixed
 *                 (the API enforces this too — it is only a UI convenience)
 */
const AttendanceRecords = ({ role = "admin", lockedClassId = "", onRecordChanged = () => {} }) => {
  const isAdmin = role === "admin";

  const [draft, setDraft] = useState(EMPTY_FILTERS);
  const [applied, setApplied] = useState(EMPTY_FILTERS);
  const [page, setPage] = useState(1);

  const [classes, setClasses] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [students, setStudents] = useState([]);

  // Results are stored with the key they were fetched for; "loading" is
  // simply "the stored key is not the current key".
  const [tick, setTick] = useState(0);            // bump to force a reload
  const [listState, setListState] = useState({ key: null, rows: [], count: 0, error: "" });
  const [sumState, setSumState] = useState({ key: null, data: null, error: "" });
  const [error, setError] = useState("");
  const [filterError, setFilterError] = useState("");
  const [notice, setNotice] = useState("");

  const [editing, setEditing] = useState(null);   // record being edited
  const [editForm, setEditForm] = useState({ status: "present", notes: "" });
  const [editError, setEditError] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(null); // record pending delete
  const [exporting, setExporting] = useState(false);

  const classFilter = lockedClassId || applied.school_class;
  const params = useMemo(() => buildParams(applied, lockedClassId), [applied, lockedClassId]);
  const listKey = JSON.stringify([params, page, tick]);
  const sumKey = JSON.stringify([params, tick]);
  const reload = () => setTick((t) => t + 1);

  const loading = listState.key !== listKey;
  const loadingSummary = sumState.key !== sumKey;
  const rows = listState.rows;
  const count = listState.count;
  const summary = sumState.data;
  const shownError = error || (loading ? "" : listState.error);

  // ── lookups ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (isAdmin) {
      getClasses().then(setClasses).catch(() => setError("Failed to load classes."));
      getTeachers().then(setTeachers).catch(() => {});
    }
  }, [isAdmin]);

  const draftClass = lockedClassId || draft.school_class;
  useEffect(() => {
    if (!draftClass) return undefined;
    let cancelled = false;
    getClassStudents(draftClass)
      .then((list) => !cancelled && setStudents(list))
      .catch((e) => {
        if (!cancelled) {
          setStudents([]);
          setError(apiError(e, "Failed to load class students."));
        }
      });
    return () => { cancelled = true; };
  }, [draftClass]);
  const classStudents = draftClass ? students : [];

  // ── data ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    listAttendance({ ...params, page, page_size: PAGE_SIZE })
      .then((d) => !cancelled && setListState({ key: listKey, rows: d.results, count: d.count, error: "" }))
      .catch((e) => !cancelled && setListState({
        key: listKey, rows: [], count: 0,
        error: apiError(e, "Failed to load attendance records."),
      }));
    return () => { cancelled = true; };
  }, [params, page, listKey]);

  useEffect(() => {
    let cancelled = false;
    getAttendanceSummary(params)
      .then((d) => !cancelled && setSumState({ key: sumKey, data: d, error: "" }))
      .catch((e) => !cancelled && setSumState({
        key: sumKey,
        data: null,
        error: apiError(e, "Failed to load attendance summary."),
      }));
    return () => { cancelled = true; };
  }, [params, sumKey]);

  // ── filter actions ───────────────────────────────────────────────────────
  const setField = (k, v) =>
    setDraft((d) => {
      const next = { ...d, [k]: v };
      if (k === "school_class") next.student = "";
      return next;
    });

  const applyFilters = (e) => {
    e?.preventDefault();
    if (draft.period === "range" && draft.start && draft.end && draft.start > draft.end) {
      setFilterError("Start date cannot be after the end date.");
      return;
    }
    if (draft.period === "date" && !draft.date) {
      setFilterError("Pick a date, or choose a different period.");
      return;
    }
    setFilterError("");
    setPage(1);
    setApplied({ ...draft });
  };

  const resetFilters = () => {
    setFilterError("");
    setDraft(EMPTY_FILTERS);
    setApplied(EMPTY_FILTERS);
    setPage(1);
  };

  // ── edit / delete ────────────────────────────────────────────────────────
  const openEdit = (rec) => {
    setEditing(rec);
    setEditForm({ status: rec.status, notes: rec.notes || "" });
    setEditError("");
  };

  const saveEdit = async () => {
    setSaving(true);
    setEditError("");
    try {
      await updateAttendance(editing.id, { status: editForm.status, notes: editForm.notes });
      setEditing(null);
      setNotice("Attendance record updated.");
      reload();
      await onRecordChanged();
    } catch (e) {
      setEditError(apiError(e, "Could not update the record."));
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    try {
      await deleteAttendance(deleting.id);
      setDeleting(null);
      setNotice("Attendance record deleted.");
      if (rows.length === 1 && page > 1) setPage(page - 1);
      reload();
      await onRecordChanged();
    } catch (e) {
      setDeleting(null);
      setError(apiError(e, "Could not delete the record."));
    }
  };

  // ── export / print ───────────────────────────────────────────────────────
  const periodLabel = summary?.period?.start
    ? `${fmtDate(summary.period.start)} – ${fmtDate(summary.period.end)}`
    : "All recorded dates";

  const exportCsv = async () => {
    setExporting(true);
    try {
      const all = await fetchAllAttendance(params);
      const head = ["Date", "Student", "Admission No.", "Class", "Status", "Notes",
        "Recorded by", "Recorded at", "Last modified by", "Last modified at"];
      const lines = [head.map(csvCell).join(",")];
      all.forEach((r) => lines.push([
        r.date, r.student_name, r.admission_number, r.class_name,
        STATUS_META[r.status]?.label || r.status, r.notes,
        r.created_by_name || "", r.created_at || "", r.updated_by_name || "", r.updated_at || "",
      ].map(csvCell).join(",")));
      const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `attendance_${todayStr()}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(apiError(e, "Export failed."));
    } finally {
      setExporting(false);
    }
  };

  const printReport = async () => {
    setExporting(true);
    try {
      const all = await fetchAllAttendance(params);
      const t = summary?.totals;
      const w = window.open("", "_blank");
      if (!w) { setError("Allow pop-ups to print the report."); return; }
      const studentRows = (summary?.students || []).map((s) =>
        `<tr><td>${esc(s.student_name)}</td><td>${esc(s.admission_number)}</td><td>${s.present}</td><td>${s.absent}</td><td>${s.late}</td><td>${s.excused}</td><td>${fmtPct(s.percentage)}</td></tr>`).join("");
      const recordRows = all.map((r) =>
        `<tr><td>${esc(fmtDate(r.date))}</td><td>${esc(r.student_name)}</td><td>${esc(r.admission_number)}</td><td>${esc(r.class_name)}</td><td>${esc(STATUS_META[r.status]?.label || r.status)}</td><td>${esc(r.updated_by_name || r.created_by_name || "")}</td></tr>`).join("");
      w.document.write(`<!doctype html><html><head><title>Attendance report</title>
<style>body{font-family:Arial,sans-serif;font-size:12px;color:#111;margin:24px}h1{font-size:18px;margin:0 0 4px}h2{font-size:14px;margin:18px 0 6px}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:4px 6px;text-align:left}th{background:#f3f4f6}.m{color:#555;margin:2px 0}</style></head><body>
<h1>Attendance report</h1>
<p class="m">Period: ${esc(periodLabel)}</p>
${t ? `<p class="m">School days: ${t.school_days} · Attended: ${t.attended} · Absent: ${t.absent} · Late: ${t.late} · Excused: ${t.excused} · Attendance: ${fmtPct(t.percentage)}</p>` : ""}
<p class="m">Weekends, holidays and excused days are not counted against students.</p>
${studentRows ? `<h2>By student</h2><table><thead><tr><th>Student</th><th>Adm. No.</th><th>Present</th><th>Absent</th><th>Late</th><th>Excused</th><th>%</th></tr></thead><tbody>${studentRows}</tbody></table>` : ""}
<h2>Records (${all.length})</h2><table><thead><tr><th>Date</th><th>Student</th><th>Adm. No.</th><th>Class</th><th>Status</th><th>Recorded by</th></tr></thead><tbody>${recordRows}</tbody></table>
<script>window.onload=function(){window.print()}</script></body></html>`);
      w.document.close();
    } catch (e) {
      setError(apiError(e, "Could not prepare the report."));
    } finally {
      setExporting(false);
    }
  };

  // ── derived ──────────────────────────────────────────────────────────────
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const from = count === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, count);
  const t = summary?.totals;
  const holidays = summary?.holidays || [];
  const studentLabel = (s) =>
    s.student_name || [s.first_name, s.last_name].filter(Boolean).join(" ") || s.admission_number;

  // ── render ───────────────────────────────────────────────────────────────
  return (
    <div>
      {/* Filters */}
      <form onSubmit={applyFilters} className="bg-white border border-gray-100 rounded-2xl shadow-sm p-4 mb-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <label className={labelCls} htmlFor="ar-year">Academic year</label>
            <select id="ar-year" className={input} value={draft.year} onChange={(e) => setField("year", e.target.value)}>
              <option value="">All years</option>
              {yearOptions().map((y) => <option key={y} value={y}>{y}/{y + 1}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="ar-term">Term</label>
            <select id="ar-term" className={input} value={draft.term} onChange={(e) => setField("term", e.target.value)}>
              <option value="">All terms</option>
              {TERMS.map((tm) => <option key={tm.value} value={tm.value}>{tm.label}</option>)}
            </select>
          </div>
          {isAdmin && (
            <div>
              <label className={labelCls} htmlFor="ar-class">Class</label>
              <select id="ar-class" className={input} value={draft.school_class} onChange={(e) => setField("school_class", e.target.value)}>
                <option value="">All classes</option>
                {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          )}
          {isAdmin && (
            <div>
              <label className={labelCls} htmlFor="ar-teacher">Teacher</label>
              <select id="ar-teacher" className={input} value={draft.teacher} onChange={(e) => setField("teacher", e.target.value)}>
                <option value="">All teachers</option>
                {teachers.map((tc) => <option key={tc.id} value={tc.id}>{tc.teacher_name || tc.teacher_id}</option>)}
              </select>
            </div>
          )}
          <div>
            <label className={labelCls} htmlFor="ar-student">Student</label>
            <select id="ar-student" className={input} value={draft.student}
              disabled={!draftClass} onChange={(e) => setField("student", e.target.value)}>
              <option value="">{draftClass ? "All students" : "Select a class first"}</option>
              {classStudents.map((s) => <option key={s.id} value={s.id}>{studentLabel(s)}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="ar-status">Status</label>
            <select id="ar-status" className={input} value={draft.status} onChange={(e) => setField("status", e.target.value)}>
              <option value="">All statuses</option>
              {Object.entries(STATUS_META).map(([v, m]) => <option key={v} value={v}>{m.label}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="ar-period">Date</label>
            <select id="ar-period" className={input} value={draft.period} onChange={(e) => setField("period", e.target.value)}>
              {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="ar-search">Search student</label>
            <input id="ar-search" type="search" className={input} placeholder="Name or admission no."
              value={draft.search} onChange={(e) => setField("search", e.target.value)} />
          </div>

          {draft.period === "date" && (
            <div>
              <label className={labelCls} htmlFor="ar-date">Specific date</label>
              <input id="ar-date" type="date" className={input} max={todayStr()} value={draft.date}
                onChange={(e) => setField("date", e.target.value)} />
            </div>
          )}
          {draft.period === "range" && (
            <>
              <div>
                <label className={labelCls} htmlFor="ar-from">From date</label>
                <input id="ar-from" type="date" className={input} max={todayStr()} value={draft.start}
                  onChange={(e) => setField("start", e.target.value)} />
              </div>
              <div>
                <label className={labelCls} htmlFor="ar-to">To date</label>
                <input id="ar-to" type="date" className={input} max={todayStr()} value={draft.end}
                  onChange={(e) => setField("end", e.target.value)} />
              </div>
            </>
          )}
        </div>

        {filterError && <p role="alert" className="mt-3 text-sm text-red-600">{filterError}</p>}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button type="submit" className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-5 py-2 rounded-xl shadow-sm">
            Apply Filters
          </button>
          <button type="button" onClick={resetFilters} className="bg-white border border-gray-200 hover:bg-gray-50 text-gray-600 text-sm font-semibold px-5 py-2 rounded-xl">
            Reset
          </button>
          <div className="ml-auto flex gap-2">
            <button type="button" onClick={exportCsv} disabled={exporting || count === 0}
              className="bg-white border border-gray-200 hover:bg-gray-50 text-gray-600 text-sm font-semibold px-4 py-2 rounded-xl disabled:opacity-40">
              {exporting ? "Preparing…" : "Export CSV"}
            </button>
            <button type="button" onClick={printReport} disabled={exporting || count === 0}
              className="bg-white border border-gray-200 hover:bg-gray-50 text-gray-600 text-sm font-semibold px-4 py-2 rounded-xl disabled:opacity-40">
              Print
            </button>
          </div>
        </div>
      </form>

      {(shownError || sumState.error) && (
        <div role="alert" className="mb-4 px-4 py-3 rounded-xl text-sm font-medium bg-red-50 border border-red-200 text-red-700 flex justify-between gap-3">
          <span>{shownError || sumState.error}</span>
          <button
            onClick={() => { setError(""); setListState((s) => ({ ...s, error: "" })); }}
            aria-label="Dismiss" className="opacity-60 hover:opacity-100">✕</button>
        </div>
      )}
      {notice && (
        <div role="status" className="mb-4 px-4 py-3 rounded-xl text-sm font-medium bg-emerald-50 border border-emerald-200 text-emerald-700 flex justify-between gap-3">
          <span>{notice}</span>
          <button onClick={() => setNotice("")} aria-label="Dismiss" className="opacity-60 hover:opacity-100">✕</button>
        </div>
      )}

      {/* Summary */}
      <section className="mb-6" aria-label="Attendance summary">
        <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
          <h3 className="text-sm font-semibold text-gray-700">Summary</h3>
          <p className="text-xs text-gray-400">
            Period: <span className="font-medium text-gray-500">{periodLabel}</span>
          </p>
        </div>
        {loadingSummary && !t ? (
          <p className="text-sm text-gray-400 py-3">Calculating summary…</p>
        ) : t ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <Tile label="School days" value={summary.school_days} hint="weekends & holidays excluded" />
              <Tile label="Days attended" value={t.attended} tone="text-emerald-600" hint="present + late" />
              <Tile label="Absent" value={t.absent} tone="text-red-600" />
              <Tile label="Late" value={t.late} tone="text-amber-600" />
              <Tile label="Excused" value={t.excused} tone="text-sky-600" hint="not counted" />
              <Tile label="Attendance" value={fmtPct(t.percentage)} tone={rateColor(t.percentage)} />
            </div>
            {holidays.length > 0 && (
              <p className="mt-2 text-xs text-gray-400">
                <span aria-hidden="true">🏖 </span>
                Excluded from calculations:{" "}
                {holidays.slice(0, 6).map((h) => `${fmtDate(h.date)} (${h.name})`).join(", ")}
                {holidays.length > 6 ? ` and ${holidays.length - 6} more` : ""}
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-gray-400 py-3">No summary available for these filters.</p>
        )}
      </section>

      {/* Class report / by class */}
      {summary && summary.students?.length > 0 && classFilter && (
        <section className="mb-6" aria-label="Class report">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Class report</h3>
          <div className="overflow-x-auto rounded-2xl border border-gray-100 shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/80 text-gray-400 text-xs uppercase tracking-wider">
                  <th className="px-4 py-3 text-left">Student</th>
                  <th className="px-4 py-3 text-left hidden sm:table-cell">Adm. No.</th>
                  <th className="px-4 py-3 text-center">Present</th>
                  <th className="px-4 py-3 text-center">Absent</th>
                  <th className="px-4 py-3 text-center">Late</th>
                  <th className="px-4 py-3 text-center">Excused</th>
                  <th className="px-4 py-3 text-center">Attendance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {summary.students.map((s) => (
                  <tr key={s.student} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-medium text-gray-800">{s.student_name}</td>
                    <td className="px-4 py-2.5 text-gray-400 text-xs hidden sm:table-cell">{s.admission_number}</td>
                    <td className="px-4 py-2.5 text-center text-emerald-600 font-semibold">{s.present}</td>
                    <td className="px-4 py-2.5 text-center text-red-500 font-semibold">{s.absent}</td>
                    <td className="px-4 py-2.5 text-center text-amber-500 font-semibold">{s.late}</td>
                    <td className="px-4 py-2.5 text-center text-sky-600 font-semibold">{s.excused}</td>
                    <td className={`px-4 py-2.5 text-center font-semibold tabular-nums ${rateColor(s.percentage)}`}>{fmtPct(s.percentage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {isAdmin && summary && !classFilter && summary.by_class?.length > 1 && (
        <section className="mb-6" aria-label="By class">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">By class</h3>
          <div className="overflow-x-auto rounded-2xl border border-gray-100 shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/80 text-gray-400 text-xs uppercase tracking-wider">
                  <th className="px-4 py-3 text-left">Class</th>
                  <th className="px-4 py-3 text-center">Present</th>
                  <th className="px-4 py-3 text-center">Absent</th>
                  <th className="px-4 py-3 text-center">Late</th>
                  <th className="px-4 py-3 text-center">Excused</th>
                  <th className="px-4 py-3 text-center">Attendance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {summary.by_class.map((c) => (
                  <tr key={c.school_class} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-medium text-gray-800">{c.class_name}</td>
                    <td className="px-4 py-2.5 text-center text-emerald-600 font-semibold">{c.present}</td>
                    <td className="px-4 py-2.5 text-center text-red-500 font-semibold">{c.absent}</td>
                    <td className="px-4 py-2.5 text-center text-amber-500 font-semibold">{c.late}</td>
                    <td className="px-4 py-2.5 text-center text-sky-600 font-semibold">{c.excused}</td>
                    <td className={`px-4 py-2.5 text-center font-semibold tabular-nums ${rateColor(c.percentage)}`}>{fmtPct(c.percentage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Records */}
      <section aria-label="Attendance records">
        <div className="flex items-baseline justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-700">History</h3>
          <p className="text-xs text-gray-400 tabular-nums">
            {count > 0 ? `Showing ${from}–${to} of ${count}` : ""}
          </p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center gap-3 py-14 text-gray-400 text-sm" role="status">
            <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24" aria-hidden="true">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            Loading attendance…
          </div>
        ) : rows.length === 0 ? (
          <div className="text-center py-14 text-gray-400 rounded-2xl border border-dashed border-gray-200">
            <div className="text-4xl mb-3" aria-hidden="true">🗃️</div>
            <p className="text-sm">No attendance records match these filters.</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-gray-100 shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/80 text-gray-400 text-xs uppercase tracking-wider">
                  <th className="px-4 py-3 text-left">Date</th>
                  <th className="px-4 py-3 text-left">Student</th>
                  <th className="px-4 py-3 text-left hidden md:table-cell">Class</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-left hidden lg:table-cell">Recorded</th>
                  <th className="px-4 py-3 text-left hidden lg:table-cell">Last modified</th>
                  <th className="px-4 py-3 text-right"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {rows.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 whitespace-nowrap text-gray-700">{fmtDate(r.date)}</td>
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-gray-800 leading-tight">{r.student_name}</div>
                      <div className="text-[11px] text-gray-400">{r.admission_number}</div>
                    </td>
                    <td className="px-4 py-2.5 text-gray-500 hidden md:table-cell">{r.class_name}</td>
                    <td className="px-4 py-2.5 text-center"><StatusPill status={r.status} /></td>
                    <td className="px-4 py-2.5 text-xs text-gray-500 hidden lg:table-cell">
                      <div>{r.created_by_name || "—"}</div>
                      <div className="text-gray-400">{fmtDateTime(r.created_at)}</div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-500 hidden lg:table-cell">
                      <div>{r.updated_by_name || "—"}</div>
                      <div className="text-gray-400">{fmtDateTime(r.updated_at)}</div>
                    </td>
                    <td className="px-4 py-2.5 text-right whitespace-nowrap">
                      <button onClick={() => openEdit(r)}
                        className="text-xs px-2.5 py-1 rounded-lg border border-blue-100 text-blue-600 hover:bg-blue-600 hover:text-white transition-colors">
                        Edit
                      </button>
                      {isAdmin && (
                        <button onClick={() => setDeleting(r)}
                          className="ml-1.5 text-xs px-2.5 py-1 rounded-lg border border-red-100 text-red-400 hover:bg-red-600 hover:text-white transition-colors">
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {totalPages > 1 && !loading && (
          <div className="mt-3 flex items-center justify-center gap-3 text-sm">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
              className="px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 disabled:opacity-40">← Prev</button>
            <span className="text-gray-400 tabular-nums">Page {page} of {totalPages}</span>
            <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}
              className="px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 disabled:opacity-40">Next →</button>
          </div>
        )}
      </section>

      {/* Edit modal */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-label="Edit attendance">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <h4 className="text-base font-bold text-gray-800">Edit attendance</h4>
            <p className="text-sm text-gray-500 mt-0.5">{editing.student_name} · {fmtDate(editing.date)}</p>

            <label className={`${labelCls} mt-4`} htmlFor="ed-status">Status</label>
            <select id="ed-status" className={input} value={editForm.status}
              onChange={(e) => setEditForm((f) => ({ ...f, status: e.target.value }))}>
              {Object.entries(STATUS_META).map(([v, m]) => <option key={v} value={v}>{m.label}</option>)}
            </select>
            {editForm.status === "excused" && (
              <p className="text-[11px] text-gray-400 mt-1">Excused days are left out of the attendance percentage.</p>
            )}

            <label className={`${labelCls} mt-3`} htmlFor="ed-notes">Notes</label>
            <textarea id="ed-notes" rows={3} className={input} value={editForm.notes}
              onChange={(e) => setEditForm((f) => ({ ...f, notes: e.target.value }))} />

            <p className="text-[11px] text-gray-400 mt-3">
              Recorded by {editing.created_by_name || "—"} · {fmtDateTime(editing.created_at)}<br />
              Last modified by {editing.updated_by_name || "—"} · {fmtDateTime(editing.updated_at)}
            </p>

            {editError && <p role="alert" className="mt-3 text-sm text-red-600">{editError}</p>}

            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setEditing(null)} disabled={saving}
                className="px-4 py-2 rounded-xl text-sm font-semibold border border-gray-200 text-gray-600 hover:bg-gray-50">Cancel</button>
              <button onClick={saveEdit} disabled={saving}
                className="px-4 py-2 rounded-xl text-sm font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirm */}
      {deleting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-label="Confirm delete">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            <p className="text-sm text-gray-700 leading-relaxed">
              Delete the attendance record for <b>{deleting.student_name}</b> on {fmtDate(deleting.date)}? This is logged in the audit trail and cannot be undone.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setDeleting(null)} autoFocus
                className="px-4 py-2 rounded-xl text-sm font-semibold border border-gray-200 text-gray-600 hover:bg-gray-50">Cancel</button>
              <button onClick={confirmDelete}
                className="px-4 py-2 rounded-xl text-sm font-semibold bg-red-600 text-white hover:bg-red-700">Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AttendanceRecords;

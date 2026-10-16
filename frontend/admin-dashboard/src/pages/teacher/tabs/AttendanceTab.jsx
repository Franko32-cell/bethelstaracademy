import React, { useState } from "react";
import { StatusPill } from "../Ui";
import HolidayBanner from "../../../components/attendance/HolidayBanner";
import AttendanceRecords from "../../../components/attendance/AttendanceRecords";

const VIEWS = [
  { key: "mark",    label: "Mark attendance" },
  { key: "history", label: "History & summary" },
];

const AttendanceTab = ({
  students = [],
  loading = false,
  selectedClassName = "",
  attDate = "",
  attendance = {},
  dayInfo = null,
  recorded = false,
  classId = "",
  saving = false,
  onToggle = () => {},
  onSave = () => {},
}) => {
  const [view, setView] = useState("mark");

  const switcher = (
    <div className="flex gap-1 mb-4 border-b border-slate-100" role="tablist">
      {VIEWS.map((v) => (
        <button
          key={v.key}
          type="button"
          role="tab"
          aria-selected={view === v.key}
          onClick={() => setView(v.key)}
          className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
            view === v.key
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-400 hover:text-slate-600"
          }`}
        >
          {v.label}
        </button>
      ))}
    </div>
  );

  if (view === "history") {
    return (
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
        {switcher}
        {classId ? (
          <AttendanceRecords role="teacher" lockedClassId={String(classId)} />
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
            Select a class to view its attendance history.
          </div>
        )}
      </div>
    );
  }

  if (loading) return <div className="p-4 text-sm text-slate-500">Loading attendance…</div>;

  const values = Object.values(attendance);
  const statusCounts = {
    present: values.filter((s) => s === "present").length,
    absent: values.filter((s) => s === "absent").length,
    late: values.filter((s) => s === "late").length,
    excused: values.filter((s) => s === "excused").length,
  };

  const nonSchoolDay = !!dayInfo && !dayInfo.is_school_day;
  const studentCount = students.length;
  const dateSummary = studentCount
    ? `${statusCounts.present} present · ${statusCounts.absent} absent · ${statusCounts.late} late · ${statusCounts.excused} excused`
    : "No students to mark attendance.";

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
      {switcher}

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between mb-5">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Attendance</p>
          <h3 className="mt-1 text-xl font-semibold text-slate-900">{selectedClassName || "Class"}</h3>
          <p className="text-sm text-slate-500">Date: {attDate}</p>
          {!nonSchoolDay && <p className="text-sm text-slate-500 mt-2">{dateSummary}</p>}
          {!nonSchoolDay && studentCount > 0 && (
            recorded ? (
              <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                ✓ Attendance already recorded for this date — saving will update it
              </p>
            ) : (
              <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">
                Not recorded yet for this date
              </p>
            )
          )}
        </div>
        {!nonSchoolDay && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-sm">
            <div className="rounded-2xl bg-emerald-50 px-3 py-3 text-emerald-700">
              <div className="text-xs uppercase tracking-[0.24em]">Present</div>
              <div className="text-lg font-semibold">{statusCounts.present}</div>
            </div>
            <div className="rounded-2xl bg-red-50 px-3 py-3 text-red-700">
              <div className="text-xs uppercase tracking-[0.24em]">Absent</div>
              <div className="text-lg font-semibold">{statusCounts.absent}</div>
            </div>
            <div className="rounded-2xl bg-amber-50 px-3 py-3 text-amber-700">
              <div className="text-xs uppercase tracking-[0.24em]">Late</div>
              <div className="text-lg font-semibold">{statusCounts.late}</div>
            </div>
            <div className="rounded-2xl bg-sky-50 px-3 py-3 text-sky-700">
              <div className="text-xs uppercase tracking-[0.24em]">Excused</div>
              <div className="text-lg font-semibold">{statusCounts.excused}</div>
            </div>
          </div>
        )}
      </div>

      {nonSchoolDay ? (
        <HolidayBanner info={dayInfo} date={attDate} />
      ) : students.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
          No students available to mark attendance.
        </div>
      ) : (
        <div className="divide-y divide-slate-100">
          {students.map((s) => {
            const status = attendance?.[s.id] ?? "present";
            const studentIdLabel = s.admission_number || s.username || `ID: ${s.id}`;
            return (
              <div key={s.id} className="flex flex-col gap-3 border-b border-slate-100 py-4 sm:flex-row sm:items-center sm:justify-between last:border-b-0">
                <div className="min-w-0">
                  <p className="font-medium text-slate-800">{s.student_name || s.name}</p>
                  <p className="text-sm text-slate-500">{studentIdLabel}</p>
                </div>
                <button
                  type="button"
                  onClick={() => onToggle(s.id)}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-300"
                >
                  <StatusPill status={status} />
                  <span className="text-xs uppercase tracking-[0.18em] text-slate-500">Tap to change</span>
                </button>
              </div>
            );
          })}
        </div>
      )}

      {!nonSchoolDay && (
        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-500">Tap each status pill to cycle through Present, Absent, Late and Excused.</p>
          <button
            onClick={onSave}
            disabled={saving || students.length === 0}
            className="inline-flex items-center justify-center rounded-2xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {saving ? "Saving…" : recorded ? "Update Attendance" : "Save Attendance"}
          </button>
        </div>
      )}
    </div>
  );
};

export default AttendanceTab;

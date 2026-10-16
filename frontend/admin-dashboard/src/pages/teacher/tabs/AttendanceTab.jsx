import React, { useMemo, useState } from "react";
import HolidayBanner from "../../../components/attendance/HolidayBanner";
import AttendanceRecords from "../../../components/attendance/AttendanceRecords";

const VIEWS = [
  { key: "mark", label: "Mark attendance" },
  { key: "history", label: "History & summary" },
];

const STATUS_OPTIONS = [
  { value: "present", label: "Present", active: "bg-emerald-600 text-white", idle: "bg-emerald-50 text-emerald-700 hover:bg-emerald-100" },
  { value: "absent", label: "Absent", active: "bg-red-600 text-white", idle: "bg-red-50 text-red-700 hover:bg-red-100" },
  { value: "late", label: "Late", active: "bg-amber-500 text-white", idle: "bg-amber-50 text-amber-700 hover:bg-amber-100" },
  { value: "excused", label: "Excused", active: "bg-sky-600 text-white", idle: "bg-sky-50 text-sky-700 hover:bg-sky-100" },
];

const shiftDate = (value, days) => {
  const date = new Date(`${value}T00:00:00`);
  date.setDate(date.getDate() + days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
};

const studentName = (student) =>
  student.student_name ||
  student.name ||
  [student.first_name, student.last_name].filter(Boolean).join(" ") ||
  `Student ${student.id}`;

const AttendanceTab = ({
  students = [],
  loading = false,
  attendanceLoading = false,
  attendanceReady = false,
  selectedClassName = "",
  attDate = "",
  attendance = {},
  dayInfo = null,
  recorded = false,
  classId = "",
  saving = false,
  onDateChange = () => {},
  onToggle = () => {},
  onMarkAll = () => {},
  onSave = () => {},
  onHistoryChange = () => {},
  onRetry = () => {},
}) => {
  const [view, setView] = useState("mark");
  const [search, setSearch] = useState("");
  const today = new Date();
  const todayValue = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const selectedDayInfo = dayInfo?.date === attDate ? dayInfo : null;

  const counts = useMemo(() => {
    const result = { present: 0, absent: 0, late: 0, excused: 0, unset: 0 };
    Object.values(attendance).forEach((status) => {
      if (status && result[status] !== undefined) result[status] += 1;
      else result.unset += 1;
    });
    return result;
  }, [attendance]);

  const filteredStudents = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    if (!query) return students;
    return students.filter((student) =>
      studentName(student).toLocaleLowerCase().includes(query) ||
      String(student.admission_number || "").toLocaleLowerCase().includes(query)
    );
  }, [search, students]);

  const switcher = (
    <div className="flex gap-1 mb-4 border-b border-slate-100" role="tablist">
      {VIEWS.map((item) => (
        <button
          key={item.key}
          type="button"
          role="tab"
          aria-selected={view === item.key}
          onClick={() => setView(item.key)}
          className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
            view === item.key
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-400 hover:text-slate-600"
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );

  if (view === "history") {
    return (
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
        {switcher}
        {classId ? (
          <AttendanceRecords
            role="teacher"
            lockedClassId={String(classId)}
            onRecordChanged={onHistoryChange}
          />
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
            Select a class to view its attendance history.
          </div>
        )}
      </div>
    );
  }

  const nonSchoolDay = selectedDayInfo && !selectedDayInfo.is_school_day;
  const canSave = attendanceReady && !attendanceLoading && !loading &&
    Boolean(selectedDayInfo?.is_school_day) && !nonSchoolDay;
  const isBusy = loading || attendanceLoading;

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
      {switcher}

      <div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Attendance</p>
          <h3 className="mt-1 text-xl font-semibold text-slate-900">{selectedClassName || "Class"}</h3>
          <p className="text-sm text-slate-500">
            {students.length} students · {counts.present} present · {counts.absent} absent · {counts.late} late · {counts.excused} excused
            {counts.unset > 0 ? ` · ${counts.unset} unmarked` : ""}
          </p>
          {recorded && (
            <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
              ✓ Attendance already recorded for this date — saving will update it
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="teacher-attendance-date" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">
              Date
            </label>
            <input
              id="teacher-attendance-date"
              type="date"
              value={attDate}
              max={todayValue}
              onChange={(event) => onDateChange(event.target.value)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          </div>
          <button
            type="button"
            onClick={() => onDateChange(shiftDate(attDate, -1))}
            disabled={!attDate || shiftDate(attDate, -1) > todayValue}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40"
          >
            Previous day
          </button>
          <button
            type="button"
            onClick={() => onDateChange(todayValue)}
            disabled={attDate === todayValue}
            className="rounded-xl border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-semibold text-blue-600 hover:bg-blue-100 disabled:opacity-40"
          >
            Today
          </button>
          <button
            type="button"
            onClick={() => onDateChange(shiftDate(attDate, 1))}
            disabled={!attDate || shiftDate(attDate, 1) > todayValue}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40"
          >
            Next day
          </button>
        </div>
      </div>

      {nonSchoolDay ? (
        <HolidayBanner info={selectedDayInfo} date={attDate} />
      ) : (
        <>
          <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Mark all</span>
              {STATUS_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onMarkAll(option.value)}
                  disabled={isBusy || !attendanceReady || students.length === 0 || !selectedDayInfo?.is_school_day}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40 ${option.idle}`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <label className="block w-full lg:max-w-xs">
              <span className="sr-only">Search students</span>
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search name or admission number…"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
              />
            </label>
          </div>

          {!selectedDayInfo && (
            <p role="status" className="mb-3 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800">
              {attendanceLoading ? "Checking the school calendar…" : "School-day status is unavailable. Retry loading attendance."}
            </p>
          )}

          {isBusy ? (
            <div className="py-10 text-center text-sm text-slate-500" role="status">Loading attendance…</div>
          ) : students.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
              No students available to mark attendance.
            </div>
          ) : filteredStudents.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
              No students match “{search}”.
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {filteredStudents.map((student) => {
                const status = attendance?.[student.id] ?? null;
                return (
                  <div key={student.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <p className="font-medium text-slate-800">{studentName(student)}</p>
                      <p className="text-sm text-slate-500">{student.admission_number || `ID: ${student.id}`}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {STATUS_OPTIONS.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          aria-pressed={status === option.value}
                          onClick={() => onToggle(student.id, option.value)}
                          disabled={isBusy || !attendanceReady || !selectedDayInfo?.is_school_day}
                          className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                            status === option.value ? option.active : option.idle
                          }`}
                        >
                          {option.label}
                        </button>
                      ))}
                      {!status && <span className="ml-1 text-xs text-slate-400">Unmarked</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {!isBusy && students.length > 0 && (!attendanceReady || !selectedDayInfo) && (
            <div className="my-4 text-center">
              <button
                type="button"
                onClick={onRetry}
                className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-100"
              >
                Retry loading attendance
              </button>
            </div>
          )}

          <div className="mt-6 flex flex-col gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-slate-500">
              Past dates start unmarked. Choose a status for each student or use Mark all.
            </p>
            <button
              type="button"
              onClick={onSave}
              disabled={saving || isBusy || !canSave || students.length === 0 || counts.present + counts.absent + counts.late + counts.excused === 0}
              className="inline-flex items-center justify-center rounded-2xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {saving ? "Saving…" : recorded ? "Update attendance" : "Save attendance"}
            </button>
          </div>
        </>
      )}
    </div>
  );
};

export default AttendanceTab;

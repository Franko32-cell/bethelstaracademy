import React from "react";
import { gradeFromTotal } from "../Helpers";
import { isExamOnly, SBA_COMPONENTS, scoreResult } from "../../../utils/sbaScoring";

const AVATAR_COLORS = [
  "bg-blue-100 text-blue-700",
  "bg-emerald-100 text-emerald-700",
  "bg-violet-100 text-violet-700",
  "bg-amber-100 text-amber-700",
  "bg-rose-100 text-rose-700",
  "bg-cyan-100 text-cyan-700",
];

const getInitials = (name = "") =>
  name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase();

const ResultsTab = ({
  students = [],
  selectedSubject = "",
  selectedClassLevel = "",
  scores = {},
  existingIds = {},
  saving = false,
  deleting = false,
  filledCount = 0,
  onScoreChange = () => {},
  onDelete = () => {},
  onSubmit = () => {},
}) => {
  const savedCount = Object.keys(existingIds).length;

  if (!selectedSubject) {
    return (
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-12 text-center">
        <div className="w-12 h-12 rounded-2xl bg-blue-50 flex items-center justify-center mx-auto mb-4">
          <svg className="w-6 h-6 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        </div>
        <p className="text-sm font-bold text-slate-800 mb-1">Pick a subject to get started</p>
        <p className="text-sm text-slate-400">Choose a subject from the filter above, then enter scores for each student.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-5">

      {/* ── Header ── */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-[10.5px] font-bold tracking-widest text-slate-400 uppercase mb-1">Results entry</p>
          <h3 className="text-xl font-extrabold text-slate-900 tracking-tight">{selectedSubject}</h3>
          <p className="text-sm text-slate-500 mt-0.5">{selectedClassLevel || "Class level"} · enter values for the selected term and year</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 112.828 2.828L11.828 15.828a4 4 0 01-1.414.914l-3.414.672.672-3.414A4 4 0 019 13z" />
            </svg>
            Filled: {filledCount}
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            Saved: {savedCount}
          </span>
          <span className="inline-flex items-center px-3 py-1.5 rounded-full text-xs font-bold bg-slate-100 text-slate-500">
            {students.length} students
          </span>
        </div>
      </div>

      {/* ── Score legend cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          ...(isExamOnly(selectedClassLevel)
            ? [{ label: "Exam", max: "/ 100", color: "bg-slate-50 border-slate-200 text-slate-700" }]
            : [
                { label: "Test 1", max: "/ 20", color: "bg-slate-50 border-slate-200 text-slate-700" },
                { label: "Group Work", max: "/ 20", color: "bg-slate-50 border-slate-200 text-slate-700" },
                { label: "Test 2", max: "/ 20", color: "bg-slate-50 border-slate-200 text-slate-700" },
                { label: "SBA", max: "/ 50", color: "bg-slate-50 border-slate-200 text-slate-700" },
                { label: "Exam", max: "/ 50", color: "bg-slate-50 border-slate-200 text-slate-700" },
              ]),
          { label: "Total", max: "/ 100", color: "bg-blue-50 border-blue-200 text-blue-700" },
        ].map(({ label, max, color }) => (
          <div key={label} className={`rounded-xl border px-4 py-3 text-center ${color}`}>
            <p className="text-[10px] font-bold uppercase tracking-widest opacity-60 mb-1">{label}</p>
            <p className="text-lg font-black font-mono">{max}</p>
          </div>
        ))}
      </div>

      {/* ── Table ── */}
      {students.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-10 text-center text-sm text-slate-400">
          No students found for this class.
        </div>
      ) : (
        <div className="rounded-2xl border border-slate-100 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" style={{ minWidth: "760px" }}>
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="py-3 px-4 text-left text-[10.5px] font-bold uppercase tracking-widest text-slate-400">Student</th>
                  {(isExamOnly(selectedClassLevel)
                    ? [{ key: "exam", label: "Exam /100" }]
                    : [
                        { key: "test1", label: "Test 1 /20" },
                        { key: "group_work", label: "Group Work /20" },
                        { key: "test2", label: "Test 2 /20" },
                        { key: "sba", label: "SBA /50" },
                        { key: "exam", label: "Exam /100" },
                        { key: "exam_score", label: "Exam /50" },
                      ]).map(({ key, label }) => (
                    <th key={key} className="py-3 px-4 text-center text-[10.5px] font-bold uppercase tracking-widest text-slate-400">{label}</th>
                  ))}
                  <th className="py-3 px-4 text-center text-[10.5px] font-bold uppercase tracking-widest text-slate-400">Total</th>
                  <th className="py-3 px-4 text-center text-[10.5px] font-bold uppercase tracking-widest text-slate-400">Grade</th>
                  <th className="py-3 px-4 text-left text-[10.5px] font-bold uppercase tracking-widest text-slate-400">Actions</th>
                </tr>
              </thead>
              <tbody>
                {students.map((s, index) => {
                  const sc = scores?.[s.id] ?? {};
                  const activeComponents = isExamOnly(selectedClassLevel)
                    ? [SBA_COMPONENTS[3]]
                    : SBA_COMPONENTS;
                  const rowFilled = activeComponents.some(({ key }) => sc[key] !== "");
                  const saved = Boolean(existingIds[s.id]);
                  const metrics = scoreResult(sc, selectedClassLevel);
                  const total = metrics.total;
                  const grade = rowFilled ? gradeFromTotal(total, selectedClassLevel) : null;
                  const avatarColor = AVATAR_COLORS[index % AVATAR_COLORS.length];
                  const gradeChip = rowFilled
                    ? saved
                      ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                      : "bg-amber-50 text-amber-700 border border-amber-200"
                    : "bg-slate-100 text-slate-400";

                  return (
                    <tr
                      key={s.id}
                      className={`border-t border-slate-100 transition-colors hover:bg-slate-50 ${rowFilled && !saved ? "bg-amber-50/30" : ""}`}
                    >
                      {/* Student */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-3">
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${avatarColor}`}>
                            {getInitials(s.student_name || s.name)}
                          </div>
                          <div>
                            <p className="font-semibold text-slate-800 text-[13px]">{s.student_name || s.name}</p>
                            <p className={`text-[11px] font-semibold mt-0.5 ${saved ? "text-emerald-600" : rowFilled ? "text-amber-600" : "text-slate-400"}`}>
                              {saved ? "✓ Saved" : rowFilled ? "Draft" : "No entry yet"}
                            </p>
                          </div>
                        </div>
                      </td>

                      {/* Scores */}
                      {activeComponents.slice(0, isExamOnly(selectedClassLevel) ? 1 : 3).map(({ key, label, max }) => (
                        <td key={key} className="py-3.5 px-2 text-center">
                          <input
                            type="number"
                            min="0"
                            max={max}
                            step="0.1"
                            aria-label={`${label} score for ${s.student_name || s.name}`}
                            value={sc[key] ?? ""}
                            onChange={(event) => {
                              const value = event.target.value;
                              if (value === "" || (Number(value) >= 0 && Number(value) <= max)) {
                                onScoreChange(s.id, key, value);
                              }
                            }}
                            className="w-20 rounded-lg border border-slate-200 bg-white px-2 py-2 text-center font-mono text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
                          />
                        </td>
                      ))}
                      {!isExamOnly(selectedClassLevel) && (
                        <>
                          <td className="py-3.5 px-4 text-center font-mono text-slate-600">{rowFilled ? metrics.sba.toFixed(1) : "—"}</td>
                          <td className="py-3.5 px-2 text-center">
                            <input
                              type="number" min="0" max="100" step="0.1"
                              aria-label={`Exam score for ${s.student_name || s.name}`}
                              value={sc.exam ?? ""}
                              onChange={(event) => {
                                const value = event.target.value;
                                if (value === "" || (Number(value) >= 0 && Number(value) <= 100)) {
                                  onScoreChange(s.id, "exam", value);
                                }
                              }}
                              className="w-20 rounded-lg border border-slate-200 bg-white px-2 py-2 text-center font-mono text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
                            />
                          </td>
                          <td className="py-3.5 px-4 text-center font-mono text-slate-600">{rowFilled ? metrics.examScore.toFixed(1) : "—"}</td>
                        </>
                      )}

                      {/* Total */}
                      <td className="py-3.5 px-4 text-center">
                        {rowFilled ? (
                          <span className="text-base font-black text-blue-600 font-mono">{total.toFixed(1)}</span>
                        ) : (
                          <span className="text-slate-300 text-sm">—</span>
                        )}
                      </td>

                      {/* Grade */}
                      <td className="py-3.5 px-4 text-center">
                        <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-bold ${gradeChip}`}>
                          {grade ?? "—"}
                        </span>
                      </td>

                      {/* Actions */}
                      <td className="py-3.5 px-4">
                        <div className="flex flex-wrap gap-1.5">
                          <button
                            onClick={() => onDelete(s.id)}
                            disabled={!saved || deleting}
                            className="px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-red-200 bg-white text-red-500 hover:bg-red-50 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Footer ── */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pt-2 border-t border-slate-100">
        <p className="text-xs text-slate-400">
          Enter marks directly in the table; SBA and totals recalculate as you type.
        </p>
        <button
          onClick={onSubmit}
          disabled={saving || filledCount === 0}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-emerald-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17 3H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V7l-4-4z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M17 21v-8H7v8M7 3v4h8" />
          </svg>
          {saving ? "Saving…" : `Save ${filledCount} result${filledCount !== 1 ? "s" : ""}`}
        </button>
      </div>

    </div>
  );
};

export default ResultsTab;
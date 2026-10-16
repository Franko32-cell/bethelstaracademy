// src/pages/student/tabs/AttendanceTab.jsx

import React from "react";
import { Empty, Loading } from "../components/Ui";
import { TERMS } from "../constants";

const AttendanceTab = ({ attendance, stats, loading, selectedTerm }) => {
  if (loading) return <Loading text="Loading attendance records…" />;

  // Late counts as attended; excused days are left out of the rate entirely.
  const rate = stats.total > 0 ? Math.round(((stats.present + stats.late) / stats.total) * 100) : 0;
  const rateColor = rate >= 80 ? "#16a34a" : rate >= 60 ? "#d97706" : "#dc2626";

  return (
    <>
      <div className="sp-att-grid">
        <div className="sp-att-kpi sp-att-present">
          <div className="sp-att-kpi-val">{stats.present}</div>
          <div className="sp-att-kpi-lbl">Present</div>
        </div>
        <div className="sp-att-kpi sp-att-absent">
          <div className="sp-att-kpi-val">{stats.absent}</div>
          <div className="sp-att-kpi-lbl">Absent</div>
        </div>
        <div className="sp-att-kpi sp-att-late">
          <div className="sp-att-kpi-val">{stats.late}</div>
          <div className="sp-att-kpi-lbl">Late</div>
        </div>
      </div>

      {stats.total > 0 && (
        <div className="sp-card" style={{ marginBottom: "14px" }}>
          <div className="sp-card-head">
            <span className="sp-card-title">Attendance Rate</span>
            <span style={{ fontFamily: "'DM Mono',monospace", fontWeight: "800", fontSize: "15px", color: rateColor }}>{rate}%</span>
          </div>
          <div style={{ padding: "12px 18px 16px" }}>
            <div className="sp-progress-bar">
              <div className="sp-progress-fill" style={{ width: `${rate}%`, background: rateColor }} />
            </div>
            <p style={{ fontSize: "11.5px", color: "#94a3b8", marginTop: "5px" }}>
              {stats.present + stats.late} of {stats.total} school days attended{stats.late > 0 ? ` (${stats.late} late)` : ""}
              {stats.excused > 0 ? ` · ${stats.excused} excused, not counted` : ""}
            </p>
          </div>
        </div>
      )}

      {attendance.length === 0
        ? <Empty icon="📋" title="No attendance records yet" sub="Your teacher's attendance records will appear here." />
        : (
          <div className="sp-card">
            <div className="sp-card-head">
              <span className="sp-card-title">Daily Attendance — {TERMS.find((t) => t.value === selectedTerm)?.label}</span>
              <span style={{ fontSize: "12px", color: "#94a3b8" }}>{attendance.length} days recorded</span>
            </div>
            <div className="sp-table-wrap">
              <table className="sp-table">
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", padding: "10px 14px" }}>#</th>
                    <th style={{ textAlign: "left", padding: "10px 14px" }}>Date</th>
                    <th className="c">Day</th>
                    <th className="c">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {attendance.map((rec, i) => {
                    const d = new Date(rec.date);
                    const day = d.toLocaleDateString("en-GH", { weekday: "short" });
                    const dateStr = d.toLocaleDateString("en-GH", { day: "numeric", month: "short", year: "numeric" });
                    const PILL = { present: "sp-att-present-pill", absent: "sp-att-absent-pill", late: "sp-att-late-pill", excused: "sp-att-excused-pill" };
                    const LABEL = { present: "✓ Present", absent: "✕ Absent", late: "⚠ Late", excused: "✎ Excused" };
                    const statusClass = PILL[rec.status] || "sp-att-late-pill";
                    const statusLabel = LABEL[rec.status] || rec.status;
                    return (
                      <tr key={rec.id ?? i}>
                        <td style={{ color: "#94a3b8", fontSize: "12px" }}>{i + 1}</td>
                        <td style={{ fontWeight: "600", color: "#1e293b" }}>{dateStr}</td>
                        <td className="c" style={{ color: "#94a3b8", fontSize: "12px" }}>{day}</td>
                        <td className="c"><span className={`sp-att-pill ${statusClass}`}>{statusLabel}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
    </>
  );
};

export default AttendanceTab;
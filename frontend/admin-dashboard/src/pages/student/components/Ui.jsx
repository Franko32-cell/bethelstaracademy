// src/pages/student/components/Ui.jsx

import React from "react";
import { GRADE_REMARK } from "../constants";
import { isExamOnly, scoreResult } from "../../../utils/sbaScoring";

export const GradeBadge = ({ grade }) => {
  const c = GRADE_REMARK[grade];
  return (
    <span className="sp-badge" style={c ? { background: c.bg, color: c.color } : { background: "#f1f5f9", color: "#64748b" }}>
      {grade ?? "—"}
    </span>
  );
};

export const RemarkBadge = ({ grade }) => {
  const c = GRADE_REMARK[grade];
  return (
    <span className="sp-badge" style={c ? { background: c.bg, color: c.color, fontWeight: 500, fontFamily: "'Outfit',sans-serif" } : { background: "#f1f5f9", color: "#94a3b8" }}>
      {c?.label ?? "—"}
    </span>
  );
};

export const KpiCard = ({ label, value, sub }) => (
  <div className="sp-kpi">
    <div className="sp-kpi-value">{value ?? "—"}</div>
    {sub && <div className="sp-kpi-sub">{sub}</div>}
    <div className="sp-kpi-label">{label}</div>
  </div>
);

export const Empty = ({ icon, title, sub }) => (
  <div className="sp-empty">
    <div className="sp-empty-icon">{icon}</div>
    <h3>{title}</h3>
    {sub && <p>{sub}</p>}
  </div>
);

export const Loading = ({ text = "Loading…" }) => (
  <div className="sp-loading"><div className="sp-spinner" />{text}</div>
);

export const EyeIcon = ({ open }) =>
  open ? (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ) : (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );

export const RefreshIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
    <polyline points="23 4 23 10 17 10" />
    <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
  </svg>
);

export const SubjectTable = ({ report }) => (
  <div className="sp-card">
    <div className="sp-table-wrap">
      <table className="sp-table">
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "10px 14px" }}>Subject</th>
            {isExamOnly(report.level) ? (
              <th className="c">Exam<br /><span style={{ fontSize: "9px", fontWeight: 400, textTransform: "none" }}>/ 100</span></th>
            ) : (
              <>
                <th className="c">Test 1<br /><span style={{ fontSize: "9px", fontWeight: 400, textTransform: "none" }}>/ 20</span></th>
                <th className="c">Group Work<br /><span style={{ fontSize: "9px", fontWeight: 400, textTransform: "none" }}>/ 20</span></th>
                <th className="c">Test 2<br /><span style={{ fontSize: "9px", fontWeight: 400, textTransform: "none" }}>/ 20</span></th>
                <th className="c">SBA<br /><span style={{ fontSize: "9px", fontWeight: 400, textTransform: "none" }}>/ 50</span></th>
                <th className="c">Exam<br /><span style={{ fontSize: "9px", fontWeight: 400, textTransform: "none" }}>/ 50</span></th>
              </>
            )}
            <th className="c">Total<br /><span style={{ fontSize: "9px", fontWeight: 400, textTransform: "none" }}>/ 100</span></th>
            {report.show_position && <th className="c">Pos</th>}
            <th className="c">Grade</th>
            <th className="c">Remark</th>
          </tr>
        </thead>
        <tbody>
          {report.subjects?.map((sub, i) => {
            const metrics = scoreResult(sub, report.level);
            return (
            <tr key={i}>
              <td style={{ fontWeight: "600", color: "#1e293b" }}>{sub.subject}</td>
              {isExamOnly(report.level) ? (
                <td className="c"><span className="sp-muted" style={{ fontFamily: "'DM Mono',monospace" }}>{sub.exam ?? "—"}</span></td>
              ) : (
                <>
                  <td className="c"><span className="sp-muted" style={{ fontFamily: "'DM Mono',monospace" }}>{sub.test1 ?? "—"}</span></td>
                  <td className="c"><span className="sp-muted" style={{ fontFamily: "'DM Mono',monospace" }}>{sub.group_work ?? "—"}</span></td>
                  <td className="c"><span className="sp-muted" style={{ fontFamily: "'DM Mono',monospace" }}>{sub.test2 ?? "—"}</span></td>
                  <td className="c"><span className="sp-muted" style={{ fontFamily: "'DM Mono',monospace" }}>{metrics.sba.toFixed(1)}</span></td>
                  <td className="c"><span className="sp-muted" style={{ fontFamily: "'DM Mono',monospace" }}>{metrics.examScore.toFixed(1)}</span></td>
                </>
              )}
              <td className="c sp-score">{sub.score}</td>
              {report.show_position && <td className="c" style={{ fontWeight: "600", color: "#64748b" }}>{sub.subject_position ?? "—"}</td>}
              <td className="c"><GradeBadge grade={sub.grade} /></td>
              <td className="c"><RemarkBadge grade={sub.grade} /></td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  </div>
);
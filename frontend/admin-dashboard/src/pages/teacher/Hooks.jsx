// src/pages/teacher/hooks.js
//
// Four focused hooks, one per data domain.
// Each hook owns its state slice and exposes a stable API to the portal.

import { useState, useCallback, useRef } from "react";
import * as svc from "./Teacherportalservice";
import { mkDefaultCharState } from "./Helpers";
import { todayStr } from "./constants";
import { checkSchoolDay } from "../../services/schoolCalendarService";
import { apiError } from "../../utils/apiError";

// ── useTeacherData ────────────────────────────────────────────────────────
// Loads classes, subjects, and students. Resets derived state on class change.

export function useTeacherData(initialClassId = "", initialClassName = "") {
  const [classes,            setClasses]            = useState([]);
  const [subjects,           setSubjects]           = useState([]);
  const [students,           setStudents]           = useState([]);
  const [selectedClass,      setSelectedClass]      = useState(initialClassId);
  const [selectedClassName,  setSelectedClassName]  = useState(initialClassName);
  const [selectedClassLevel, setSelectedClassLevel] = useState("basic_7_9");
  const [loadingStudents,    setLoadingStudents]    = useState(false);
  const [error,              setError]              = useState("");

  // Stable ref so other callbacks can read the latest students list
  // without declaring it as a dependency (avoids stale closure loops).
  const studentsRef = useRef([]);
  studentsRef.current = students;

  const loadClasses = useCallback(async () => {
    try {
      setClasses(await svc.fetchClasses());
    } catch {
      setError("Failed to load classes.");
    }
  }, []);

  const loadSubjects = useCallback(async () => {
    try {
      setSubjects(await svc.fetchSubjects());
    } catch {
      // Subjects are non-critical; fail silently
    }
  }, []);

  const loadStudents = useCallback(async (classId) => {
    if (!classId) return;
    setLoadingStudents(true);
    try {
      const data = await svc.fetchStudents(classId);
      setStudents(data);
    } catch {
      setError("Failed to load students.");
    } finally {
      setLoadingStudents(false);
    }
  }, []);

  const changeClass = useCallback(
    (classId, allClasses) => {
      setSelectedClass(classId);
      const found = allClasses.find((c) => String(c.id) === String(classId));
      setSelectedClassName(found?.name ?? "");
      setSelectedClassLevel(found?.level ?? "basic_7_9");
      setStudents([]);
    },
    []
  );

  return {
    classes,
    subjects,
    students,
    studentsRef,
    selectedClass,
    selectedClassName,
    selectedClassLevel,
    loadingStudents,
    error,
    setError,
    loadClasses,
    loadSubjects,
    loadStudents,
    changeClass,
  };
}

// ── useAttendance ─────────────────────────────────────────────────────────

export function useAttendance() {
  const [attendance, setAttendance] = useState({});
  const [attendanceReady, setAttendanceReady] = useState(false);
  const [loading,    setLoading]    = useState(false);
  const [saving,     setSaving]     = useState(false);
  const [error,      setError]      = useState("");
  const [success,    setSuccess]    = useState("");
  const [dayInfo,    setDayInfo]    = useState(null);   // school-day check for the date
  const [recorded,   setRecorded]   = useState(false);  // attendance already saved for the date
  const savingRef = useRef(false);
  const loadRequestRef = useRef(0);

  const load = useCallback(async (classId, date, students) => {
    const requestId = ++loadRequestRef.current;
    setError("");
    setSuccess("");
    setAttendanceReady(false);
    setAttendance({});
    setDayInfo(null);
    setRecorded(false);

    if (!classId || !date || !students.length) {
      setAttendance({});
      setAttendanceReady(false);
      setLoading(false);
      return;
    }

    setLoading(true);
    const [recordsResult, calendarResult] = await Promise.allSettled([
      svc.fetchAttendance(classId, date),
      checkSchoolDay(date),
    ]);
    if (requestId !== loadRequestRef.current) return;

    if (recordsResult.status === "fulfilled") {
      const records = recordsResult.value;
      const map = Object.fromEntries(
        records.map((rec) => [String(rec.student), rec.status])
      );
      setAttendance(
        Object.fromEntries(students.map((s) => [
          s.id,
          map[String(s.id)] ?? (date === todayStr() ? "present" : null),
        ]))
      );
      setRecorded(records.length > 0);
      setAttendanceReady(true);
    } else {
      setAttendance({});
      setError(apiError(recordsResult.reason, "Failed to load attendance records."));
    }

    if (calendarResult.status === "fulfilled") {
      setDayInfo(calendarResult.value);
    } else {
      setDayInfo(null);
      setError((current) => current || apiError(
        calendarResult.reason,
        "Could not check whether this date is a school day."
      ));
    }
    setLoading(false);
  }, []);

  const toggle = useCallback((id, status) => {
    const cycle = { present: "absent", absent: "late", late: "excused", excused: "present" };
    setAttendance((prev) => ({
      ...prev,
      [id]: status ?? cycle[prev[id]] ?? "present",
    }));
  }, []);

  const markAll = useCallback((status) => {
    setAttendance((prev) =>
      Object.fromEntries(Object.keys(prev).map((id) => [id, status]))
    );
  }, []);

  const save = useCallback(async (classId, date, students, todayStr) => {
    if (!classId || !date || !students.length) {
      setError("Select a class, date, and at least one student before saving.");
      return;
    }
    if (date > todayStr) {
      setError("Cannot record attendance for a future date.");
      return;
    }
    if (loading) {
      setError("Attendance is still loading. Please wait before saving.");
      return;
    }
    if (!dayInfo || dayInfo.date !== date) {
      setError("School-day status is unavailable for this date. Please retry loading attendance.");
      return;
    }
    if (!dayInfo.is_school_day) {
      setError("Attendance cannot be recorded because this date is a non-school day.");
      return;
    }
    if (!attendanceReady) {
      setError("Attendance has not loaded. Please retry before saving.");
      return;
    }
    if (!Object.values(attendance).some((status) => status)) {
      setError("Choose a status for at least one student before saving.");
      return;
    }
    if (savingRef.current) return; // ignore double-clicks / duplicate submissions
    savingRef.current = true;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const { saved, failed, skipped, firstError } = await svc.saveAttendance(classId, date, students, attendance);
      if (failed > 0) {
        setError(`${saved} record(s) saved, ${failed} failed${skipped ? `, ${skipped} skipped` : ""}. ${firstError || "Please try again."}`);
        if (saved > 0) setRecorded(true);
      } else {
        setRecorded(true);
        setSuccess(skipped
          ? `Attendance saved. ${skipped} student(s) without a status were skipped.`
          : "Attendance saved successfully.");
      }
    } catch (e) {
      setError(apiError(e, "Failed to save attendance."));
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }, [attendance, attendanceReady, dayInfo, loading]);

  const reset = useCallback(() => {
    loadRequestRef.current += 1;
    setAttendance({});
    setAttendanceReady(false);
    setLoading(false);
    setSaving(false);
    setError("");
    setSuccess("");
    setDayInfo(null);
    setRecorded(false);
  }, []);

  return {
    attendance,
    attendanceReady,
    loading,
    saving,
    error,
    success,
    dayInfo,
    recorded,
    setError,
    setSuccess,
    load,
    toggle,
    markAll,
    save,
    reset,
  };
}

// ── useResults ────────────────────────────────────────────────────────────

export function useResults() {
  const [scores,      setScores]      = useState({});
  const [breakdowns,  setBreakdowns]  = useState({});
  const [existingIds, setExistingIds] = useState({});
  const [saving,      setSaving]      = useState(false);
  const [deleting,    setDeleting]    = useState(null);
  const [error,       setError]       = useState("");
  const [success,     setSuccess]     = useState("");

  const load = useCallback(async (classId, term, subjectId, year, students) => {
    if (!classId || !term || !subjectId || !students.length) return;
    try {
      const records   = await svc.fetchResults(classId, term, subjectId, year);
      const serverMap = Object.fromEntries(
        records.map((rec) => [
          String(rec.student),
          { reopen: rec.reopen, ca: rec.ca, exams: rec.exams },
        ])
      );
      const idMap = Object.fromEntries(records.map((rec) => [rec.student, rec.id]));

      setScores(
        Object.fromEntries(
          students.map((s) => [
            s.id,
            serverMap[String(s.id)] ?? { reopen: "", ca: "", exams: "" },
          ])
        )
      );
      setExistingIds(idMap);
    } catch {
      // Silent — caller shows an error if needed
    }
  }, []);

  const applyScore = useCallback((studentId, field, score, breakdown) => {
    setScores((prev) => ({
      ...prev,
      [studentId]: { ...(prev[studentId] || {}), [field]: score },
    }));
    setBreakdowns((prev) => ({
      ...prev,
      [studentId]: { ...(prev[studentId] || {}), [field]: breakdown },
    }));
  }, []);

  const submitAll = useCallback(
    async (classId, term, subjectId, year, students) => {
      const records = Object.entries(scores)
        .filter(([, v]) => v.reopen !== "" || v.ca !== "" || v.exams !== "")
        .map(([sid, v]) => ({
          student:      sid,
          subject:      subjectId,
          school_class: classId,
          term,
          year,
          reopen: parseFloat(v.reopen) || 0,
          ca:     parseFloat(v.ca)     || 0,
          exams:  parseFloat(v.exams)  || 0,
        }));

      if (!records.length) {
        setError("No scores entered.");
        return false;
      }

      setSaving(true);
      setError("");
      try {
        const data = await svc.saveResults(records);
        if (data.errors?.length > 0) {
          setError(`${data.saved} saved, ${data.errors.length} failed. Check scores and try again.`);
        } else {
          setSuccess(`Saved ${data.saved} result(s) successfully.`);
          // Reload from server so existingIds reflects what was just saved
          await load(classId, term, subjectId, year, students);
        }
        return true;
      } catch (err) {
        const detail = err.response?.data?.detail || err.response?.data?.error;
        setError(detail || "Error saving results. Please try again.");
        return false;
      } finally {
        setSaving(false);
      }
    },
    [scores, load]
  );

  const deleteOne = useCallback(async (studentId) => {
    const id = existingIds[studentId];
    if (!id) return;
    setDeleting(studentId);
    try {
      await svc.deleteResult(id);
      setScores((prev)      => ({ ...prev,      [studentId]: { reopen: "", ca: "", exams: "" } }));
      setExistingIds((prev) => { const n = { ...prev }; delete n[studentId]; return n; });
      setBreakdowns((prev)  => { const n = { ...prev }; delete n[studentId]; return n; });
      setSuccess("Result deleted.");
    } catch {
      setError("Failed to delete result.");
    } finally {
      setDeleting(null);
    }
  }, [existingIds]);

  const reset = useCallback(() => {
    setScores({});
    setBreakdowns({});
    setExistingIds({});
  }, []);

  return {
    scores,
    breakdowns,
    existingIds,
    saving,
    deleting,
    error,
    success,
    setError,
    setSuccess,
    load,
    applyScore,
    submitAll,
    deleteOne,
    reset,
  };
}

// ── useCharAssessment ─────────────────────────────────────────────────────

export function useCharAssessment() {
  // charForms caches one form state object per student id
  const [charForms,       setCharForms]       = useState({});
  const [charStudentId,   setCharStudentId]   = useState("");
  const [charExtraSkills, setCharExtraSkills] = useState([]);
  const [loading,         setLoading]         = useState(false);
  const [saving,          setSaving]          = useState(false);
  const [saved,           setSaved]           = useState(false);
  const [error,           setError]           = useState("");
  const [success,         setSuccess]         = useState("");

  // Active form for the current student (or a blank default)
  const form = charForms[charStudentId] ?? mkDefaultCharState();

  // ── Internal form updater ─────────────────────────────────────────────
  const updateForm = useCallback((studentId, updater) => {
    setCharForms((prev) => ({
      ...prev,
      [studentId]:
        typeof updater === "function"
          ? updater(prev[studentId] ?? mkDefaultCharState())
          : updater,
    }));
    setSaved(false);
  }, []);

  // ── Load ──────────────────────────────────────────────────────────────
  // BUG FIX: the original had `charForms` in the dependency array of
  // loadCharAssessment, causing it to re-run every time any form field changed
  // (infinite re-fetch risk). We use a ref to check the cache instead.
  const charFormsRef = useRef({});
  charFormsRef.current = charForms;

  const load = useCallback(async (studentId, term, year) => {
    if (!studentId) return;
    // Skip if already fetched for this student (cache hit)
    if (charFormsRef.current[studentId]) return;

    setLoading(true);
    try {
      const data = await svc.fetchCharAssessment(studentId, term, year);
      if (data) {
        setCharForms((prev) => ({
          ...prev,
          [studentId]: { ...mkDefaultCharState(), ...data },
        }));
      }
      // If null (no saved record), the blank default form is used automatically
    } catch {
      // First-time form — keep defaults, stay silent
    } finally {
      setLoading(false);
    }
  }, []); // No dependency on charForms — uses ref instead

  // ── Save ──────────────────────────────────────────────────────────────
  const save = useCallback(
    async (classId, term, year) => {
      if (!charStudentId) return;
      setSaving(true);
      setError("");
      setSaved(false);
      try {
        await svc.saveCharAssessment(charStudentId, classId, term, year, form);
        setSaved(true);
        setSuccess("Character assessment saved successfully.");
        setTimeout(() => setSaved(false), 3000);
      } catch {
        setError("Failed to save character assessment. Please try again.");
      } finally {
        setSaving(false);
      }
    },
    [charStudentId, form]
  );

  // ── Field updaters (stable, no re-render of unrelated components) ─────
  const updateArea = useCallback(
    (field, subField, value) => {
      updateForm(charStudentId, (prev) => ({
        ...prev,
        areas: {
          ...prev.areas,
          [field]: {
            ...(prev.areas?.[field] ?? { score: "", remarks: "" }),
            [subField]: value,
          },
        },
      }));
    },
    [charStudentId, updateForm]
  );

  const updateCareerSkill = useCallback(
    (key, subField, value) => {
      updateForm(charStudentId, (prev) => ({
        ...prev,
        career: {
          ...prev.career,
          [key]: {
            ...(prev.career?.[key] ?? { score: "", remarks: "", exam: "" }),
            [subField]: value,
          },
        },
      }));
    },
    [charStudentId, updateForm]
  );

  const updateField = useCallback(
    (field, value) => {
      updateForm(charStudentId, (prev) => ({ ...prev, [field]: value }));
    },
    [charStudentId, updateForm]
  );

  // ── Extra career skill rows ────────────────────────────────────────────
  const addExtraSkill = useCallback(() => {
    const key = `extra_${Date.now()}`;
    setCharExtraSkills((prev) => [...prev, { key, label: "", exam: "" }]);
    updateForm(charStudentId, (prev) => ({
      ...prev,
      career: { ...prev.career, [key]: { score: "", remarks: "", exam: "" } },
    }));
  }, [charStudentId, updateForm]);

  const updateExtraSkillLabel = useCallback((key, label) => {
    setCharExtraSkills((prev) =>
      prev.map((s) => (s.key === key ? { ...s, label } : s))
    );
  }, []);

  const removeExtraSkill = useCallback(
    (key) => {
      setCharExtraSkills((prev) => prev.filter((s) => s.key !== key));
      updateForm(charStudentId, (prev) => {
        const career = { ...prev.career };
        delete career[key];
        return { ...prev, career };
      });
    },
    [charStudentId, updateForm]
  );

  const selectStudent = useCallback(
    (id) => {
      setCharStudentId(id);
      setSaved(false);
    },
    []
  );

  const resetForClass = useCallback(() => {
    setCharStudentId("");
    setCharForms({});
    setSaved(false);
    setCharExtraSkills([]);
  }, []);

  return {
    form,
    charForms,
    charStudentId,
    charExtraSkills,
    loading,
    saving,
    saved,
    error,
    success,
    setError,
    setSuccess,
    load,
    save,
    updateArea,
    updateCareerSkill,
    updateField,
    addExtraSkill,
    updateExtraSkillLabel,
    removeExtraSkill,
    selectStudent,
    resetForClass,
  };
}
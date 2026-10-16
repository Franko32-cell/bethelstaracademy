export const SBA_COMPONENTS = [
  { key: "test1", label: "Test 1", max: 20 },
  { key: "group_work", label: "Group Work", max: 20 },
  { key: "test2", label: "Test 2", max: 20 },
  { key: "exam", label: "Exam", max: 100 },
];

export const isExamOnly = (level) =>
  ["nursery_kg", "nursery", "kg"].includes(String(level || "").toLowerCase());

export const roundHalfUp = (value, digits = 1) => {
  const factor = 10 ** digits;
  return Math.floor(Number(value) * factor + 0.5 + Number.EPSILON) / factor;
};

export const scoreResult = (values = {}, level = "basic_7_9") => {
  const test1 = Number(values.test1) || 0;
  const groupWork = Number(values.group_work) || 0;
  const test2 = Number(values.test2) || 0;
  const exam = Number(values.exam) || 0;
  const examOnly = isExamOnly(level);
  const sbaRaw = roundHalfUp(test1 + groupWork + test2);
  const sba = roundHalfUp((sbaRaw / 60) * 50);
  const examScore = roundHalfUp((exam / 100) * 50);
  return {
    examOnly,
    sbaRaw,
    sba: examOnly ? 0 : sba,
    examScore: examOnly ? exam : examScore,
    total: roundHalfUp(examOnly ? exam : sba + examScore),
  };
};

export const emptyResult = () => ({
  test1: "",
  group_work: "",
  test2: "",
  exam: "",
});

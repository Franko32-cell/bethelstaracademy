// Flattens a DRF error response ({detail}, {field: [msgs]}, [msgs], string)
// into one readable sentence for display.
export const apiError = (err, fallback = "Something went wrong. Please try again.") => {
  const data = err?.response?.data;
  if (!data) return err?.message === "Network Error" ? "Network error. Check your connection." : fallback;
  if (typeof data === "string") return data.length > 300 ? fallback : data;
  if (Array.isArray(data)) return data.map(String).join(" ");
  if (data.detail) return String(data.detail);
  if (data.error) return String(data.error);
  const parts = Object.values(data).flatMap((v) => (Array.isArray(v) ? v : [v]));
  return parts.length ? parts.map(String).join(" ") : fallback;
};

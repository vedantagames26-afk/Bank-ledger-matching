export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const token = sessionStorage.getItem("recon-token");
  if (token) headers.set("X-Recon-Token", token);
  const response = await fetch("/api" + path, { ...options, headers });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Service unavailable" }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : JSON.stringify(error.detail),
    );
  }
  return response.json();
}
export async function download(path: string, name: string) {
  const headers = new Headers();
  const token = sessionStorage.getItem("recon-token");
  if (token) headers.set("X-Recon-Token", token);
  const response = await fetch("/api" + path, { headers });
  if (!response.ok) throw new Error("Download failed");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const currency = (paise: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(paise / 100);
export const label = (text: string) =>
  text.replaceAll("_", " ").replace(/\b\w/g, (s) => s.toUpperCase());

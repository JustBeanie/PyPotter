/* Generated API surface. Regenerate from the backend OpenAPI document when the contract changes. */
import type { Recognition } from "../api";

export async function postRecognition(payload: { spell?: string; image_base64?: string }): Promise<Recognition> {
  const response = await fetch("/api/v1/recognitions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail ?? body.message ?? "Recognition failed.");
  return body as Recognition;
}

export async function getRecognitions(): Promise<Recognition[]> {
  const response = await fetch("/api/v1/recognitions");
  if (!response.ok) throw new Error("History could not be loaded.");
  return ((await response.json()) as { items: Recognition[] }).items;
}

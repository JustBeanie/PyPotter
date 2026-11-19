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

export async function getSpells(): Promise<string[]> {
  const response = await fetch("/api/v1/spells");
  if (!response.ok) throw new Error("Spells could not be loaded.");
  return (await response.json()) as string[];
}

export async function postTraining(payload: { name: string; images: string[] }): Promise<{ spell: string; added: number }> {
  const response = await fetch("/api/v1/spells/train", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.message ?? body.detail ?? "Training failed.");
  return body as { spell: string; added: number };
}

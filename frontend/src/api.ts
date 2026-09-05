export type Recognition = {
  id: number;
  spell: string;
  confidence: number | null;
  source: string;
  created_at: string;
};

export { getRecognitions as history, postRecognition as recognize } from "./generated/client";

export type Recognition = {
  id: number;
  spell: string;
  confidence: number | null;
  source: string;
  created_at: string;
};

export { getRecognitions as history, getSpells as spells, postRecognition as recognize, postTraining as trainSpell } from "./generated/client";

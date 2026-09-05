import { describe, expect, it } from "vitest";
import { trainedSpells } from "./App";

describe("trained spell contract", () => {
  it("keeps the web choices aligned with the domain spell list", () => {
    expect(trainedSpells).toContain("incendio");
    expect(trainedSpells).toContain("specialis_revelio");
    expect(new Set(trainedSpells).size).toBe(trainedSpells.length);
  });
});


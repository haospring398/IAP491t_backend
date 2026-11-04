import { factorCatalogue, type ExplanationFactor } from "./contracts";
// Lời văn hiển thị explanation theo EXPERIENCE.md; ngưỡng mức độ là giả định UX (A5).
export const explanationHeading = "What the model relied on";
export const explanationNotice = "These factors describe how the model reached this result. They are not proof that the email is safe or malicious.";
export function factorText(factor: ExplanationFactor) { return factorCatalogue[factor.factor]; }
export function directionText(factor: ExplanationFactor) { return factor.direction === "positive" ? "Toward Phishing" : "Toward Legit"; }
export function strengthText(strength: number) { return strength >= 0.67 ? "Strong" : strength >= 0.34 ? "Moderate" : "Weak"; }

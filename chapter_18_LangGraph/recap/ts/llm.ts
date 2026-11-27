/** Shared LLM factory. Reads chapter_18_LangGraph/.env, same as the Python llm.py. */
import { ChatGroq } from "@langchain/groq";
import dotenv from "dotenv";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(HERE, "../../.env") });   // ts/ -> recap/ -> chapter_18

export function getLlm() {
  if (!process.env.GROQ_API_KEY) {
    throw new Error("GROQ_API_KEY is not set. Add it to chapter_18_LangGraph/.env");
  }
  return new ChatGroq({
    model: process.env.LLM_MODEL ?? "openai/gpt-oss-120b",
    temperature: 0,
  });
}

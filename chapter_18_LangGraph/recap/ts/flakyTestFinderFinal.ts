/**
 * Project (final, TypeScript) - two Playwright builds in, a triaged verdict out.
 *
 * The same graph as Project_FlakyTestFinderFinal.py. Differences are all
 * LangGraph-JS API, not design:
 *   - state is an Annotation.Root({...}) instead of a TypedDict
 *   - addConditionalEdges takes the mapping as the third argument
 *   - interrupt() throws a GraphInterrupt, so the caller checks __interrupt__
 *   - a node may NOT share a name with a state channel, so the node that
 *     fills the `triage` channel has to be called something else
 *
 *   npm run build:1 && npm run build:2
 *   npm run finder              # auto-quarantine
 *   npm run finder -- --human   # ask me first
 */
import { Annotation, Command, END, MemorySaver, START, StateGraph, interrupt }
  from "@langchain/langgraph";
import { z } from "zod";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline/promises";
import { fileURLToPath } from "node:url";
import { getLlm } from "./llm.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BUILDS = path.join(HERE, "builds");

/** 07 - structured output, so the answer is a union type and not prose. */
const Triage = z.object({
  cause: z.enum(["timing", "test_bug", "product_bug", "environment"]),
  reason: z.string().describe("one sentence"),
});
type Triage = z.infer<typeof Triage>;

/** 01 - state. Each channel replaces its old value when a node returns it. */
const State = Annotation.Root({
  runs: Annotation<Record<string, string>[]>,
  passed: Annotation<string[]>,
  flaky: Annotation<string[]>,
  broken: Annotation<string[]>,
  triage: Annotation<Triage | undefined>,
  quarantined: Annotation<string>,
  verdict: Annotation<string>,
});
type S = typeof State.State;

/** Playwright's JSON reporter nests specs one level deeper than you expect. */
function readBuild(n: number): Record<string, string> {
  const r = JSON.parse(fs.readFileSync(path.join(BUILDS, `build_${n}.json`), "utf8"));
  const specs = r.suites[0].suites?.[0]?.specs ?? r.suites[0].specs;
  return Object.fromEntries(specs.map((s: any) => [s.title, s.ok ? "passed" : "failed"]));
}

// ---------------------------------------------------------------- nodes
const loadBuilds = async (_: S) => {
  const runs = [readBuild(1), readBuild(2)];
  console.log(`loaded 2 builds, ${Object.keys(runs[0]).length} tests each`);
  return { runs };
};

/** The whole rule: compare the PAIR, never a single status. */
const compare = async (s: S) => {
  const [b1, b2] = s.runs;
  const passed: string[] = [], flaky: string[] = [], broken: string[] = [];
  for (const test of Object.keys(b1)) {
    const pair = `${b1[test]}|${b2[test]}`;
    (pair === "passed|passed" ? passed : pair === "failed|failed" ? broken : flaky)
      .push(test);
  }
  return { passed, flaky, broken };
};

/** 03 - no flaky test means no LLM call, and no spend. */
const routeAfterCompare = (s: S) => (s.flaky.length ? "triage_flaky" : "report");

/** 07 - Groq says WHY. TypeScript still decides what happens next. */
const triage = async (s: S) => {
  const [b1, b2] = s.runs;
  const test = s.flaky[0];
  const t = await getLlm().withStructuredOutput(Triage).invoke(
    "You triage flaky UI tests. One sentence.\n" +
    `Test: ${test}\nBuild 1: ${b1[test]}   Build 2: ${b2[test]}\n` +
    "It asserts the product grid has 6 items after login.");
  console.log(`groq: ${t.cause} - ${t.reason}`);
  return { triage: t };
};

/** 03 again - the --human flag picks the lane. */
const routeQuarantine = (_: S) =>
  process.argv.includes("--human") ? "ask_human" : "quarantine";

/** 06 - interrupt() freezes the graph until someone answers. */
const askHuman = async (s: S) => {
  const answer = interrupt({ question: `Quarantine ${s.flaky[0]}?`, cause: s.triage?.cause });
  return { quarantined: String(answer).toLowerCase().startsWith("y") ? s.flaky[0] : "" };
};

const quarantine = async (s: S) => ({ quarantined: s.flaky[0] });

const report = async (s: S) => {
  const [b1, b2] = s.runs;
  const label: Record<string, string> = {};
  s.passed.forEach(t => (label[t] = "PASSED"));
  s.flaky.forEach(t => (label[t] = "FLAKY"));
  s.broken.forEach(t => (label[t] = "BROKEN"));

  const rows = ["TEST".padEnd(22) + "BUILD 1".padEnd(9) + "BUILD 2".padEnd(9) + "VERDICT",
                "-".repeat(54)];
  for (const t of Object.keys(b1)) {
    rows.push(t.padEnd(22) + b1[t].padEnd(9) + b2[t].padEnd(9) + label[t]);
  }
  rows.push("", `${s.passed.length} passed, ${s.flaky.length} flaky, ${s.broken.length} broken`);
  if (s.triage) rows.push(`cause: ${s.triage.cause} - ${s.triage.reason}`);
  rows.push(s.quarantined ? `quarantined: ${s.quarantined}` : "quarantined: nothing");
  return { verdict: rows.join("\n") };
};

// ---------------------------------------------------------------- graph
const app = new StateGraph(State)
  .addNode("load_builds", loadBuilds)
  .addNode("compare", compare)
  .addNode("triage_flaky", triage)
  .addNode("ask_human", askHuman)
  .addNode("quarantine", quarantine)
  .addNode("report", report)
  .addEdge(START, "load_builds")
  .addEdge("load_builds", "compare")
  .addConditionalEdges("compare", routeAfterCompare, ["triage_flaky", "report"])
  .addConditionalEdges("triage_flaky", routeQuarantine, ["ask_human", "quarantine"])
  .addEdge("ask_human", "report")
  .addEdge("quarantine", "report")
  .addEdge("report", END)
  .compile({ checkpointer: new MemorySaver() });   // 05 - interrupt needs it

const cfg = { configurable: { thread_id: "flaky-final-ts" } };
let out = await app.invoke({}, cfg);

if ((out as any).__interrupt__) {                   // 06 - paused, ask and resume
  const q = (out as any).__interrupt__[0].value;
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const answer = await rl.question(`\n${q.question} (cause: ${q.cause}) [y/N]: `);
  rl.close();
  out = await app.invoke(new Command({ resume: answer }), cfg);
}

console.log(`\n${out.verdict}`);

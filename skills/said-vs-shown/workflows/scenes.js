export const meta = {
  name: 'svs-scenes',
  description: 'Said vs. Shown: build bespoke scenes (receipt scenes with per-story illustrations) in parallel against the design system and word timings',
  phases: [{ title: 'Build', detail: '2–3 scenes per worker, one wave' }],
}
// args: { project: "<abs episode>/video", skill: "<abs skill dir>",
//         jobs: [{ key: "ui-receipt", files: "compositions/05-ui-receipt.html", scene_id: "ui-receipt", prefix: "ur-", spec: "what this scene shows, beat by beat" }] }
// Without the Workflow tool: the same brief is in references/scenes.md ("Receipt scene brief"); run it as one subagent per job, or one job after another.
const A = args || {}
const COMMON = `You build HyperFrames sub-composition scenes for a Said vs. Shown episode. Project: ${A.project}.
READ FIRST: ${A.project}/frame.md (design truth) · ${A.skill}/references/editorial.md · ${A.skill}/templates/scenes/receipt.html (canonical receipt pattern: CFG block, browser frame, coordinate-target-zoom, synced highlighter, ILLUSTRATION slot) · ${A.project}/audio/scene-words.json (your scene's LOCAL word timings — sync every beat to them) · the hyperframes-core skill's SKILL.md and references/sub-compositions.md (where to find it: "HyperFrames knowledge" in ${A.skill}/SKILL.md).
CONTRACT: <template> wrapper with <style>/<script> inside; root <div id="root" data-composition-id="<SCENE_ID>" data-width="1920" data-height="1080">; one paused GSAP timeline registered last on window.__timelines["<SCENE_ID>"]; ids prefixed; CSS selectors prefixed [data-composition-id="<SCENE_ID>"]; no Math.random/Date.now/network; no CSS transform on GSAP-transformed elements (use fromTo); caption band y 920–1080 stays empty; text ≥18px.
TRUTH: on-screen words come from the narration, the ledger quotes or the spec; illustrations carry a visible ILLUSTRATION tag and are never presented as a product's real output.
Edit only your file(s). Validate with \`npx -y hyperframes@<version in ${A.skill}/engine/config.json> lint ${A.project}\` and fix your findings. Return the file(s), a beat table (local time → visual → synced words) and concerns.`
phase('Build')
const out = await parallel((A.jobs || []).map(j => () => agent(`${COMMON}\n\nYOUR SCENE: ${j.files} — SCENE_ID "${j.scene_id}", prefix "${j.prefix}".\n${j.spec}`, { label: `scene:${j.key}`, phase: 'Build' }).then(r => ({ key: j.key, report: r }))))
return out.filter(Boolean)

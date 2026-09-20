import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".boot")).toHaveCount(0, { timeout: 15_000 });
});

test.afterEach(async ({ request }) => {
  const workspaces = await (await request.get("/api/v1/workspaces")).json() as Array<{ id: string }>;
  for (const workspace of workspaces) {
    const teams = await (await request.get(`/api/v1/teams?workspace_id=${workspace.id}`)).json() as Array<{ id: string }>;
    for (const team of teams) {
      const runs = await (await request.get(`/api/v1/runs?team_id=${team.id}`)).json() as Array<{ id: string; goal: string }>;
      for (const run of runs.filter(item => item.goal.startsWith("E2E product journey"))) {
        await request.delete(`/api/v1/runs/${run.id}`);
      }
    }
  }
});

test("main navigation and explicit agent selection work", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "What will we create today?" })).toBeVisible();
  await page.locator(".agentselect").click();
  await page.locator(".agentpickergrid > button").nth(0).click();
  await page.locator(".agentpickergrid > button").nth(1).click();
  await expect(page.locator(".agentselect")).toContainText("2 agents");
  const goal = `E2E product journey ${Date.now()}`;
  await page.getByPlaceholder("Describe a task for your agent team…").fill(goal);
  await page.locator(".sendround").click();
  await expect(page.getByRole("heading", { name: "Dialogue" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(goal, { exact: true }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".tasklabel")).toContainText("CURRENT TURN · 2/2", { timeout: 30_000 });
  await expect(page.locator(".minitask")).toHaveCount(2);
  await expect(page.locator(".runleft")).not.toContainText("TASKS ·");
});

test("new chat accepts material context and exposes clear attachment feedback", async ({ page }) => {
  const input = page.locator(".attachbutton input[type=file]");
  await input.setInputFiles({ name: "launch-brief.md", mimeType: "text/markdown", buffer: Buffer.from("# Launch brief\nTarget: creators") });
  await expect(page.locator(".materialchips")).toContainText("launch-brief.md");
  await expect(page.locator(".attachbutton")).toContainText("1 material");
  await expect(page.locator(".attachbutton")).toHaveClass(/has-files/);
  await page.getByRole("button", { name: "Remove launch-brief.md" }).click();
  await expect(page.locator(".materialchips")).toHaveCount(0);
});

test("new chat exposes useful team context without invented provider budgets", async ({ page }) => {
  const summary = page.locator(".sessionbrief-trigger");
  await expect(summary).toBeVisible();
  await expect(summary).toContainText(/Team context|Build your team/);
  await expect(summary).not.toContainText("$");
  await summary.click();
  await expect(page.locator(".sessionbrief-pop")).toBeVisible();
  await expect(page.getByText("Launch context", { exact: true })).toBeVisible();
  await expect(page.locator(".sessionbrief-pop")).toContainText(/memory/i);
});

test("dialogue history filters and opens a selected dialogue", async ({ page }) => {
  await expect(page.locator(".historylist")).toHaveCount(0);
  await page.getByRole("button", { name: "Workflows" }).first().click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  const cards = page.locator(".dialoguelist article");
  await expect(cards.first()).toBeVisible();
  const goal = (await cards.first().locator("h3").textContent())?.trim() || "";
  const search = page.getByPlaceholder("Search conversations");
  await search.fill(goal.slice(0, 12));
  await expect(cards.first()).toContainText(goal);
  await search.fill("definitely-non-existent-dialogue");
  await expect(page.getByText("Nothing found")).toBeVisible();
  await search.fill("");
  await cards.first().click();
  await expect(page.getByRole("heading", { name: "Dialogue" })).toBeVisible();
});

test("dialogue deletion is confirmed inside Orbit", async ({ page }) => {
  await page.getByRole("button", { name: "Workflows" }).first().click();
  const dialogue = page.locator(".historylist button").first();
  await dialogue.click({ button: "right" });
  await page.getByRole("button", { name: "Delete dialogue" }).click();
  const modal = page.getByRole("alertdialog");
  await expect(modal).toBeVisible();
  await expect(modal).toContainText("Delete this dialogue?");
  await modal.getByRole("button", { name: "Cancel" }).click();
  await expect(modal).toHaveCount(0);
});

test("a completed dialogue accepts follow-up instructions", async ({ page }) => {
  test.setTimeout(60_000);
  await page.getByRole("button", { name: "Workflows" }).first().click();
  const firstHistory = page.locator(".historylist button").first();
  await expect(firstHistory).toBeVisible();
  await firstHistory.click();
  await expect(page.getByRole("heading", { name: "Dialogue" })).toBeVisible();
  const composer = page.locator(".composer textarea");
  await expect(composer).toBeVisible();
  const followUp = `E2E follow-up ${Date.now()}`;
  await composer.fill(followUp);
  await page.locator(".composer button.primary").click({ force: true });
  await expect(page.locator(".eventbody p").filter({ hasText: followUp }).first()).toBeVisible({ timeout: 15_000 });
  await expect(composer).toHaveValue("");
  await expect(page.getByText("Cannot message a completed run")).toHaveCount(0);
});

test("a message remains visible while the live event stream reconnects", async ({ page }) => {
  test.setTimeout(60_000);
  await page.route(/\/api\/v1\/runs\/[^/]+\/stream/, (route) => route.abort("connectionrefused"));
  await page.getByRole("button", { name: "Workflows" }).first().click();
  await page.locator(".historylist button").first().click();
  await expect(page.getByRole("heading", { name: "Dialogue" })).toBeVisible();
  await expect(page.locator(".statusbar")).toContainText("Reconnecting", { timeout: 15_000 });

  const composer = page.locator(".composer textarea");
  const message = `E2E reconnect message ${Date.now()}`;
  await composer.fill(message);
  await composer.press("Enter");

  const rendered = page.locator(".eventbody p").filter({ hasText: message });
  await expect(rendered).toHaveCount(1, { timeout: 15_000 });
  await expect(rendered).toBeVisible();
  await expect(composer).toHaveValue("");
});

test("dialogue supports live result, fork/rewind, and speaking as an agent", async ({ page }) => {
  test.setTimeout(60_000);
  await page.getByRole("button", { name: "Workflows" }).first().click();
  await page.locator(".historylist button").first().click();
  await expect(page.getByRole("heading", { name: "Dialogue" })).toBeVisible();

  await page.getByTitle("Live result").click();
  await expect(page.locator(".resultpanel")).toBeVisible();
  await expect(page.locator(".resulttabs")).toContainText("Artifact");
  await page.locator(".resultpanel > header button").click();

  const branchable = page.locator(".event").filter({ has: page.locator(".eventactions") }).first();
  await branchable.getByTitle("Fork from here").click({ force: true });
  await expect(page.getByRole("heading", { name: "Change the team path" })).toBeVisible();
  await expect(page.locator(".branchchoice")).toContainText("Keep both branches");
  await page.locator(".branchmodal footer button").first().click({ force: true });
  await expect(page.locator(".branchmodal")).toHaveCount(0);

  await page.locator(".commandselect").selectOption("speak_as");
  await expect(page.locator(".composer textarea")).toHaveAttribute("placeholder", "The message will appear as the selected agent…");
  expect(await page.locator(".composer select").nth(1).locator("option").allTextContents()).not.toContain("@all");
  await expect(page.locator(".statusbar .telemetry")).toContainText("tools");
});

test("automation is opt-in and scoped to the current dialogue", async ({ page }) => {
  await page.getByRole("button", { name: "Workflows" }).first().click();
  await page.locator(".historylist button").first().click();
  await expect(page.getByRole("heading", { name: "Dialogue" })).toBeVisible();
  await page.getByTitle("Automation for this dialogue only").click();
  await expect(page.getByRole("heading", { name: "Automation for this dialogue" })).toBeVisible();
  const toggle = page.getByRole("switch");
  if ((await toggle.getAttribute("aria-checked")) === "false") {
    await expect(page.getByText("Regular dialogue", { exact: true })).toBeVisible();
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked", "true");
    await expect(page.locator(".automationeditor")).toBeVisible();
    await expect(page.getByRole("button", { name: "Launch automation" })).toBeEnabled();
  } else {
    await expect(page.locator(".automationeditor")).toBeVisible();
    await expect(page.getByText("Automation is running", { exact: true })).toBeVisible();
  }
});

test("shared replay plays the visible team decision timeline", async ({ page, request }) => {
  const workspaces = await (await request.get("/api/v1/workspaces")).json() as Array<{id:string}>;
  const teams = await (await request.get(`/api/v1/teams?workspace_id=${workspaces[0].id}`)).json() as Array<{id:string}>;
  const runs = await (await request.get(`/api/v1/runs?team_id=${teams[0].id}`)).json() as Array<{id:string}>;
  const shared = await (await request.post(`/api/v1/runs/${runs[0].id}/share`)).json() as {token:string};
  await page.goto(`/?replay=${encodeURIComponent(shared.token)}`);
  await expect(page.getByText("PUBLIC TEAM REPLAY")).toBeVisible();
  await expect(page.getByRole("button", { name: "Fork this team" })).toBeVisible();
  await expect(page.locator(".replayteam > span").first()).toBeVisible();
  await expect(page.locator(".replaycontrols")).toBeVisible();
  await page.locator(".replaycontrols .play").click();
});

test("Memory exposes the graph, note selection, editing, and portable export", async ({ page }) => {
  await page.getByRole("button", { name: "Memory" }).click();
  await expect(page.getByRole("heading", { name: "Memory" })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^orbit-memory-\d{4}-\d{2}-\d{2}\.md$/);
  await expect(page.locator(".memorynode.core")).toBeVisible();
  await expect(page.locator(".memorynode.dialogue").first()).toBeVisible();
  await page.locator(".memorynode.dialogue").first().click({ force: true });
  await expect(page.locator(".memorynote.open")).toBeVisible();
  await page.getByRole("button", { name: "Edit note" }).click();
  await expect(page.locator(".memorynote textarea")).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.locator(".memorynote textarea")).toHaveCount(0);
});

test("one persistent skill can be assigned to an agent", async ({ page }) => {
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await expect(page.locator(".agentcard").first()).toBeVisible();
  await page.getByRole("button", { name: /Choose skill|Change/ }).click();
  await expect(page.getByRole("heading", { name: /Skill for/ })).toBeVisible();
  await page.getByRole("button", { name: /Critical Thinking/ }).click();
  await expect(page.locator(".customskill input")).toHaveValue("Critical Thinking");
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.locator(".skillmodal")).toHaveCount(0);
});

test("model API wizard discovers models on agents, while Connections contains shared tools", async ({ page }) => {
  await page.route("**/api/v1/connections/discover", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ok:true,latency_ms:42,model_count:2,models:[
      {id:"claude-sonnet-test",name:"Claude Sonnet Test",owner:"anthropic",context_length:200000},
      {id:"claude-haiku-test",name:"Claude Haiku Test",owner:"anthropic",context_length:200000},
    ]}),
  }));
  await page.getByRole("button", { name: "Connections" }).click();
  await expect(page.getByRole("heading", { name: "Connections" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add API" })).toHaveCount(0);
  await page.getByRole("button", { name: "MCP Hub" }).click();
  await expect(page.getByRole("heading", { name: "MCP Hub" })).toBeVisible();
  await expect(page.locator(".mcpcatalog button").first()).toBeVisible();
  await page.locator(".mcphub > header button").click();
  const githubButton = page.getByRole("button", { name: "GitHub" });
  await expect(githubButton).toBeVisible();
  if (await githubButton.isDisabled()) {
    await expect(githubButton).toHaveAttribute("title", "OAuth setup is required on the server");
  }

  await page.getByRole("button", { name: "Agents" }).click();
  await page.locator(".sectiontitle button").click();
  await page.locator(".agentwizard .inputlabel").filter({ hasText: "Name" }).locator("input").fill("E2E Wizard Agent");
  await page.locator(".agentwizard .inputlabel").filter({ hasText: "Role" }).locator("input").fill("Auditor");
  await page.getByRole("button", { name: "Choose model" }).click();
  await expect(page.locator(".agentproviders")).toBeVisible();
  await expect(page.getByRole("button", { name: /AgentRouter/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /TabiToken/ })).toBeVisible();
  await page.getByRole("button", { name: /Anthropic/ }).click();
  const keyInput=page.locator(".agentconnectionfields .inputlabel").filter({ hasText: "API key" }).locator("input");
  await expect(keyInput).toBeVisible();
  await keyInput.fill("test-key-never-sent");
  await page.getByRole("button", { name: "Test and discover" }).click();
  await expect(page.getByText("2 models discovered")).toBeVisible();
  await expect(page.locator(".modellist")).toContainText("claude-sonnet-test");
  await page.locator(".modellist button").first().click();
  await expect(page.getByText("Active model: claude-sonnet-test")).toBeVisible();
  await expect(page.getByText(/price per million tokens/i)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Create agent" })).toBeEnabled();
  await page.locator(".agentwizard > header button").click();
});

test("Deep Research is managed by Orbit and never asks users for search API keys", async ({ page }) => {
  await page.getByRole("button", { name: "Deep Research" }).click();
  await expect(page.getByRole("heading", { name: "Explore a topic in depth" })).toBeVisible();
  const run = page.getByRole("button", { name: /Start research/ });
  await expect(run).toBeDisabled();
  await page.getByPlaceholder(/For example: which short-video formats/).fill("E2E product research trends");
  await expect(run).toBeEnabled();
  await expect(page.getByText("Sources ready", { exact: true })).toBeVisible();
  await expect(page.getByText("Search is provided by Orbit", { exact: true })).toBeVisible();
  await expect(page.getByText(/API key/i)).toHaveCount(0);
  for (const source of ["Web", "Youtube", "Tiktok", "Instagram"]) {
    await expect(page.getByRole("button", { name: source })).toBeVisible();
  }
});

test("profile exposes X connection and the upcoming ambassador campaign", async ({ page }) => {
  await page.goto("/");
  await page.locator(".user").click();
  await expect(page.getByRole("heading", { name: /Your profile|Ваш профиль/ })).toBeVisible();
  await expect(page.getByText(/Ambassador campaign|Амбассадорская кампания/, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /In development|В разработке/ })).toBeDisabled();
  await page.getByRole("button", { name: /Connect X|Подключить X/ }).click();
  await expect(page.getByRole("heading", { name: /Continue with X|Войти через X/ })).toBeVisible();
  await expect(page.locator(".twittermodal").getByText(/users\.read.*tweet\.read/i)).toBeVisible();
  await expect(page.locator(".twittermodal input")).toHaveCount(0);
});

test("Russian and English localization can be switched without reload errors", async ({ page }) => {
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("button", { name: "Русский" }).click();
  await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Новый чат" })).toBeVisible();
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("button", { name: "New chat" })).toBeVisible();
});

test("mobile interface has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".boot")).toHaveCount(0, { timeout: 15_000 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await expect(page.getByPlaceholder("Describe a task for your agent team…")).toBeVisible();
});

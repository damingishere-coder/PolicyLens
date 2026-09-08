import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { promises as fs } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";

interface RuntimeInfo {
  servicePid: number;
  serviceHost: "127.0.0.1";
  servicePort: number;
  manager: string;
  browserMode: true;
  sessionProtection: string;
}

async function unusedPort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("无法分配测试端口"));
        return;
      }
      server.close(() => resolve(address.port));
    });
  });
}

async function waitForHealth(url: string, server: ChildProcessWithoutNullStreams): Promise<void> {
  let diagnostic = "";
  server.stderr.on("data", (chunk: Buffer) => {
    diagnostic = (diagnostic + chunk.toString("utf8")).slice(-4_000);
  });
  await expect.poll(async () => {
    if (server.exitCode !== null) throw new Error(`本地 Web 服务提前退出：${diagnostic}`);
    try {
      const response = await fetch(`${url}/health`);
      return response.ok ? (await response.json() as { service?: string }).service : "";
    } catch {
      return "";
    }
  }, { timeout: 30_000 }).toBe("policylens");
}

async function stopServer(server: ChildProcessWithoutNullStreams): Promise<void> {
  if (server.exitCode !== null || !server.pid) return;
  if (process.platform === "win32") {
    const killer = spawn("taskkill.exe", ["/PID", String(server.pid), "/T", "/F"], {
      windowsHide: true,
      shell: false,
      stdio: "ignore"
    });
    await new Promise<void>((resolve) => killer.once("exit", () => resolve()));
    return;
  }
  server.kill("SIGTERM");
}

async function waitForPortToClose(port: number): Promise<void> {
  await expect.poll(async () => await new Promise<boolean>((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port });
    socket.once("connect", () => { socket.destroy(); resolve(false); });
    socket.once("error", () => resolve(true));
    socket.setTimeout(500, () => { socket.destroy(); resolve(true); });
  }), { timeout: 10_000 }).toBe(true);
}

async function acceptCurrentImport(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { name: "候选字段" })).toBeVisible();
  await page.getByRole("button", { name: "全部接受" }).click();
  await page.getByRole("button", { name: "确认并发布版本" }).click();
  await expect(page.getByText("产品版本已保存")).toBeVisible();
}

async function createManualProduct(page: Page): Promise<void> {
  await page.getByRole("button", { name: "手工资料" }).click();
  await page.getByLabel("产品名称").fill("SYNTHETIC Browser Beta");
  await page.getByLabel("版本", { exact: true }).fill("Synthetic Browser B 2026");
  await page.getByLabel("标准年费率").fill("1560.00");
  await page.getByRole("button", { name: "生成待核验字段" }).click();
  await acceptCurrentImport(page);
}

test("首次可用闭环可在 localhost 浏览器中完成", async ({ page }, testInfo) => {
  const projectRoot = path.resolve(__dirname, "../..");
  const dataDirectory = await fs.mkdtemp(path.join(os.tmpdir(), "policylens-web-smoke-"));
  const port = await unusedPort();
  const url = `http://127.0.0.1:${port}`;
  const server = spawn(
    path.join(projectRoot, ".venv", "Scripts", "python.exe"),
    [
      "scripts/serve.py", "--host", "127.0.0.1", "--port", String(port),
      "--data-dir", dataDirectory, "--manager", "RunDock test", "--skip-frontend-build"
    ],
    {
      cwd: projectRoot,
      windowsHide: true,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        POLICYLENS_TEST_MODE: "1",
        POLICYLENS_FAKE_CODEX_COMMAND: process.execPath,
        POLICYLENS_FAKE_CODEX_SCRIPT: path.join(projectRoot, "tests", "fixtures", "synthetic", "fake-codex.mjs"),
        POLICYLENS_FAKE_RESEARCH_CODEX_COMMAND: process.execPath,
        POLICYLENS_FAKE_RESEARCH_CODEX_SCRIPT: path.join(projectRoot, "tests", "fixtures", "synthetic", "fake-research-codex.mjs"),
        POLICYLENS_FAKE_RESEARCH_SOURCE: "1"
      }
    }
  );
  let runtime: RuntimeInfo | undefined;
  try {
    await waitForHealth(url, server);
    const navigation = await page.goto(url);
    expect(navigation?.status()).toBe(200);
    expect(navigation?.headers()["content-security-policy"]).toContain("default-src 'self'");
    await expect(page.getByTestId("app-shell")).toBeVisible();
    await expect(page.getByRole("heading", { name: "香港保险公开研究台" })).toBeVisible();

    const browserIsolation = await page.evaluate(() => ({
      process: typeof (window as unknown as { process?: unknown }).process,
      require: typeof (window as unknown as { require?: unknown }).require,
      policyLens: typeof (window as unknown as { policyLens?: unknown }).policyLens
    }));
    expect(browserIsolation).toEqual({ process: "undefined", require: "undefined", policyLens: "undefined" });

    await page.getByRole("button", { name: "香港储蓄/年金" }).click();
    await expect(page.getByRole("heading", { name: "香港储蓄/年金主动研究" })).toBeVisible();
    await page.getByRole("button", { name: "查看联网研究预览" }).click();
    await expect(page.getByRole("heading", { name: "本次联网研究预览" })).toBeVisible();
    await expect(page.getByText("友邦香港", { exact: true })).toBeVisible();
    await expect(page.getByText("保诚香港", { exact: true })).toBeVisible();
    await expect(page.getByText("宏利香港", { exact: true })).toBeVisible();
    await expect(page.getByText("会发送", { exact: true })).toBeVisible();
    await expect(page.getByText("不会发送", { exact: true })).toBeVisible();
    await expect(page.getByText("Codex", { exact: false }).first()).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("policylens-research-preview.png"), fullPage: true });

    await page.getByLabel("我已查看范围和用量提示，同意本次只搜索公开资料").check();
    await page.getByRole("button", { name: "确认并启动一次研究" }).click();
    await expect(page.getByRole("heading", { name: "SYNTHETIC Future Savings Plan" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "SYNTHETIC Retirement Plan" })).toBeVisible();
    await expect(page.locator(".research-execution")).toContainText("网页检索活动 1 次");
    await expect(page.getByText("本次仅发现第三方线索", { exact: false })).toBeVisible();
    await page.getByLabel("加入待核验对比").nth(0).check();
    await page.getByLabel("加入待核验对比").nth(1).check();
    await page.getByRole("button", { name: /对比所选 2/ }).click();
    await expect(page.getByRole("heading", { name: "待核验候选对比" })).toBeVisible();
    await expect(page.getByText("不是正式结论", { exact: true })).toBeVisible();
    await page.locator(".candidate-card").first().getByRole("button", { name: "逐项人工核验" }).click();
    await acceptCurrentImport(page);
    await page.getByRole("button", { name: "香港储蓄/年金" }).click();
    await expect(page.getByRole("button", { name: "查看正式产品" }).first()).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("policylens-candidate-workbench.png"), fullPage: true });

    await page.getByRole("button", { name: "规划中" }).click();
    await page.getByRole("button", { name: "打开工具" }).click();
    const pdfChooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "选择文本 PDF" }).click();
    await (await pdfChooser).setFiles(path.join(projectRoot, "tests", "fixtures", "synthetic", "synthetic-care-alpha.pdf"));
    await acceptCurrentImport(page);
    await page.getByRole("button", { name: "查看字段证据" }).click();
    await expect(page.getByRole("heading", { name: "字段级证据" })).toBeVisible();
    await expect(page.getByText("RULE_EXTRACTION", { exact: false }).first()).toBeVisible();

    await page.getByRole("button", { name: "规划中" }).click();
    await page.getByRole("button", { name: "打开工具" }).click();
    await createManualProduct(page);
    await page.getByRole("button", { name: "证据对比" }).click();
    await page.locator(".product-picker button").nth(0).click();
    await page.locator(".product-picker button").nth(1).click();
    await page.getByRole("button", { name: "生成证据对比" }).click();
    await expect(page.getByText("保证续保不表示保费固定", { exact: false })).toBeVisible();
    await page.getByRole("button", { name: "生成外发预览" }).click();
    await expect(page.getByRole("heading", { name: "Codex 白名单外发预览" })).toBeVisible();
    await expect(page.locator(".preview pre")).not.toContainText(dataDirectory);
    await page.getByLabel("我已逐项查看本次完整预览，并主动确认只发送以上内容").check();
    await page.getByRole("button", { name: "确认并调用 Codex" }).click();
    await expect(page.getByText("DRAFT", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "仅接受为笔记" }).click();
    await expect(page.getByText("ACCEPTED_AS_NOTE", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "家庭保单" }).click();
    await page.getByRole("button", { name: "新增保单" }).click();
    await page.getByLabel("家庭成员昵称").fill("SYNTHETIC 成员甲");
    await page.getByLabel("已核验产品").selectOption({ index: 1 });
    await page.getByRole("button", { name: "保存本地保单" }).click();
    await page.getByRole("button", { name: "查看保单" }).click();
    await expect(page.getByRole("heading", { name: "PolicyPremiumRecord 实际缴费" })).toBeVisible();

    await page.getByRole("button", { name: "设置" }).click();
    await expect(page.getByText("浏览器本地模式", { exact: true })).toBeVisible();
    const password = "SYNTHETIC-browser-backup-2026";
    await page.getByLabel("恢复密码（至少 12 字符）").fill(password);
    await page.getByLabel("再次输入恢复密码").fill(password);
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "验证密码并下载备份" }).click();
    const download = await downloadPromise;
    const backupPath = testInfo.outputPath("synthetic-portable.plbackup");
    await download.saveAs(backupPath);
    expect(download.suggestedFilename()).toMatch(/^PolicyLens-backup-.*\.plbackup$/);

    await page.getByLabel("备份恢复密码").fill("SYNTHETIC-wrong-password");
    const wrongChooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "上传备份并验证" }).click();
    await (await wrongChooser).setFiles(backupPath);
    await expect(page.getByText("recovery password or backup integrity is invalid")).toBeVisible();

    await page.getByLabel("备份恢复密码").fill(password);
    const restoreChooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "上传备份并验证" }).click();
    await (await restoreChooser).setFiles(backupPath);
    await expect(page.getByRole("heading", { name: "恢复摘要" })).toBeVisible();
    await page.getByLabel("我确认用已验证备份切换当前数据").check();
    await page.getByRole("button", { name: "确认恢复并重新绑定 DPAPI" }).click();
    await expect(page.getByText("恢复成功", { exact: false })).toBeVisible();

    runtime = await page.evaluate(async () => await fetch("/api/v1/runtime").then((response) => response.json()) as RuntimeInfo);
    expect(runtime.serviceHost).toBe("127.0.0.1");
    expect(runtime.servicePort).toBe(port);
    expect(runtime.manager).toBe("RunDock test");
    expect(runtime.browserMode).toBe(true);
    console.log("Runtime acceptance:", JSON.stringify({ ...runtime, dataDirectory }));
    await page.screenshot({ path: testInfo.outputPath("policylens-web-dashboard.png"), fullPage: true });

    // Render a failed API record separately from successful empty discovery.
    await page.route("**/api/v1/research/runs", async (route) => {
      const response = await route.fetch();
      const runs = await response.json() as Array<Record<string, unknown>>;
      const latest = runs[0] as Record<string, unknown> & { insurer_outcomes: Array<Record<string, unknown>> };
      await route.fulfill({ response, json: [{
        ...latest, status: "FAILED", error_code: "CODEX_TIMEOUT", summary: { execution: {
          phase: "WEB_SEARCH", elapsed_seconds: 900, timeout_seconds: 900,
          events_observed: 12, web_searches: 4, last_event_elapsed_seconds: 895
        } }, leads: [],
        insurer_outcomes: latest.insurer_outcomes.map((item) => ({
          ...item, status: "FAILED", official_candidates: 0, waiting_review: 0,
          published: 0, rejected: 0, lead_only: 0, error_codes: ["CODEX_TIMEOUT"]
        }))
      }] });
    });
    await page.getByRole("button", { name: "香港储蓄/年金" }).click();
    await expect(page.locator(".insurer-outcomes").getByText("执行失败", { exact: true })).toHaveCount(3);
    await expect(page.locator(".research-run")).toContainText("研究超时");
    await expect(page.locator(".research-execution")).toContainText("已用 15 分 0 秒");
    await expect(page.locator(".insurer-outcomes")).not.toContainText("NO_RESULT_RETURNED");
    await page.screenshot({ path: testInfo.outputPath("policylens-research-failure.png"), fullPage: true });
  } finally {
    await stopServer(server);
    await waitForPortToClose(port);
    await fs.rm(dataDirectory, { recursive: true, force: true });
  }
});

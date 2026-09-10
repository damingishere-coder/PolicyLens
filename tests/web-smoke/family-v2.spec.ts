import { expect, test } from "@playwright/test";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { promises as fs } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";

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


test("家庭 V2 从空库建档到养老、原文与笔记的真实页面闭环", async ({page},testInfo) => {
  test.setTimeout(180_000);
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
  try {
    await waitForHealth(url,server);
    await page.goto(url);
    await expect(page.getByRole("heading",{name:"把家人的保障，放在心上。"})).toBeVisible();
    // Research failures do not block local family use.
    await page.route("**/api/v1/research/**", route => route.fulfill({status:503,body:"SYNTHETIC research unavailable"}));
    await page.getByRole("link",{name:"我的家庭",exact:true}).click();
    for(const [nickname,age] of [["SYNTHETIC 我","28"],["SYNTHETIC 妈妈","58"]]) {
      await page.getByRole("button",{name:"添加家人",exact:true}).click();
      await page.getByLabel("成员昵称",{exact:true}).fill(nickname!);
      await page.getByLabel("年龄（可稍后填写）").fill(age!);
      await page.getByRole("button",{name:"保存成员"}).click();
      await expect(page.getByRole("heading",{name:nickname!,exact:true})).toBeVisible();
    }
    const policyUrls:string[]=[];
    for(const [name,line,member] of [["SYNTHETIC 医疗险","MEDICAL","SYNTHETIC 我"],["SYNTHETIC 意外险","ACCIDENT","SYNTHETIC 我"],["SYNTHETIC 惠民保","HUIMIN","SYNTHETIC 妈妈"]]) {
      await page.goto(`${url}/policies/new`);
      await page.getByLabel("保险名称",{exact:true}).fill(name!);
      await page.getByLabel("被保险成员").selectOption({label:member!});
      await page.getByRole("combobox",{name:"保险类别",exact:true}).selectOption(line!);
      await page.getByRole("button",{name:"保存这份保单"}).click();
      await expect(page.getByRole("heading",{name:name!,exact:true})).toBeVisible();
      policyUrls.push(page.url().split("?")[0]!);
      await expect(page.getByText("状态待确认",{exact:true})).toBeVisible();
    }
    await page.goto(policyUrls[0]!);
    await page.getByRole("button",{name:"编辑保单"}).click();

    await page.getByLabel("我记录的保障责任").fill("SYNTHETIC 住院医疗责任，条件待核实");
    await page.getByLabel("重要限制与除外",{exact:true}).fill("SYNTHETIC 免赔额与医院范围待确认");
    await page.getByRole("button",{name:"保存保单修改"}).click();
    await expect(page.getByText("SYNTHETIC 免赔额与医院范围待确认",{exact:true})).toBeVisible();
    await page.getByRole("button",{name:"登记缴费",exact:true}).click();
    await expect(page.getByLabel("应缴金额",{exact:true})).toHaveValue("");
    await page.getByLabel("应缴金额",{exact:true}).fill("1200.00");
    const today=new Date().toLocaleDateString("en-CA");
    await page.getByLabel("应缴日期",{exact:true}).fill(today);
    await page.getByLabel("本期实缴金额").fill("400.00");
    await page.getByLabel("实缴日期",{exact:true}).fill(today);
    await page.getByRole("button",{name:"保存缴费记录"}).click();
    await expect(page.getByRole("cell",{name:"CNY 400.00",exact:true})).toBeVisible();
    await page.getByRole("link",{name:"这份保单的资料"}).click();
    await page.getByLabel("PDF 文件（最多 10 MiB、100 页）").setInputFiles(path.join(projectRoot,"tests/fixtures/synthetic/synthetic-care-alpha.pdf"));
    await page.getByRole("button",{name:"保存本地资料"}).click();
    await expect(page.getByRole("heading",{name:"本地原文",exact:true})).toBeVisible();
    await expect(page.locator(".document-text")).toContainText("SYNTHETIC");
    await expect(page.getByRole("link",{name:"打开 PDF 原件"})).toBeVisible();
    await page.goto(`${url}/retirement/new`);
    await page.getByLabel("目标名称").fill("SYNTHETIC 妈妈的养老目标");
    await page.getByLabel("为谁规划").selectOption({label:"SYNTHETIC 妈妈"});
    await page.getByRole("button",{name:"保存目标并计算"}).click();
    await expect(page.getByText("还需要一些信息",{exact:true})).toBeVisible();
    await expect(page.locator(".scenario-number")).toHaveCount(0);
    const retirementUrl=page.url();
    await page.getByRole("button",{name:"调整参数"}).click();
    await page.getByLabel("退休收支参考日期").fill("2030-01-01");
    await page.getByLabel("参考时点每月支出预算").fill("6000.00");
    await page.getByRole("button",{name:"添加收入来源"}).click();
    await page.getByLabel("收入名称",{exact:true}).fill("PRIVATE_PENSION_SOURCE");
    await page.getByLabel("月度金额",{exact:true}).fill("3000.00");
    await page.getByLabel("收入性质").selectOption("GUARANTEED");
    await page.getByLabel("我已登记目前已知的收入来源",{exact:false}).check();
    await page.getByRole("button",{name:"保存目标并计算"}).click();
    await expect(page.locator(".scenario-number")).toHaveCount(3);
    await expect(page.locator(".scenario-number").first()).toHaveText("CNY 3,000.00");
    await page.getByRole("button",{name:"复算此版本"}).first().click();
    await expect(page.getByText("已按该版本保存的参数复算",{exact:false})).toBeVisible();
    await page.getByRole("button",{name:"生成解读外发预览"}).click();
    await expect(page.locator(".explanation pre")).not.toContainText("PRIVATE_PENSION_SOURCE");
    await expect(page.locator(".explanation pre")).not.toContainText("SYNTHETIC 妈妈");
    await page.getByLabel("我已检查本次完整内容，同意仅外发以上资料").check();
    await page.getByRole("button",{name:"确认并开始解读"}).click();
    await expect(page.getByText("待审阅草稿",{exact:true})).toBeVisible();
    await page.getByRole("button",{name:"仅接受为笔记"}).click();
    await expect(page.getByText("已保存为笔记",{exact:true})).toBeVisible();
    await page.goto(`${url}/library?tab=notes`);
    await page.getByRole("link",{name:/养老计算解读 · 已保存为笔记/}).click();
    await expect(page.getByText("已保存为笔记",{exact:true})).toBeVisible();
    await page.goto(url);
    await expect(page.getByRole("heading",{name:"已记录 2 位家人、3 份保单"})).toBeVisible();
    await expect(page.getByText("CNY 400.00",{exact:true})).toBeVisible();
    await expect(page.getByText("CNY 800.00",{exact:true})).toBeVisible();
    await expect(page.getByRole("heading",{name:"SYNTHETIC 妈妈的养老目标"})).toBeVisible();
    await page.screenshot({path:testInfo.outputPath("family-home-desktop.png"),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    for(const target of [url,policyUrls[0]!,retirementUrl]) {
      await page.goto(target);
      await expect(page.locator("main h1").first()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
    await page.screenshot({path:testInfo.outputPath("retirement-mobile.png"),fullPage:true});
  } finally {
    await stopServer(server);
    await waitForPortToClose(port);
    await fs.rm(dataDirectory,{recursive:true,force:true});
  }
});

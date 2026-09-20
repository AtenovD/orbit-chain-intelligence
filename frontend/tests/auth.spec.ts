import { expect, test } from "@playwright/test";

test("registration creates a secure profile and a revocable session", async ({ page }) => {
  const email=`browser-${Date.now()}@example.com`;
  const password="browser-password-123";
  await page.goto("/");
  await expect(page.getByRole("heading",{name:"Welcome back"})).toBeVisible();
  await page.getByRole("button",{name:"No account? Create one"}).click();
  await page.locator(".inputlabel").filter({hasText:"Name"}).locator("input").fill("Browser Owner");
  await page.locator(".inputlabel").filter({hasText:"Email"}).locator("input").fill(email);
  await page.locator(".inputlabel").filter({hasText:/Password/}).locator("input").fill(password);
  await page.getByRole("button",{name:"Create account"}).click();
  await expect(page.getByRole("heading",{name:"What will we create today?"})).toBeVisible({timeout:15_000});
  await page.getByRole("button",{name:"Profile"}).click();
  await expect(page.getByRole("heading",{name:"Your profile"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Account and active sessions"})).toBeVisible();
  await expect(page.getByText("This session",{exact:true})).toBeVisible();
  const response = await page.request.delete("/api/v1/auth/me", { data: { password } });
  expect(response.status()).toBe(204);
});

test("password recovery form is reachable", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button",{name:"Forgot password?"}).click();
  await expect(page.getByRole("heading",{name:"Recover access"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Continue"})).toBeDisabled();
});

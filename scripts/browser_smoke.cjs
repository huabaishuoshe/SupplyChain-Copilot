// Optional real-browser checks. Requires Playwright and a running local app.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const output = path.join(root, 'outputs');
const checks = [];

(async () => {
  fs.mkdirSync(output, {recursive: true});
  const python = process.env.COPILOT_PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  execFileSync(python, [path.join(__dirname, 'prepare_browser_fixture.py')], {windowsHide: true});
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.COPILOT_BROWSER_PATH ? {executablePath: process.env.COPILOT_BROWSER_PATH} : {}),
  });
  const pageErrors = [];
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1100}, acceptDownloads: true});
    page.on('pageerror', error => pageErrors.push(error.message));
    const metrics = async expected => {
      await page.waitForFunction(values => {
        const current = Array.from(document.querySelectorAll('[data-testid="stMetricValue"]')).map(e => e.textContent.trim());
        return JSON.stringify(current) === JSON.stringify(values);
      }, expected);
      await page.locator('[data-testid="stApp"][data-test-script-state="notRunning"]').waitFor();
    };
    const choose = async (label, value) => {
      const input = page.getByRole('combobox', {name: label, exact: true});
      await input.fill(value);
      await input.press('ArrowDown');
      await input.press('Enter');
    };
    const sample = async () => {
      await page.getByRole('button', {name: '使用示例数据', exact: true}).click();
      await metrics(['4', '1', '50', '425.00']);
      await page.getByText('当前数据：虚构示例数据（非真实业务数据）', {exact: true}).waitFor();
    };
    await page.goto(process.env.COPILOT_URL || 'http://127.0.0.1:8501');
    await page.getByText('当前版本未接入 LLM；无需 API Key。库存计算、筛选、详情和导出均可独立使用。', {exact: true}).waitFor();
    await metrics(['4', '1', '50', '425.00']);
    checks.push('default_dashboard_without_api_key');
    await page.screenshot({path: path.join(output, 'dashboard.png'), fullPage: true});

    await choose('缺货风险', '高');
    await metrics(['1', '1', '50', '0.00']);
    await page.getByText('交期需求 = 8 × 7 = 56', {exact: true}).waitFor();
    checks.push('risk_filter_and_sku_detail');
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', {name: '导出分析 CSV', exact: true}).click();
    const download = await downloadPromise;
    assert.equal(download.suggestedFilename(), 'inventory_analysis.csv');
    const csvPath = path.join(output, 'browser_high_risk.csv');
    await download.saveAs(csvPath);
    const exported = fs.readFileSync(csvPath, 'utf8');
    assert(exported.includes('SKU-002'));
    assert(!exported.includes('SKU-001'));
    checks.push('actual_filtered_csv_download');

    await choose('缺货风险', '全部');
    await metrics(['4', '1', '50', '425.00']);
    await choose('选择 SKU 查看详情', 'SKU-004');
    await page.getByText('库存位置 = 500 + 0 = 500', {exact: true}).waitFor();
    checks.push('sku_detail_selection');
    await choose('SKU 筛选（留空表示全部）', 'SKU-004');
    await page.getByRole('combobox', {name: 'SKU 筛选（留空表示全部）', exact: true}).press('Escape');
    await metrics(['1', '0', '0', '380.00']);
    checks.push('sku_filter');

    // A new page gives a clean filter state before checking upload replacement.
    await page.reload();
    await metrics(['4', '1', '50', '425.00']);
    const customCsv = Buffer.from('sku,product_name,current_stock,avg_daily_demand,lead_time_days,safety_stock_days,in_transit_stock\nCUSTOM-001,虚构上传商品,20,10,5,2,30\n', 'utf8');
    await page.locator('input[type=file]').setInputFiles({name: 'browser_inventory.csv', mimeType: 'text/csv', buffer: customCsv});
    await metrics(['1', '1', '20', '0.00']);
    checks.push('actual_csv_upload');
    await sample();
    checks.push('sample_button_clears_csv_upload');

    await page.locator('input[type=file]').setInputFiles(path.join(root, 'work', 'browser_inventory.xlsx'));
    await metrics(['1', '1', '20', '0.00']);
    await page.getByText('当前数据：browser_inventory.xlsx', {exact: true}).waitFor();
    checks.push('actual_xlsx_upload');
    await sample();
    checks.push('sample_button_clears_excel_upload');

    await page.locator('input[type=file]').setInputFiles(path.join(root, 'tests', 'fixtures', 'inventory.xls'));
    await page.getByText('当前数据：inventory.xls', {exact: true}).waitFor();
    await metrics(['4', '1', '50', '425.00']);
    checks.push('actual_legacy_xls_upload');

    await page.locator('input[type=file]').setInputFiles({name: 'invalid.csv', mimeType: 'text/csv', buffer: Buffer.from('sku\nA\n')});
    await page.getByText('缺少必需列:', {exact: false}).waitFor();
    await page.getByTestId('stMetricValue').first().waitFor({state: 'hidden'});
    assert.equal(await page.getByRole('button', {name: '导出分析 CSV', exact: true}).count(), 0);
    checks.push('invalid_upload_blocks_analysis_and_export');
    await sample();
    await page.getByText('当前版本未接入 LLM；无需 API Key。库存计算、筛选、详情和导出均可独立使用。', {exact: true}).waitFor();
    await page.screenshot({path: path.join(output, 'dashboard.png'), fullPage: true});
    assert.deepEqual(pageErrors, []);
    checks.push('no_browser_page_errors');
    const report = {status: 'passed', checks, pageErrors};
    fs.writeFileSync(path.join(output, 'browser-results.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } catch (error) {
    fs.writeFileSync(path.join(output, 'browser-results.json'), JSON.stringify({status: 'failed', checks, pageErrors, error: error.message}, null, 2));
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

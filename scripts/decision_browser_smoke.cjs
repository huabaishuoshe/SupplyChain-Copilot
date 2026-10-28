// Real UI smoke checks with explicitly fictional test observations, not business data.
const {chromium} = require('playwright');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'outputs');
const checks = [];

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.COPILOT_BROWSER_PATH ? {executablePath: process.env.COPILOT_BROWSER_PATH} : {})});
  const errors = [];
  try {
    const page = await browser.newPage({viewport: {width: 1500, height: 1200}, acceptDownloads: true});
    page.on('pageerror', e => errors.push(e.message));
    const ready = async () => page.locator('[data-testid="stApp"][data-test-script-state="notRunning"]').waitFor();
    const navigate = async name => {
      await page.getByTestId('stSidebar').getByText(name, {exact: true}).click();
      await page.getByRole('heading', {name: name === '需求波动与策略' ? '需求波动与库存策略' : name, exact: true}).waitFor();
      await ready();
    };
    const choose = async (label, value) => {
      const input = page.getByRole('combobox', {name: label, exact: true});
      await input.fill(value);
      await page.getByRole('option', {name: value, exact: true}).waitFor();
      await input.press('ArrowDown'); await input.press('Enter');
    };
    const download = async (label, filename) => {
      const pending = page.waitForEvent('download');
      await page.getByRole('button', {name: label, exact: true}).click();
      await (await pending).saveAs(path.join(output, filename));
    };
    const number = async (label, value) => {
      const input = page.getByRole('spinbutton', {name: label, exact: true});
      await input.fill(String(value)); await input.press('Enter');
    };
    await page.goto(process.env.COPILOT_URL || 'http://127.0.0.1:8502');
    await page.getByText('当前版本未接入 LLM；无需 API Key。库存计算、筛选、详情和导出均可独立使用。', {exact: true}).waitFor();

    await navigate('情景分析');
    await number('需求变化比例 (%)', 100);
    await page.getByText('情景参数：需求 +100%，交期 +0 天，现货 +0%，安全天数 保留各 SKU 原值。', {exact: true}).waitFor();
    await ready();
    await download('导出情景对比 CSV', 'decision_scenario_demand100.csv');
    checks.push('scenario_demand_change_and_real_export');
    await page.getByRole('button', {name: '恢复默认参数', exact: true}).click();
    await page.getByText('情景参数：需求 +0%，交期 +0 天，现货 +0%，安全天数 保留各 SKU 原值。', {exact: true}).waitFor();
    await ready();
    assert.equal(await page.getByRole('spinbutton', {name: '需求变化比例 (%)', exact: true}).inputValue(), '0.00');
    await download('导出情景对比 CSV', 'decision_scenario_reset.csv');
    checks.push('scenario_reset_recalculates_baseline');

    await page.getByTestId('stSidebar').getByText('库存仪表盘', {exact: true}).click();
    await page.getByRole('heading', {name: '库存分析结果', exact: true}).waitFor();
    await ready();
    assert.deepEqual(await page.getByTestId('stMetricValue').allTextContents(), ['4', '1', '50', '425.00']);
    checks.push('original_inventory_unchanged_after_scenario');

    await navigate('需求波动与策略');
    await page.getByText('没有可用历史时间序列，无法计算真实需求标准差/CV；继续使用固定安全库存天数。', {exact: true}).waitFor();
    await download('下载空白历史销量模板', 'decision_empty_history_template.csv');
    assert.equal(fs.readFileSync(path.join(output, 'decision_empty_history_template.csv'), 'utf8').trim(), 'date,sku,demand');
    checks.push('no_history_keeps_fixed_and_template_contains_no_records');

    const lines = ['date,sku,demand'];
    for (let i = 0; i < 14; i++) lines.push(`2026-01-${String(i + 1).padStart(2, '0')},SKU-001,${i % 2 === 0 ? 2 : 6}`);
    const uploader = page.getByTestId('stFileUploader').filter({hasText: '可选历史销量 CSV'}).locator('input[type=file]');
    await uploader.setInputFiles({name: 'fictional_test_history.csv', mimeType: 'text/csv', buffer: Buffer.from(lines.join('\n') + '\n')});
    await page.getByText('当前历史来源：fictional_test_history.csv（用户导入，跨页面保留，使用清除按钮移除）', {exact: true}).waitFor();
    await ready();
    await choose('安全库存策略', '基于需求波动估算');
    await page.getByText('当前结果：需求波动策略 1 个 SKU；固定天数策略 3 个 SKU。', {exact: true}).waitFor();
    await ready();
    await download('导出策略对比 CSV', 'decision_policy_comparison.csv');
    await download('导出当前策略 CSV', 'decision_variable_policy.csv');
    checks.push('real_history_upload_and_policy_selection_with_per_sku_fallback');
    await choose('周期服务水平假设', '99.0%');
    await page.getByText('当前服务水平假设：99.0%。', {exact: true}).waitFor();
    await ready();
    await download('导出当前策略 CSV', 'decision_variable_policy99.csv');
    checks.push('service_level_configuration_and_real_export');

    await uploader.setInputFiles({name: 'invalid_history.csv', mimeType: 'text/csv', buffer: Buffer.from('date,sku,demand\nbad,SKU-001,-1\n')});
    await page.getByText('date 必须是有效的 YYYY-MM-DD 日历日期。', {exact: true}).waitFor();
    await page.getByText('当前结果：需求波动策略 0 个 SKU；固定天数策略 4 个 SKU。', {exact: true}).waitFor();
    checks.push('invalid_history_does_not_reuse_previous_statistics');
    await page.getByRole('button', {name: '清除历史销量', exact: true}).click();
    await ready();

    await navigate('供应商分析');
    await page.getByText('未提供 supplier 字段，无法按供应商分组。其他库存、历史需求与情景功能仍可使用。', {exact: true}).waitFor();
    checks.push('supplier_field_missing_page_remains_usable');
    const inventory = 'sku,product_name,current_stock,avg_daily_demand,lead_time_days,safety_stock_days,in_transit_stock,supplier\nA,FictionalA,70,10,5,2,0,FictionalSupplierA\nB,FictionalB,10,10,5,2,0,FictionalSupplierA\nC,FictionalC,60,10,5,2,0,FictionalSupplierB\n';
    await page.locator('input[type=file]').setInputFiles({name: 'fictional_suppliers.csv', mimeType: 'text/csv', buffer: Buffer.from(inventory)});
    await page.getByRole('button', {name: '导出供应商汇总 CSV', exact: true}).waitFor();
    await ready();
    await download('导出供应商汇总 CSV', 'decision_suppliers.csv');
    checks.push('supplier_upload_grouping_and_real_export');

    const python = process.env.COPILOT_PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    const verified = execFileSync(python, [path.join(__dirname, 'verify_decision_exports.py')], {encoding: 'utf8', windowsHide: true});
    console.log(verified);
    checks.push('downloaded_scenario_policy_and_supplier_formulas_verified');
    assert.deepEqual(errors, []);
    checks.push('no_browser_page_errors');
    const report = {status: 'passed', dataNotice: 'All uploaded history/supplier data in this test are fictional test fixtures; no forecasts or business outcomes are asserted.', checks, errors};
    fs.writeFileSync(path.join(output, 'decision-browser-results.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } catch (e) {
    fs.writeFileSync(path.join(output, 'decision-browser-results.json'), JSON.stringify({status: 'failed', checks, errors, error: e.message}, null, 2));
    throw e;
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});

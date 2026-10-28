# SupplyChain Copilot

Python、Pandas、Streamlit 构建的库存决策助手。保留原有库存仪表盘，并新增可选历史需求波动分析、安全库存策略对比、情景模拟和供应商分组。所有数值通过 Python 公式计算，历史缺失时不生成虚构记录或波动估计。

## 当前工作区直接运行（PowerShell）

```powershell
Set-Location -LiteralPath 'C:\Users\ZJJ\Documents\ChatGPT\ai+供应链'
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

浏览器打开 http://127.0.0.1:8502。本轮升级验证使用 8502，因为 8501 已被已有服务占用；旧服务未自动重启时可能仍显示旧界面。若端口被占用可使用已启动的升级页面或另选空闲端口。按 Ctrl+C 停止自己启动的服务。无需激活脚本、修改系统 PATH 或配置 API Key。

## 新环境安装

需要 Python 3.10+（本轮实际使用 3.12.14）。将 `python` 换成自己的有效解释器路径即可：

```powershell
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' -m streamlit run app.py
```

本机找到的基础解释器为 `C:\Users\ZJJ\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`。本轮 `.venv` 使用 `--system-site-packages` 创建，复用已有 Pandas 和 openpyxl；Streamlit、pytest、xlrd 已实际安装到项目环境。普通 `python`、`py`、`python3`、`pip`、`streamlit` 命令当前不在 PATH。

## 部署到 Streamlit Community Cloud

项目已将应用运行依赖放在仓库根目录的 `requirements.txt`，入口为 `app.py`，Python 代码从 `supplychain_copilot/` 导入。示例库存和公式说明通过 `Path(__file__)` 相对应用文件读取，不依赖 Cloud 工作目录。`.streamlit/config.toml` 将单文件上传限制与程序校验统一设为 20 MB。没有 LLM 调用，因此不需要 `OPENAI_API_KEY` 或 `[secrets]` 配置。

### 1. 推送代码到 GitHub

在 GitHub 新建一个空仓库。选择代码仓库可见范围时，请根据项目内容决定；部署出来的网页访问权限要在 Streamlit Cloud 页面另行确认，仓库设为私有不自动等于网页需要登录。本项目当前没有远程仓库或提交记录。

在项目根目录 PowerShell 中检查忽略规则，再提交项目文件：

```powershell
git status --short --ignored
git add .
git status --short
git commit -m "Prepare SupplyChain Copilot for Streamlit Cloud"
git branch -M main
git remote add origin https://github.com/<GitHub用户名>/<仓库名>.git
git push -u origin main
```

`.venv/`、缓存、`work/`、本机验证用 `outputs/`、常见上传目录、仓库根目录新放入的 CSV/Excel 用户文件以及凭证文件均在 `.gitignore` 中。确认第二次 `git status --short` 没有用户数据或密钥后再提交。示例 `sample_inventory.csv` 和测试夹具是明确标注的虚构数据，保留在仓库供应用和测试使用。不要把访问令牌写进文件或命令；按 GitHub 登录流程完成认证。

### 2. 在 Streamlit Community Cloud 创建应用

1. 登录 Streamlit Community Cloud 并连接刚才的 GitHub 账号。
2. 新建应用，选择仓库、`main` 分支和 `app.py` 主文件。
3. Python 版本选择 **3.12**（与本项目验证环境一致）。依赖文件保持仓库根目录默认的 `requirements.txt`，不需要填写 Secrets。
4. 部署完成后用 Cloud 给出的 HTTPS URL 打开网页，确认应用状态正常。改动推送到所选分支后，按 Cloud 页面显示的状态检查重新部署结果。

### 3. 数据处理和访问范围

应用不会将上传的库存或历史 CSV/Excel 写入仓库或磁盘；文件在应用会话中解析，历史销量会保存在 Streamlit 会话状态中，以支持页面切换。托管平台仍会接收并在其运行环境中处理上传内容。当前没有应用登录或角色权限；部署后应检查 Cloud 分享设置。没有确认访问控制前，不要在公开 URL 上传敏感供应商或库存数据。本项目没有数据库、持久化上传、API Key 或 LLM 配置。

若部署失败，先检查 Community Cloud 构建日志中的 Python 版本、仓库分支/入口和依赖安装错误。勿将 secrets 或上传文件放进 GitHub 作为排障材料。

## 输入格式

| 列 | 含义 | 规则 |
| --- | --- | --- |
| sku | SKU 唯一编号 | 必填，去首尾空格后唯一；文本编号可保留前导零 |
| product_name | 商品名称 | 必填且不能仅含空格 |
| current_stock | 当前可用现货数量 | 有限、非负数 |
| avg_daily_demand | 日均需求数量 | 有限、非负数，0 有专门处理 |
| lead_time_days | 采购/补货交期（天） | 必填、有限、非负数，缺失不自动填补 |
| safety_stock_days | 安全库存天数 | 必填、有限、非负数 |
| in_transit_stock | 已下单未到货数量 | 可选列；缺列时明确提示并按 0，存在空值时拒绝 |
| supplier | 供应商分组名称 | 可选列；空值归入“未填写供应商”，没有该列时其他功能照常使用 |

CSV 为逗号分隔，支持 UTF-8、UTF-8 BOM、GB18030。Excel 支持 `.xlsx`（openpyxl）和 `.xls`（xlrd），读取第一个工作表。文件上限 20 MB；拒绝空数据、重复列名、重复 SKU、空值、负数、非数值、布尔值、NaN、无穷大以及计算溢出。Excel 中已保存为数字的 SKU 无法凭空恢复前导零，应将编号存为文本。

## 计算和交互

- `coverage_days = current_stock / avg_daily_demand`；零需求覆盖天数留空。
- `lead_time_demand = avg_daily_demand × lead_time_days`。
- `target_stock = avg_daily_demand × (lead_time_days + safety_stock_days)`。
- `inventory_position = current_stock + in_transit_stock`。
- `recommended_reorder_qty = ceil(max(target_stock - inventory_position, 0))`。
- `potential_overstock = max(inventory_position - target_stock, 0)`。

风险按现货覆盖天数与交期、安全库存天数比较；在途库存抵扣补货量，但不降低风险，原因是输入没有到货日期。详见 [FORMULAS.md](FORMULAS.md)。页面汇总、表格和导出均使用当前筛选。点击“使用示例数据”会清除旧上传文件。筛选无匹配时显示提示并禁用导出。CSV 包含实际公式结果，采用 UTF-8 BOM，零需求的覆盖天数为空。

## 页面入口与新增能力

侧栏“功能页面”提供四个入口：

1. **库存仪表盘**：默认仍按原库存文件的 `avg_daily_demand` 和 `safety_stock_days` 计算，旧筛选、详情、CSV/Excel 上传及导出保留。
2. **需求波动与策略**：导入真实逐日需求 CSV，检查统计可用性，选择服务水平和安全库存方法，对比同一需求口径下的固定/波动策略，并导出结果。
3. **情景分析**：调整需求比例、供应商交期天数、现货比例，选择是否统一覆盖安全库存天数；比较基准与调整后汇总、逐 SKU 覆盖/交期需求/交期末预计可用量/补货/积压/风险；一键恢复默认参数。
4. **供应商分析**：存在 `supplier` 时显示 SKU 数、风险分布及库存/补货汇总；缺少字段时提示，不阻断其他页面。不计算未经采购订单历史支持的交付率或延迟率。

### 可选历史需求格式

在“需求波动与策略”下载的 CSV 模板**只有表头**，不含虚构历史记录：

```csv
date,sku,demand
```

请填入自己持有的实际逐日数据，再上传。日期必须是 YYYY-MM-DD，每个 SKU 每天唯一。零需求日需显式记录为 0；系统不把缺失日期补零，不聚合重复日，不推测缺失销量。默认至少 14 个连续日观测，可将门槛调整到至少 2，但这不保证预测可靠性。页面显示窗口日期、记录数、缺失日数、均值、样本标准差（ddof=1）、CV 和不可用原因。CV=样本标准差/均值。

样本不足或日期有间隔时，均值/标准差/CV 留空；均值为零时保留实际均值 0，标准差/CV 不用于策略，回退固定策略。没有匹配历史的 SKU 也回退，并逐项说明。恒定正需求的标准差和 CV 可以是真实的 0。

历史数据仅在用户上传后使用，在会话内跨页面保留，点击“清除历史销量”移除。上传无效的新文件会清除旧统计来源，不悄悄继续使用旧历史。切换或恢复库存样例不会制造或替换历史记录。无历史数据时所有核心页面仍可使用。

### 安全库存策略

- 固定天数：`SS = D × B`。
- 需求波动：`SS = NormalDist().inv_cdf(alpha) × sigma_daily × sqrt(L)`，默认周期服务水平假设 95%，界面可选 90%、95%、97.5%、99%。
- 波动策略的目标库存为 `D×L+SS`，不再额外叠加固定安全库存。可用历史 SKU 使用其历史均值 D；其他 SKU 明确回退原固定天数策略。
- 策略对比中两种候选方法使用相同 D：有可用历史时都用其均值，否则都用库存输入日均需求。原仪表盘日均需求不会被改写。
- 服务水平是独立同分布日需求、确定交期及正态近似下的模型假设，不是实际客户满足率。未评估强趋势、季节性、间歇需求或实际交期波动，不能宣称预测或服务效果。

### 情景口径

情景页独立采用固定天数策略，基准来自原库存输入。调整需求和现货百分比、交期加减天数只作用于副本；在途数量不变。安全天数覆盖默认关闭，保留每 SKU 原值，启用时才统一替换。任何负交期直接报错，不自动截断；需求或现货最多减少 100%。

`projected_available_at_lead_end = current_stock - avg_daily_demand × lead_time_days`，是可带负号的简化现货结余，负数表示未覆盖的交期需求；忽略在途到货时点和建议新订单，不代表真实库存时序。高/中风险和积压 SKU 数按逐行计算结果计数，补货总量按逐行向上取整结果相加；不输出含糊的跨 SKU 平均覆盖天数。点击“恢复默认参数”将所有变化归零并关闭安全天数覆盖。

## LLM 状态与边界

当前工作区没有实际 LLM 调用模块或 API 配置，页面明确显示该状态。没有 API Key 时，上传、校验、公式计算、筛选、详情、图表和导出均可运行。未来解释层只能读取结果生成文字，不能写回计算数据。当前没有把固定文案按钮当作 AI 分析。

原仪表盘和情景页是基于给定日均需求的规则模型；新增历史分析是描述统计，波动策略是有假设的库存估算，均不是经过验证的缺货概率预测。尚未考虑在途到货日期、未履约订单、MOQ、整箱约束、订货复核周期、季节性、金额及多仓调拨。潜在积压表示超过目标库存的数量，不代表已经确认的呆滞库存。跨 SKU 总量只有单位一致时才有业务意义。

## 项目与验证

- `app.py`：Streamlit 页面与交互。
- `supplychain_copilot/validation.py`：校验与明确的缺列假设。
- `supplychain_copilot/calculations.py`：确定性指标与风险分级。
- `supplychain_copilot/file_io.py`：真实文件读取与导出。
- `supplychain_copilot/demand.py`、`strategies.py`：历史质量校验、描述统计和安全库存策略对比。
- `supplychain_copilot/scenarios.py`、`suppliers.py`、`views.py`：情景副本、供应商聚合及新增页面。
- `tests/`：原有测试、边界测试、文件测试及 Streamlit AppTest。
- `scripts/browser_smoke.cjs`：可选真实浏览器上传/下载检查，需要安装 Playwright 并启动应用。
- `scripts/decision_browser_smoke.cjs`：新增页面的真实交互/下载验证；测试专用虚构历史只在脚本运行时上传，不是应用默认业务数据。

`requirements-dev.txt` 额外提供生成旧版 `.xls` 测试文件所需的 xlwt。已提交测试样本，运行常规 pytest 不需要 xlwt；重新生成时执行 `python -m pip install -r requirements-dev.txt` 和 `python tests/generate_excel_fixtures.py`。

详见 `PROJECT_PLAN.md`、`FORMULAS.md`、`DEMO_SCRIPT.md`。示例与测试数据全部为虚构，不作为业务成效证据。

本机上一轮完整回归曾有 161 项测试通过，另完成原有 12 项和新增 11 项浏览器检查；这些本机 `outputs/` 验证产物会被 Git 忽略，不作为 Cloud 部署文件。部署前请在本机重新执行 `& '.\.venv\Scripts\python.exe' -m pytest -q`。

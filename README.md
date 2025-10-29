# AlphaNex 股票监控与智能交易系统

## 项目概述

AlphaNex是一个基于Python的智能股票监控与交易系统，它通过LongPort API获取实时行情数据，利用Deepseek AI进行交易决策分析，并能根据配置自动执行交易操作。系统采用量化交易策略，严格执行风险管理规则，支持实时监控、AI决策、自动交易和完整的报告生成功能。

## 系统架构

### 核心组件

- **股票监控器** (`stock_monitor.py`) - 系统的主要入口，负责协调各组件工作
- **配置管理** (`config.yaml`) - 集中管理API密钥、监控股票列表和系统参数
- **AI决策引擎** - 利用Deepseek AI进行交易分析和决策
- **交易执行器** - 通过LongPort API执行实际交易或模拟交易
- **数据存储** - 保存交易历史、账户信息和监控数据
- **报告生成器** - 生成利润报告和交易统计

## 功能特点

### 核心功能
- **配置化监控**：通过YAML文件灵活配置监控股票列表和参数
- **实时行情跟踪**：监控股票实时价格、涨跌幅和技术指标
- **阈值提醒**：当涨跌幅超过设定阈值时自动触发分析
- **AI智能决策**：利用Deepseek AI作为量化交易专家进行深度分析
- **自动交易执行**：根据AI决策自动下单买入或卖出
- **风险管理**：严格执行单笔交易资金限制和止损策略
- **完整日志系统**：记录所有监控和交易操作
- **交易历史记录**：保存和恢复交易历史
- **利润报告生成**：计算并展示已实现和未实现利润

### 高级功能
- **技术指标分析**：支持RSI、MACD、布林带等技术指标
- **统计模型应用**：实现价格动量、均值回归等策略
- **多因子评估**：综合市场温度、行业强度、资金流向等因素
- **时间序列分析**：识别日内波动模式和短期趋势
- **决策记忆系统**：记录历史决策，避免频繁交易
- **模拟交易支持**：在真实交易失败时自动回退到模拟交易

## 安装指南

### 1. 克隆项目

```bash
git clone https://your-repository-url/AlphaNex.git
cd AlphaNex
```

### 2. 创建虚拟环境（推荐）

```bash
python3 -m venv .venv
source .venv/bin/activate  # 在Windows上使用 .venv\Scripts\activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置API密钥

编辑 `config.yaml` 文件，填写你的API密钥和配置信息：

```yaml
# LongPort API配置
longport:
  app_key: "your_app_key"
  app_secret: "your_app_secret"
  access_token: "your_access_token"

# Deepseek API配置
deepseek:
  api_key: "your_deepseek_api_key"
  api_url: "https://api.deepseek.com/v1/chat/completions"
```

## 配置说明

### 股票配置项

```yaml
stocks:
  - symbol: BABA.US
    watch: true
    initial_action: hold
    threshold: 3.0  # 涨跌幅阈值百分比
  - symbol: INTC.US
    watch: true
    initial_action: hold
    threshold: 3.0
```

- `symbol`：股票代码，格式如 `BABA.US`, `INTC.US`
- `watch`：是否监控此股票
- `initial_action`：初始操作（hold/buy/sell）
- `threshold`：涨跌幅阈值百分比，超过此值将触发分析

### 应用配置项

```yaml
app:
  check_interval: 10  # 检查间隔（秒）
  log_level: "INFO"  # 日志级别（DEBUG/INFO/WARNING/ERROR）
  max_position: 50000  # 最大持仓金额
  fallback_to_simulated: true  # 真实下单失败时是否回退到模拟下单
```

### 交易配置项

```yaml
fund_limit: 0  # 交易资金限额（USD），0表示不限制
```

## 使用方法

### 1. 配置监控股票

在 `config.yaml` 文件中设置你想要监控的股票列表，参考配置说明部分。

### 2. 运行监控程序

```bash
python stock_monitor.py
```

### 3. 查看日志和报告

- 日志文件：`stock_monitor.log`
- 交易历史：`transaction_history.json`
- 账户日志：`account_daily_log.csv`

## 项目文件结构

```
AlphaNex/
├── stock_monitor.py      # 主监控程序
├── config.yaml           # 配置文件
├── requirements.txt      # 项目依赖
├── transaction_history.json  # 交易历史记录
├── account_daily_log.csv     # 账户每日日志
├── stock_monitor.log     # 系统日志
├── account.py            # 账户管理模块
├── cash.py               # 现金管理模块
├── order.py              # 订单处理模块
├── holder.py             # 持仓管理模块
├── market_temp.py        # 市场温度分析
├── calc_index.py         # 指标计算模块
└── watch.py              # 监控功能模块
```

## 核心功能详细说明

### AI决策系统

系统使用Deepseek AI作为量化交易专家，基于以下框架进行分析：

1. **技术指标分析**：RSI、MACD、布林带、成交量变化率、波动率等
2. **统计模型应用**：价格动量、均值回归、波动率突破策略
3. **风险管理**：严格执行单笔交易资金限制、止损策略
4. **多因子评估**：市场温度、行业相对强度、资金流向、量价关系
5. **时间序列分析**：日内波动模式识别、短期趋势预测

AI输出格式为：买入/卖出/持有 指令 + 详细量化分析理由

### 风险管理策略

- **资金限制**：单笔交易不超过资金限额的设定比例（默认10%）
- **止损规则**：单笔交易最大亏损不超过入场价格的2%
- **止盈建议**：在3%盈利时考虑卖出
- **模拟交易回退**：当真实交易失败时自动切换到模拟交易

### 报告功能

系统能够生成详细的利润报告，包含以下信息：

- 总交易次数
- 买入交易次数
- 卖出交易次数
- 盈利交易次数
- 亏损交易次数
- 已实现利润
- 未实现利润
- 按股票的利润分布
- 最大单笔盈利/亏损

## 日志系统

系统使用Python的logging模块实现完整的日志记录：

- **日志级别**：支持DEBUG、INFO、WARNING、ERROR
- **输出目标**：同时输出到文件和控制台
- **日志格式**：包含时间戳、模块名、级别和消息
- **关键操作记录**：所有API调用、交易操作、决策过程都会被记录

## 注意事项

1. **API密钥安全**：请妥善保管你的API密钥，不要泄露给他人
2. **模拟交易测试**：在实盘交易前，建议先进行充分的模拟测试
3. **风险控制**：设置合理的阈值和最大持仓金额，避免过度交易
4. **API频率限制**：注意LongPort API的调用频率限制
5. **网络稳定性**：确保网络连接稳定，避免因网络问题导致交易失败

## 扩展开发

### 功能扩展方向

- 集成更多数据源和交易API
- 添加更多技术指标和分析方法
- 实现更复杂的量化交易策略
- 开发可视化仪表盘和监控界面
- 添加回测功能

### 代码扩展指南

1. **添加新的分析指标**：在`calc_index.py`中实现
2. **修改交易策略**：调整`stock_monitor.py`中的决策逻辑
3. **扩展配置选项**：在`config.yaml`中添加新的配置项
4. **集成新的数据源**：创建新的API客户端模块

## 许可证

[MIT License](https://opensource.org/licenses/MIT)

## 免责声明

本系统仅供学习和研究使用，不构成投资建议。使用本系统进行的任何交易操作，风险自负。请在实盘交易前进行充分测试并了解相关风险。
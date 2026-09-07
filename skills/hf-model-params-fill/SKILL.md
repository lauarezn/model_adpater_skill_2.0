---
name: hf-model-params-fill
version: 1.1.0
description: 从 Hugging Face config.json 补全/校正本仓库「全球AI模型参数」（data/model-params.json）的模型参数与架构，并维护「Dense 架构总参=激活参」的数据一致性规则
tags: [model, hf, hf-mirror, config, moe, dense, params, data]
allowed_tools: [bash, read_file, write_file, edit_file, grep]
---

# HF 模型参数补全与架构校正（仓库专有）

本 Skill 服务于本仓库（昇腾服务器大模型适配清单 / model_adapter）的「全球AI模型参数」数据维护。
数据源文件：`data/model-params.json`（913 条记录），后台管理页面为「全球AI模型参数」。
后端 `server.py` 的 `load_model_params()` 每次请求重新读取文件，**改完数据无需重启服务**。

## 触发场景

- 后台「全球AI模型参数」中某模型部分参数（layers / attentionHeads / kvHeads / headDim / context）为空白或缺失。
- 用户提供 HF 仓库链接（如 `https://hf-mirror.com/org/repo/blob/main/config.json`）要求补全某模型参数。
- 需要校验或校正某模型的架构标注（Dense / MoE）。

## 数据模型（model-params.json 字段）

| 字段 | 含义 | 来源 config.json 键 |
|------|------|---------------------|
| modelCode | 模型标识（主键） | - |
| name | 展示名 | - |
| totalParams | 总参数(B) | 用户提供/既有数据 |
| activeParams | 激活参数(B) | Dense 时 = totalParams |
| layers | 层数 | `num_hidden_layers`（或 `num_layers`） |
| attentionHeads | 注意力头数 | `num_attention_heads` |
| kvHeads | KV 头数 | `num_key_value_heads`（或 `num_kv_heads`，缺省=头数） |
| headDim | 头维度 | `head_dim`（或 `qk_head_dim`，缺省=hidden_size/heads；**DeepSeek MLA 特例见下**） |
| context | 上下文(tokens) | `max_position_embeddings`（或 `seq_length`，缺省查 tokenizer model_max_length） |
| architecture | 架构 | Dense / MoE |
| isMoE | 是否 MoE | 是 / 否 |
| hfRepo | HF 仓库 | org/name |

## 核心规则

### 1. 架构判断流程（用户规定，必须遵循）

查看模型 `config.json`（支持多模态模型嵌套在 `text_config` 中）：

```
1. 查找键 "n_routed_experts" 或 "num_local_experts"
   ├─ 存在且 > 0 → 【MoE 架构】(立即确认)
   └─ 不存在 → 继续
2. 查找键 "num_experts_per_tok" 或 "top_k"
   ├─ 存在 → 【MoE 架构】
   └─ 不存在 → 【Dense 架构】(最终确认)
```

补充判据（增强）：`num_experts`、`moe_num_experts`、`use_moe=True`、`moe_top_k`、
`moe_intermediate_size`、`moe_layers_enum` 任一存在也视为 MoE。
`model_type` 含 "moe" 视为 MoE。
**仅当所有 MoE 特征键都不存在时才判为 Dense。**

### 2. Dense 架构「总参 = 激活参」规则

- **Dense 架构模型的 activeParams 必须等于 totalParams**。
- 若 activeParams 缺失（null）→ 补全 `activeParams = totalParams`。
- 若 activeParams ≠ totalParams（数据错误，如激活数超过总参）→ 改为 `activeParams = totalParams`。
- **MoE 架构模型的 activeParams 保持不变**（激活数通常远小于总参，是 MoE 正常特征）。

### 3. DeepSeek MLA 头维度特殊计算（用户规定，必须遵循）

DeepSeek V3 / R1 系列（`model_type=deepseek_v3`，MLA 多头潜在注意力架构）的头维度
**不能直接取 `head_dim` 或 `hidden_size/heads`**，而应计算：

```
headDim = qk_nope_head_dim + qk_rope_head_dim
```

DeepSeek V3/R1 系列标准值：`qk_nope_head_dim=128` + `qk_rope_head_dim=64` = **headDim=192**。

- 应用范围：`DeepSeek-R1`、`DeepSeek-R1-Zero`、`DeepSeek-R1-0528`、`DeepSeek-V3`、`DeepSeek-V3-0324`、
  `DeepSeek-V3-Base`、`DeepSeek-V3.1`、`DeepSeek-V3.1-Terminus`、`DeepSeek-V3.2`、`DeepSeek-V3.2-Exp`、
  `DeepSeek-V3.2-Speciale`、`DeepSeek-Prover-V2`、`DeepSeekMath-V2` 等所有 deepseek_v3 MLA 架构模型。
- 判断依据：config.json 中存在 `qk_nope_head_dim` 且 `qk_rope_head_dim`（或 `kv_lora_rank`、`q_lora_rank`、`first_k_dense_replace` 等 MLA 特征键）。
- 若 headDim 数据为 56 等异常值，应按此规则校正为 192。

### 4. 一致性验证

修正后必须复查：**所有 Dense 架构模型，凡 totalParams 有值，activeParams 必须等于 totalParams**。

## 标准操作流程

### 补全单个模型参数

1. 定位记录：按 `modelCode`（不区分大小写）在 `data/model-params.json` 查找。
2. 抓取 config：`curl` 或 `server._http_get` 获取 `https://hf-mirror.com/{repo}/resolve/main/config.json`。
   - 网络不稳定（DNS 间歇失败）时重试 3-4 次，间隔 2 秒。
   - 多模态模型关键字段在 `text_config` 子对象中，需递归/嵌套查找。
3. 按「架构判断流程」判定架构。
4. 字段映射：按上表填充 layers/attentionHeads/kvHeads/headDim/context。
5. 应用「Dense 总参=激活参」规则。
6. 更新 `hfRepo` 字段为 `org/name`。
7. **修改前先备份**到 `data/backups/model-params-backup-{场景}-{时间戳}.json`。
8. 修改后运行一致性验证脚本。

### 批量补全

- 复用 `server._fetch_hf_config(hf_repo)` 自动抓取并解析（已实现架构判断与字段映射）。
- 提供 `fill_model_params.py` 脚本（本目录），支持单/批量、断点续跑。
- 已知限制：部分闭源模型无 HF 仓库、部分仓库需鉴权（HTTP 401）、网络不稳定（DNS 失败）——属正常，失败项可稍后重试。

## 常见坑

- **KV 头数字段名不统一**：`num_key_value_heads`（多数）vs `num_kv_heads`（Falcon 等）；缺省时默认等于注意力头数。
- **head_dim 缺失**：用 `qk_head_dim` 或 `hidden_size / num_attention_heads` 推算；值为 0 时视为缺失。
- **DeepSeek MLA 头维度**：DeepSeek V3/R1 系列（`model_type=deepseek_v3`）不要用 `head_dim`/`hidden_size/heads`，必须按 `qk_nope_head_dim + qk_rope_head_dim`（128+64=**192**）计算，见「核心规则 3」。
- **上下文异常大值**：个别模型 context 为 `1e18` 量级（异常），不要照抄，应置 null 或从真实来源补。
- **Step 系列（Step 3.5/3.7 Flash、Step3）**：config 的 MoE 键在 `text_config` 内（`use_moe`/`moe_num_experts`/`moe_top_k`），易被误判为 Dense；按流程递归查找即可正确判为 MoE。
- **多模态模型**（Qwen-VL、GLM 等）：text 部分字段在 `text_config`，优先取 `text_config`。
- **架构标注错误**：有的模型 active 远小于 total（MoE 特征）却标成 Dense，需按 config.json 复核并纠正。

## 目录结构

```
hf-model-params-fill/
├── SKILL.md                 # 本文件
└── fill_model_params.py     # 可复用填充脚本（单/批量、备份、验证）
```

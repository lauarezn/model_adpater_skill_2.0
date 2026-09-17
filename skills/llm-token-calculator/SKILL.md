---
name: llm-token-calculator
version: 1.0.0
description: LLM Token 计算器（独立计算引擎）——根据 GPU 硬件参数 + 模型参数 + 量化/推理配置，计算模型权重体积、KV Cache、Decode 速度、Prefill 时间、TTFT、吞吐与每日 Token 量等推理性能指标。算法口径与仓库 token_calculator.html 完全一致，服务于本仓库（model_adapter / 昇腾服务器大模型适配清单）的售前硬件估算与方案输出场景。
tags: [token, calculator, llm, inference, decode, prefill, ttft, throughput, 推理, 算力, 性能估算]
allowed_tools: [bash, read_file, write_file, edit_file, grep]
---

# LLM Token 计算器（独立计算引擎）

本 Skill 将 `token_calculator.html` 的 `recalc()` 计算逻辑抽离为**独立 Python 引擎**，算法口径与页面完全一致。
它是**纯计算型 Skill**（区别于编排型 `ascend-presales-recommend`），可被独立调用，也可作为硬件估算的底层引擎被其它 Skill 复用。

## 触发场景

- 售前工程师给定「GPU 型号 + 模型 + 量化精度 + 提示/生成长度」，需要算推理性能（Decode 速度 / Prefill 时间 / TTFT / 吞吐）。
- 需要判断某模型在给定单卡显存下是否放得下（模型权重 + KV Cache）。
- 需要估算多卡张量并行后的吞吐、每日可生成 Token 量、每百万 Token 显存读取量。
- 需要在方案输出中给出可解释、口径一致的性能指标。

## 核心原理

- **Prefill（处理输入）** = 算力密集 → 受 GPU FP16 TFLOPS 限制。
- **Decode（逐 Token 生成）** = 显存带宽密集 → 受 Memory Bandwidth 限制。每生成一个 Token，GPU 需把全部模型权重从显存读一遍。
- **MoE 模型**用「激活参数量」计算模型权重体积；Dense 模型激活参 = 总参。

## 数据依赖（仓库 data/ 目录，只读）

| 文件 | 用途 | 规模 | 关键字段 |
|------|------|------|----------|
| `data/gpu_lib.json` | GPU 参数库（与 Admin 共用） | 48 条 | name, bw, fp16, fp8, vram, memType, ic, price |
| `data/model-params.json` | 全球AI模型参数（与 Admin 共用） | 913 条 | modelCode, name, totalParams, activeParams, layers, attentionHeads, kvHeads, headDim, context, architecture, isMoE |

> 仅加载「可计算模型」：totalParams / layers / kvHeads / headDim 四项齐全才纳入；缺失字段自动跳过，不伪造。

## 计算口径（与 token_calculator.html 完全一致）

**精度 → 字节数：** FP32=4 | FP16/BF16=2 | INT8=1 | INT4=0.5 | INT2=0.25（KV Cache 无 INT2）

| 指标 | 公式 |
|------|------|
| 模型权重体积 (GB) | `激活参数 × 每参数字节数` |
| KV Cache 体积 (GB) | `2 × 层数 × KV头数 × 头维度 × seq × kvBytes / 1e9` |
| 总显存占用 (GB) | `模型权重 + KV Cache` |
| 理论 Decode (tok/s) | `显存带宽 ÷ 模型权重` |
| 考虑 KV 的理论速度 | `显存带宽 ÷ (权重 + KV)` |
| 实际 Decode（单卡） | `考虑KV理论 × 效率系数` |
| 多卡 TP 速度 | `(带宽 × 卡数) ÷ 权重 × 效率 × 通信系数` |
| 多卡每卡显存 | `总显存 ÷ GPU数量` |
| Prefill 时间 (ms) | `2 × 总参 × 提示长度 ÷ (FP16 × 卡数) × 1000` |
| 首 Token TTFT (ms) | `≈ Prefill 时间` |
| 生成总耗时 (秒) | `生成长度 ÷ 实际Decode速度` |
| 用户感知吞吐 (tok/s) | `生成长度 ÷ (Prefill秒 + 生成时间)` |
| 每 Token 算力 (GFLOPs) | `2 × 总参数量` |
| 每日可生成 Token | `实际速度 × 86400` |
| 每百万 Token 显存读取量 (GB) | `权重(GB) × 1,000,000` |

**参考效率系数：** llama.cpp(无优化)≈0.45~0.55 | vLLM≈0.60~0.75 | TensorRT-LLM≈0.70~0.85；多卡 TP 通信开销额外乘以 0.85~0.95（单卡填 1）。

## 使用方式

```bash
# 在仓库根目录运行
python3 skills/llm-token-calculator/token_calc.py \
  --gpu "华为昇腾910C" \
  --model "DeepSeek-V3" \
  --quant INT8 \
  --gpu-count 8 \
  --prompt-len 512 --gen-len 128000 \
  --efficiency 0.65 --tp-coef 0.92 --seq 8192

# 输出 JSON 到文件（供方案输出 / 编排器调用）
python3 skills/llm-token-calculator/token_calc.py --gpu "NVIDIA H100 SXM5" --model "Qwen2.5-72B" --out /tmp/token.json

# 指定非默认仓库根目录
python3 skills/llm-token-calculator/token_calc.py --repo /path/to/model_adapater --gpu "华为昇腾910C" --model "DeepSeek-V3"
```

## 输出契约

`build_report()` 返回 dict，写文件后为 JSON：

```
{
  "meta": { "gpu", "model", "model_code", "is_moe", "arch", "quant", "kv_prec",
            "gpu_count", "prompt_len", "gen_len", "efficiency", "tp_coef", "seq", "generated_at" },
  "gpu": { "bw", "fp16", "fp8", "vram", "memType", "ic", "price" },
  "model": { "name", "modelCode", "total", "active", "layers", "kvHeads", "headDim", "ctx", "arch", "moe" },
  "result": {
    "bytes_per_param", "kv_bytes", "weight_gb", "kv_gb", "total_vram_gb", "per_gpu_vram_gb",
    "enough_single_gpu", "theo_decode_toks", "theo_with_kv_toks", "actual_decode_toks",
    "tp_speed_toks", "prefill_ms", "ttft_ms", "gen_time_sec", "user_thru_toks",
    "per_token_gflops", "daily_tokens", "per_million_read_gb"
  }
}
```

## 可解释性

- 每个指标对应明确公式（见上表），数值来源可追溯。
- 实际速度标注「理论 × 效率系数」，估算值注明 ±20~30%（软件栈/驱动/温度影响），建议 POC 实测校准。
- 单卡显存是否放得下给出明确判定（`enough_single_gpu`），不足时提示需多卡或更低精度。

## 注意事项

- 本 Skill 是**纯计算引擎**：只读 `data/*.json`，**不修改**任何数据文件。
- 依赖 Python 标准库（`json`, `argparse`, `os`, `datetime`），无第三方依赖。
- 模型名匹配不区分大小写，支持展示名与 `modelCode` 两种输入。
- 可被 `ascend-presales-recommend` 等编排 Skill 以 `build_report()` 方式复用。

// ============ AI使能服务报价器 - 服务目录数据 ============
// 数据来源：2026年专业服务-专项服务-人天报价.xlsx
// 单人天单价：6000 元（表头标注）

const QUOTE_PRICE_PER_DAY = 6000; // 单人天单价（元）

// 服务类别（L1）
const QUOTE_CATEGORIES = [
  { id: 1, name: 'AI赋能' },
  { id: 2, name: 'AI基础开发与运行环境搭建' },
  { id: 3, name: '模型安装' },
  { id: 4, name: '应用搭建' },
  { id: 5, name: '硬件集群组网' },
  { id: 6, name: '维护升级' }
];

// 服务项（L2）。fields: code/name/desc/days/category/required
const QUOTE_SERVICES = [
  // ===== 1. AI赋能 =====
  { code: '45SC0109', name: '开发与运行环境部署赋能', desc: '基于昇腾开发环境的部署赋能', days: 2, category: 1, required: false },
  { code: '45SC0110', name: '集群环境搭建部署赋能', desc: '昇腾集群环境搭建赋能', days: 2, category: 1, required: false },
  { code: '45SC0111', name: '开发工具赋能', desc: '昇腾模型与应用开发支持、昇腾工具链使用赋能', days: 2, category: 1, required: false },
  { code: '45SC0133', name: '模型迁移/部署赋能', desc: '模型迁移/部署赋能', days: 2, category: 1, required: false },
  { code: '45SC0134', name: '本地化知识库/工作流赋能', desc: '对本地化知识库的构建以及工作流的灵活使用赋能', days: 2, category: 1, required: false },

  // ===== 2. AI基础开发与运行环境搭建 =====
  { code: '45SC0112', name: '安装部署评估与方案设计（必选）', desc: '依据客户需求，输出昇腾AI开发环境安装部署方案', days: 2, category: 2, required: true },
  { code: '45SC0113', name: '运行开发环境搭建', desc: '在昇腾节点上搭建模型/应用能够直接运行的环境，支持客户使用本地IDE（如MindStudio等）连接服务器或容器镜像环境，搭建昇腾远程开发、调试', days: 1, category: 2, required: false },
  { code: '45SC0114', name: '推理容器镜像', desc: '基于客户业务需要，制作推送需要的昇腾容器镜像', days: 2, category: 2, required: false },

  // ===== 3. 模型安装 =====
  { code: '45SC0115', name: '模型部署评估与方案设计（必选）', desc: '依据客户需求，输出昇腾模型部署评估与方案', days: 2, category: 3, required: true },
  { code: '42SC0118', name: '模型增量包（1人天/实例）', desc: '基于已部署模型实例的二次/多次增量部署，支持MindIE/vLLM多实例架构，含配置复制、端口调整、NPU资源分配、服务验证', days: 1, category: 3, required: false, perInstance: true },
  { code: '42SC0119', name: 'DeepSeek集群部署（8人天）', desc: 'DeepSeek 集群部署', days: 8, category: 3, required: false },
  { code: '45SC0135', name: '常规大模型部署', desc: 'DS满血版/量化版/蒸馏版等常规模型部署（单机单个）', days: 5, category: 3, required: false },
  { code: '42SC0120', name: '专项调优（单次15人天）', desc: '根据客户需求对模型性能调优', days: 15, category: 3, required: false },
  { code: '45SC0136', name: 'RAG模型部署', desc: 'embedding模型+rerank 模型推理服务部署', days: 3, category: 3, required: false },
  { code: '42SC0121', name: '模型迁移评估与方案设计（必选-单次）', desc: '依据客户需求，输出昇腾模型迁移评估与方案', days: 5, category: 3, required: false },
  { code: '42SC0122', name: '模型迁移(单个)', desc: '针对昇腾未发布的部分模型，支持客户实现模型迁移', days: 10, category: 3, required: false },

  // ===== 4. 应用搭建 =====
  { code: '45SC0137', name: '简易前端界面', desc: '搭建基础前端界面，灵活调度后台大模型推理服务接口（open WebUI）', days: 2, category: 4, required: false },
  { code: '45SC0138', name: 'RAG服务', desc: '根据客户需求基于容器构建开源大模型开发平台（单个）（dify/ragflow/anythingllm/bisheng/gpustack/ollama等）', days: 3, category: 4, required: false },
  { code: '45SC0139', name: '知识库/工作流demo构建', desc: '基于大模型开发平台构建简易版本知识库/工作流demo', days: 2, category: 4, required: false },

  // ===== 5. 硬件集群组网 =====
  { code: '45SC0120', name: '集群环境搭建方案设计', desc: '根据客户要求设计集群部署方案', days: 3, category: 5, required: false },
  { code: '45SC0121', name: '双机组网', desc: '双机进行组网环境搭建', days: 2, category: 5, required: false },
  { code: '45SC0122', name: '多机跨交换机组网', desc: '跨交换机进行多机组网环境搭建', days: 5, category: 5, required: false },
  { code: '45SC0123', name: '集群验证', desc: '依据验证用例，在集群环境中进行算法性能验证，输出验证报告', days: 5, category: 5, required: false },

  // ===== 6. 维护升级 =====
  { code: '45SC0124', name: '根据部署模型进行升级服务', desc: '根据部署模型进行升级维护，预计每年维护3-5次，每次预计5天', days: 20, category: 6, required: false }
];

// 供 LLM 匹配使用的服务目录文本（prompt 注入用）
function buildQuoteCatalogText() {
  const lines = [];
  for (const cat of QUOTE_CATEGORIES) {
    lines.push(`【${cat.id}. ${cat.name}】`);
    for (const s of QUOTE_SERVICES.filter(x => x.category === cat.id)) {
      const req = s.required ? '（必选）' : '';
      const per = s.perInstance ? '（按实例计）' : '';
      lines.push(`  - [${s.code}] ${s.name}${req}${per}：${s.desc}（${s.days}人天）`);
    }
  }
  return lines.join('\n');
}

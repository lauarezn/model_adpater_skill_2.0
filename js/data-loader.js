
// ============ 数据源配置（保留供参考）============
const VLLM_ASCEND_URL = 'https://docs.vllm.ai/projects/ascend/zh-cn/latest/user_guide/support_matrix/supported_models.html';
const VLLM_ASCEND_BASE = 'https://docs.vllm.ai/projects/ascend/zh-cn/latest/user_guide/support_matrix/';
const VLLM_OMNI_URL = 'https://docs.vllm.ai/projects/vllm-omni/en/latest/models/supported_models/';
const VLLM_OMNI_BASE = 'https://docs.vllm.ai/projects/vllm-omni/en/latest/models/supported_models/';
const SGLANG_ASCEND_URL = 'https://docs.sglang.io/docs/hardware-platforms/ascend-npus/ascend_npu_support_models';
const SGLANG_ASCEND_BASE = 'https://docs.sglang.io/docs/hardware-platforms/ascend-npus/';
const GITCODE_AI_URL = 'https://ai.gitcode.com/models?ascendNative=true';
const ASCEND_SACT_URL = 'https://gitcode.com/org/Ascend-SACT/repos';

// CORS 代理列表（保留供参考，浏览器端远程爬取已不再使用）
const CORS_PROXIES = [
  url => `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`,
  url => `https://corsproxy.io/?${encodeURIComponent(url)}`,
  url => `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(url)}`,
  url => `https://proxy.cors.sh/${url}`,
];

async function fetchWithProxy(url, timeoutMs = 15000) {
  for (const proxyFn of CORS_PROXIES) {
    try {
      const proxyUrl = proxyFn(url);
      const resp = await fetch(proxyUrl, { signal: AbortSignal.timeout(timeoutMs) });
      if (resp.ok) {
        const text = await resp.text();
        if (text && text.length > 100) return text;
      }
    } catch (e) {
      console.warn('Proxy failed:', e.message);
    }
  }
  // Last resort: direct fetch (may fail due to CORS)
  try {
    const resp = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    if (resp.ok) return await resp.text();
  } catch (e) {}
  return null;
}

// Build doc URL for a model name
function buildDocUrl(modelName, baseUrl) {
  const docMap = {
    'DeepSeek V4-Flash': 'DeepSeek-V4-Flash',
    'DeepSeek V4-Pro': 'DeepSeek-V4-Pro',
    'DeepSeek V3/3.1': 'DeepSeek-V3.1',
    'DeepSeek V3.2': 'DeepSeek-V3.2',
    'DeepSeek R1': 'DeepSeek-R1',
    'Qwen3-Dense': 'Qwen3-Dense',
    'Qwen3-30B-A3B': 'Qwen3-30B-A3B',
    'Qwen3-Coder-30B-A3B': 'Qwen3-Coder-30B-A3B',
    'Qwen3-235B-A22B': 'Qwen3-235B-A22B',
    'Qwen3-Next': 'Qwen3-Next',
    'GLM-4.x': 'GLM-4.x',
    'GLM-5/5.1': 'GLM-5',
    'GLM-5.2': 'GLM-5.2',
    'Gemma4': 'Gemma4',
    'Kimi-K2-Thinking': 'Kimi-K2-Thinking',
    'DeepSeekOCR2': 'DeepSeekOCR2',
    'MiniMax-M2.5/2.7': 'MiniMax-M2',
    'Qwen2.5-Math-RM-72B': 'Qwen2.5-Math-RM-72B',
    'Qwen3-VL': 'Qwen-VL-Dense',
    'Qwen3-VL-30B-A3B/Qwen3-VL-235B-A22B': 'Qwen3-VL-30B-A3B',
    'Qwen3.5-397B-A17B': 'Qwen3.5-397B-A17B',
    'Qwen3.5-27B / Qwen3.6-27B': 'Qwen3.5-27B',
    'Qwen3.6-35B-A3B': 'Qwen3.6-35B-A3B',
    'Qwen3-Omni-30B-A3B-Thinking': 'Qwen3-Omni-30B-A3B-Thinking',
    'Kimi-K2.5/Kimi-K2.6': 'Kimi-K2.5',
    'Qwen3-Embedding': 'Qwen3_embedding',
    'Qwen3-VL-Embedding': 'Qwen3-VL-Embedding',
    'Qwen3-Reranker': 'Qwen3_reranker',
    'Qwen3-VL-Reranker': 'Qwen3-VL-Reranker',
  };
  const slug = docMap[modelName];
  if (slug) return baseUrl + slug;
  const fallbackSlug = modelName.replace(/[^a-zA-Z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
  return baseUrl + fallbackSlug;
}

// ============ State ============
let models = [];

let dataSource = 'local';
let ascendModels = [];
let omniModels = [];

// ============ vLLM Ascend Data Parser ============
async function fetchAscendData() {
  const statusEl = document.getElementById('refreshStatus');
  const btn = document.getElementById('refreshBtn');

  try {
    const html = await fetchWithProxy(VLLM_ASCEND_URL);
    if (!html) return false;

    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const tables = doc.querySelectorAll('table');
    const parsedModels = [];

    tables.forEach((table) => {
      const prevText = table.previousElementSibling ? table.previousElementSibling.textContent : '';
      const prevPrevText = table.previousElementSibling?.previousElementSibling?.textContent || '';

      let category = 'LLM';
      if (prevText.includes('多模态语言模型') || prevPrevText.includes('多模态语言模型')) category = '多模态';
      if (prevText.includes('池化模型')) category = '嵌入/排序';

      const rows = table.querySelectorAll('tbody tr');
      rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length < 3) return;

        const modelCell = cells[0];
        const modelLink = modelCell.querySelector('a');
        const modelName = modelLink ? modelLink.textContent.trim() : modelCell.textContent.trim();
        const docHref = modelLink ? modelLink.getAttribute('href') : '';

        const supportCell = cells[1];
        const supportText = supportCell.textContent.trim();

        let supportLevel = '扩展兼容';
        if (supportText.includes('✅')) supportLevel = '✅ 已支持';
        else if (supportText.includes('🔵')) supportLevel = '🔵 实验性';
        else if (supportText.includes('❌')) return;

        let supportedHardware = 'A2/A3';
        for (let i = 2; i < cells.length; i++) {
          const header = table.querySelectorAll('thead th')[i];
          if (header && header.textContent.trim() === '支持的硬件') {
            supportedHardware = cells[i].textContent.trim() || 'A2/A3';
            break;
          }
        }

        let docUrl = '';
        for (let i = 2; i < cells.length; i++) {
          const header = table.querySelectorAll('thead th')[i];
          if (header && header.textContent.trim() === '文档') {
            const docLink = cells[i].querySelector('a');
            if (docLink) {
              let href = docLink.getAttribute('href');
              if (href && !href.startsWith('http')) href = VLLM_ASCEND_BASE + href;
              docUrl = href;
            }
            break;
          }
        }
        if (!docUrl && docHref) {
          docUrl = docHref.startsWith('http') ? docHref : VLLM_ASCEND_BASE + docHref;
        }

        let maxLen = '';
        for (let i = 2; i < cells.length; i++) {
          const header = table.querySelectorAll('thead th')[i];
          if (header && header.textContent.trim().includes('最大模型长度')) {
            maxLen = cells[i].textContent.trim();
            break;
          }
        }

        let developer = '社区';
        if (modelName.includes('DeepSeek')) developer = '深度求索';
        else if (modelName.includes('Qwen')) developer = '阿里云';
        else if (modelName.includes('GLM') || modelName.includes('ChatGLM') || modelName.includes('CodeGeeX')) developer = '智谱AI';
        else if (modelName.includes('Baichuan')) developer = '百川智能';
        else if (modelName.includes('LLaMA') || modelName.includes('Llama')) developer = 'Meta';
        else if (modelName.includes('Yi')) developer = '零一万物';
        else if (modelName.includes('Intern')) developer = '上海AI实验室';
        else if (modelName.includes('Mistral') || modelName.includes('Mixtral')) developer = 'Mistral AI';
        else if (modelName.includes('MiniCPM')) developer = '面壁智能';
        else if (modelName.includes('Phi')) developer = 'Microsoft';
        else if (modelName.includes('Gemma')) developer = 'Google';
        else if (modelName.includes('Kimi')) developer = '月之暗面';
        else if (modelName.includes('MiniMax')) developer = 'MiniMax';
        else if (modelName.includes('Ernie')) developer = '百度';
        else if (modelName.includes('LLaVA')) developer = '社区';
        else if (modelName.includes('Aria')) developer = 'Rhymes AI';
        else if (modelName.includes('Florence')) developer = 'Microsoft';
        else if (modelName.includes('Whisper')) developer = 'OpenAI';
        else if (modelName.includes('PaddleOCR')) developer = '百度';
        else if (modelName.includes('QVQ')) developer = '阿里云';
        else if (modelName.includes('Molmo')) developer = 'Allen AI';
        else if (modelName.includes('Bert') || modelName.includes('RoBERTa')) developer = 'Google';

        let architecture = 'Transformer';
        if (modelName.includes('MoE') || modelName.includes('A3B') || modelName.includes('A22B')) architecture = 'MoE';
        else if (modelName.includes('VL') || modelName.includes('Vision') || modelName.includes('Omni')) architecture = 'Vision-Language';
        else if (modelName.includes('Diffusion') || modelName.includes('SD')) architecture = 'Diffusion';
        else if (modelName.includes('Reward') || modelName.includes('RM')) architecture = 'Reward Model';
        else if (modelName.includes('Embedding') || modelName.includes('Reranker')) architecture = 'Embedding';
        else if (modelName.includes('OCR')) architecture = 'Vision-Language';

        const tags = [category];
        if (architecture === 'MoE') tags.push('MoE');
        if (modelName.includes('VL') || modelName.includes('Vision') || modelName.includes('Omni')) tags.push('视觉');
        if (modelName.includes('Coder') || modelName.includes('Code')) tags.push('代码');
        if (modelName.includes('OCR')) tags.push('OCR');
        if (modelName.includes('Embedding')) tags.push('嵌入');
        if (modelName.includes('Reranker')) tags.push('排序');
        if (modelName.includes('Audio')) tags.push('音频');
        if (modelName.includes('Thinking') || modelName.includes('R1')) tags.push('推理');
        if (modelName.includes('Math')) tags.push('数学');

        const id = modelName.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');

        parsedModels.push({
          id, name: modelName, category, developer,
          parameters: maxLen ? `支持 ${maxLen} 上下文` : '多尺寸',
          architecture, supportLevel, framework: 'PyTorch',
          minHardware: supportedHardware.includes('A2') ? 'Atlas 800I A3' : 'Atlas 800T A3',
          recommendedHardware: supportedHardware.includes('A3') ? 'Atlas 800T A3' : 'Atlas 800I A3',
          inferencePerf: supportLevel === '✅ 已支持' ? '优' : '良',
          trainingPerf: '良',
          mindsporeSupport: ['阿里云','智谱AI','百川智能','上海AI实验室','面壁智能','深度求索'].includes(developer) ? '支持' : '需迁移',
          cannVersion: '7.0+',
          notes: `vLLM Ascend ${supportLevel} · 硬件: ${supportedHardware}`,
          tags, docUrl, source: 'vLLM Ascend'
        });
      });
    });

    ascendModels = parsedModels;
    return parsedModels.length > 0;
  } catch (e) {
    console.warn('vLLM Ascend获取失败:', e.message);
    return false;
  }
}

// ============ vLLM Omni Data Parser ============
async function fetchOmniData() {
  try {
    const html = await fetchWithProxy(VLLM_OMNI_URL);
    if (!html) return false;

    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const tables = doc.querySelectorAll('table');
    const parsedModels = [];

    tables.forEach((table) => {
      const rows = table.querySelectorAll('tbody tr');
      rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length < 4) return;

        const archCell = cells[0];
        const modelCell = cells[1];
        const hfCell = cells[2];
        const ascendCell = cells[3]; // Ascend NPU column

        const archName = archCell.textContent.trim();
        const modelName = modelCell.textContent.trim();
        const hfModels = hfCell.textContent.trim();
        const ascendSupport = ascendCell.textContent.trim();

        // Only include models that support Ascend NPU
        if (!ascendSupport.includes('✅')) return;

        // Parse individual model names from the cell
        const modelNames = modelName.split(',').map(s => s.trim()).filter(Boolean);
        // Also try to extract from HF models
        const hfNames = hfModels.split(',').map(s => s.trim()).filter(Boolean);

        // Use the model names from the "Models" column
        const namesToAdd = modelNames.length > 0 ? modelNames : [modelName];

        namesToAdd.forEach(name => {
          // Clean up model name
          let cleanName = name.replace(/\(.*?\)/g, '').trim();
          if (!cleanName) cleanName = name;

          // Determine category based on model type
          let category = '多模态';
          if (cleanName.includes('TTS') || cleanName.includes('Audio') || cleanName.includes('Voice') || cleanName.includes('Speech') || cleanName.includes('Singer') || cleanName.includes('SVC')) category = '语音';
          else if (cleanName.includes('Video') || cleanName.includes('T2V') || cleanName.includes('I2V') || cleanName.includes('V2V') || cleanName.includes('S2V')) category = '视频生成';
          else if (cleanName.includes('Image') || cleanName.includes('Edit') || cleanName.includes('DiT') || cleanName.includes('Diffusion') || cleanName.includes('SD') || cleanName.includes('FLUX') || cleanName.includes('Pipeline')) category = '图像生成';
          else if (cleanName.includes('Omni') || cleanName.includes('Omni')) category = '多模态';
          else if (cleanName.includes('Robot') || cleanName.includes('VLA') || cleanName.includes('GR00T')) category = '具身智能';

          // Determine developer
          let developer = '社区';
          if (cleanName.includes('Qwen')) developer = '阿里云';
          else if (cleanName.includes('GLM') || cleanName.includes('GLM')) developer = '智谱AI';
          else if (cleanName.includes('Intern') || cleanName.includes('InternVL')) developer = '上海AI实验室';
          else if (cleanName.includes('MiniCPM')) developer = '面壁智能';
          else if (cleanName.includes('Mistral') || cleanName.includes('Voxtral')) developer = 'Mistral AI';
          else if (cleanName.includes('Phi')) developer = 'Microsoft';
          else if (cleanName.includes('Gemma')) developer = 'Google';
          else if (cleanName.includes('Stable') || cleanName.includes('SD')) developer = 'Stability AI';
          else if (cleanName.includes('FLUX')) developer = 'Black Forest Labs';
          else if (cleanName.includes('Wan') || cleanName.includes('Wan')) developer = 'Wan AI';
          else if (cleanName.includes('Cosmos')) developer = 'NVIDIA';
          else if (cleanName.includes('Hunyuan')) developer = '腾讯';
          else if (cleanName.includes('LTX')) developer = 'Lightricks';
          else if (cleanName.includes('BAGEL') || cleanName.includes('ByteDance') || cleanName.includes('Mammoth')) developer = '字节跳动';
          else if (cleanName.includes('Helios')) developer = 'BestWishYsh';
          else if (cleanName.includes('MagiHuman')) developer = 'SII-GAIR';
          else if (cleanName.includes('Ovis')) developer = 'OvisAI';
          else if (cleanName.includes('LongCat') || cleanName.includes('meituan')) developer = '美团';
          else if (cleanName.includes('CosyVoice') || cleanName.includes('FunAudio')) developer = 'FunAudioLLM';
          else if (cleanName.includes('OmniVoice') || cleanName.includes('k2-fsa')) developer = 'k2-fsa';
          else if (cleanName.includes('VoxCPM') || cleanName.includes('openbmb')) developer = 'OpenBMB';
          else if (cleanName.includes('Ming') || cleanName.includes('inclusionAI')) developer = 'Inclusion AI';
          else if (cleanName.includes('MOSS')) developer = 'OpenMOSS';
          else if (cleanName.includes('Higgs') || cleanName.includes('bosonai')) developer = 'Boson AI';
          else if (cleanName.includes('IndexTTS')) developer = 'IndexTeam';
          else if (cleanName.includes('NextStep') || cleanName.includes('stepfun')) developer = '阶跃星辰';
          else if (cleanName.includes('MiMo') || cleanName.includes('Xiaomi')) developer = '小米';
          else if (cleanName.includes('Fish') || cleanName.includes('fishaudio')) developer = 'Fish Audio';
          else if (cleanName.includes('DreamID')) developer = 'XuGuo699';
          else if (cleanName.includes('SenseNova')) developer = '商汤';
          else if (cleanName.includes('Lance')) developer = '字节跳动';
          else if (cleanName.includes('Ernie') || cleanName.includes('ERNIE') || cleanName.includes('baidu')) developer = '百度';
          else if (cleanName.includes('HiDream')) developer = 'HiDream';
          else if (cleanName.includes('Krea')) developer = 'Krea';
          else if (cleanName.includes('DreamZero') || cleanName.includes('GEAR')) developer = 'GEAR Dreams';
          else if (cleanName.includes('Dynin') || cleanName.includes('snu')) developer = 'SNU';
          else if (cleanName.includes('Covo') || cleanName.includes('tencent')) developer = '腾讯';
          else if (cleanName.includes('OmniGen')) developer = 'OmniGen';
          else if (cleanName.includes('SoulX')) developer = 'Soul AI Lab';
          else if (cleanName.includes('AudioX')) developer = 'zhangj1an';
          else if (cleanName.includes('GR00T') || cleanName.includes('nvidia')) developer = 'NVIDIA';

          // Determine architecture
          let architecture = 'Transformer';
          if (cleanName.includes('MoE') || cleanName.includes('MoT')) architecture = 'MoE';
          else if (cleanName.includes('Diffusion') || cleanName.includes('DiT') || cleanName.includes('Pipeline')) architecture = 'Diffusion';
          else if (cleanName.includes('VL') || cleanName.includes('Vision') || cleanName.includes('Omni')) architecture = 'Vision-Language';
          else if (cleanName.includes('TTS') || cleanName.includes('Voice') || cleanName.includes('Speech') || cleanName.includes('Singer') || cleanName.includes('Audio')) architecture = '语音模型';
          else if (cleanName.includes('Reward') || cleanName.includes('RM')) architecture = 'Reward Model';
          else if (cleanName.includes('VLA')) architecture = 'VLA';

          // Determine support level
          let supportLevel = '✅ 已支持';
          if (cleanName.includes('experimental') || cleanName.includes('Experimental')) supportLevel = '🔵 实验性';

          // Determine tags
          const tags = [category];
          if (architecture === 'MoE') tags.push('MoE');
          if (cleanName.includes('VL') || cleanName.includes('Vision') || cleanName.includes('Image')) tags.push('视觉');
          if (cleanName.includes('Video') || cleanName.includes('T2V') || cleanName.includes('I2V')) tags.push('视频');
          if (cleanName.includes('TTS') || cleanName.includes('Voice') || cleanName.includes('Speech')) tags.push('语音合成');
          if (cleanName.includes('Audio')) tags.push('音频');
          if (cleanName.includes('Edit')) tags.push('编辑');
          if (cleanName.includes('Diffusion') || cleanName.includes('DiT')) tags.push('扩散模型');
          if (cleanName.includes('Robot') || cleanName.includes('VLA')) tags.push('具身智能');
          if (cleanName.includes('Singer') || cleanName.includes('SVC')) tags.push('歌声合成');

          const id = cleanName.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');

          // Extract HF model link
          let hfLink = '';
          const hfLinkEl = hfCell.querySelector('a');
          if (hfLinkEl) hfLink = hfLinkEl.getAttribute('href') || '';

          parsedModels.push({
            id, name: cleanName, category, developer,
            parameters: '多尺寸',
            architecture, supportLevel, framework: 'PyTorch',
            minHardware: 'Atlas 800I A3',
            recommendedHardware: 'Atlas 800T A3',
            inferencePerf: '良',
            trainingPerf: '良',
            mindsporeSupport: '需迁移',
            cannVersion: '7.0+',
            notes: `vLLM Omni 支持 · 架构: ${archName}`,
            tags, docUrl: hfLink, source: 'vLLM Omni',
            archName
          });
        });
      });
    });

    omniModels = parsedModels;
    return parsedModels.length > 0;
  } catch (e) {
    console.warn('vLLM Omni获取失败:', e.message);
    return false;
  }
}

// ============ SGLang Ascend Data Parser ============
let sglangModels = [];
let gitcodeModels = [];
let sactModels = [];

async function fetchSGLangData() {
  try {
    const html = await fetchWithProxy(SGLANG_ASCEND_URL);
    if (!html) return false;

    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const tables = doc.querySelectorAll('table');
    const parsedModels = [];

    tables.forEach((table) => {
      const rows = table.querySelectorAll('tbody tr');
      rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length < 2) return;

        const modelName = cells[0].textContent.trim();
        if (!modelName) return;

        // Determine category
        let category = 'LLM';
        if (modelName.includes('VL') || modelName.includes('Vision') || modelName.includes('Omni')) category = '多模态';
        else if (modelName.includes('Coder') || modelName.includes('Code')) category = '代码';
        else if (modelName.includes('Audio') || modelName.includes('Voice') || modelName.includes('Speech')) category = '语音';
        else if (modelName.includes('Embedding') || modelName.includes('Reranker')) category = '嵌入/排序';

        // Determine developer
        let developer = '社区';
        if (modelName.includes('DeepSeek')) developer = '深度求索';
        else if (modelName.includes('Qwen')) developer = '阿里云';
        else if (modelName.includes('GLM') || modelName.includes('ChatGLM') || modelName.includes('CodeGeeX')) developer = '智谱AI';
        else if (modelName.includes('Baichuan')) developer = '百川智能';
        else if (modelName.includes('LLaMA') || modelName.includes('Llama')) developer = 'Meta';
        else if (modelName.includes('Yi')) developer = '零一万物';
        else if (modelName.includes('Intern')) developer = '上海AI实验室';
        else if (modelName.includes('Mistral') || modelName.includes('Mixtral')) developer = 'Mistral AI';
        else if (modelName.includes('MiniCPM')) developer = '面壁智能';
        else if (modelName.includes('Phi')) developer = 'Microsoft';
        else if (modelName.includes('Gemma')) developer = 'Google';
        else if (modelName.includes('Kimi')) developer = '月之暗面';
        else if (modelName.includes('MiniMax')) developer = 'MiniMax';
        else if (modelName.includes('Ernie')) developer = '百度';
        else if (modelName.includes('Stable') || modelName.includes('SD')) developer = 'Stability AI';
        else if (modelName.includes('Whisper')) developer = 'OpenAI';

        // Determine architecture
        let architecture = 'Transformer';
        if (modelName.includes('MoE') || modelName.includes('A3B') || modelName.includes('A22B')) architecture = 'MoE';
        else if (modelName.includes('VL') || modelName.includes('Vision') || modelName.includes('Omni')) architecture = 'Vision-Language';
        else if (modelName.includes('Diffusion') || modelName.includes('SD')) architecture = 'Diffusion';
        else if (modelName.includes('Embedding')) architecture = 'Embedding';

        // Determine support level
        let supportLevel = '✅ 已支持';
        if (modelName.includes('experimental') || modelName.includes('Experimental')) supportLevel = '🔵 实验性';

        const tags = [category];
        if (architecture === 'MoE') tags.push('MoE');
        if (modelName.includes('VL') || modelName.includes('Vision') || modelName.includes('Omni')) tags.push('视觉');
        if (modelName.includes('Coder') || modelName.includes('Code')) tags.push('代码');
        if (modelName.includes('Embedding')) tags.push('嵌入');
        if (modelName.includes('Reranker')) tags.push('排序');
        if (modelName.includes('Audio')) tags.push('音频');
        if (modelName.includes('Thinking') || modelName.includes('R1')) tags.push('推理');

        const id = modelName.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');

        parsedModels.push({
          id, name: modelName, category, developer,
          parameters: '多尺寸',
          architecture, supportLevel, framework: 'PyTorch',
          minHardware: 'Atlas 800I A3',
          recommendedHardware: 'Atlas 800T A3',
          inferencePerf: '良',
          trainingPerf: '良',
          mindsporeSupport: '需迁移',
          cannVersion: '7.0+',
          notes: `SGLang Ascend 支持`,
          tags, docUrl: '', source: 'SGLang Ascend'
        });
      });
    });

    sglangModels = parsedModels;
    return parsedModels.length > 0;
  } catch (e) {
    console.warn('SGLang Ascend获取失败:', e.message);
    return false;
  }
}

// ============ GitCode AI Data Parser ============
async function fetchGitCodeData() {
  try {
    const html = await fetchWithProxy(GITCODE_AI_URL);
    if (!html) return false;

    // Parse Next.js dehydrated data from self.__next_f.push entries
    const pushMatches = html.matchAll(/self\.__next_f\.push\(\[1,"(.*?)"\]\)/g);
    let allContent = [];
    let totalCount = 0;

    for (const match of pushMatches) {
      let decoded;
      try {
        decoded = match[1].replace(/\\(.)/g, (_, c) => c === 'n' ? '\n' : c === 't' ? '\t' : c === '\\' ? '\\' : c === '"' ? '"' : c);
      } catch (e) {
        continue;
      }

      // Look for React Query cache data pattern
      if (!decoded.includes('aiProjectsSearch')) continue;

      // Find the data object: look for "data":{"page_num":...
      const dataIdx = decoded.indexOf('"data":{"page_num"');
      if (dataIdx < 0) continue;

      const dataStart = dataIdx + '"data":'.length;
      let depth = 0, endIdx = 0;
      for (let i = dataStart; i < decoded.length; i++) {
        if (decoded[i] === '{') depth++;
        else if (decoded[i] === '}') { depth--; if (depth === 0) { endIdx = i + 1; break; } }
      }
      if (!endIdx) continue;

      try {
        const dataObj = JSON.parse(decoded.substring(dataStart, dataStart + endIdx));
        if (dataObj.content && Array.isArray(dataObj.content)) {
          allContent = dataObj.content;
          totalCount = parseInt(dataObj.total) || 0;
          break;
        }
      } catch (e) {
        continue;
      }
    }

    if (allContent.length === 0) return false;

    const parsedModels = [];

    allContent.forEach(m => {
      const name = m.name || '';
      const namespace = m.namespace || '';
      const webUrl = m.web_url || '';
      const description = m.description || '';
      const task = m.task && m.task.length > 0 ? m.task[0] : null;
      const taskName = task ? (task.name_en || '') : '';
      const licenseInfo = m.license && m.license.length > 0 ? m.license[0] : null;
      const licenseName = licenseInfo ? (licenseInfo.code || '') : '';
      const downloadCount = m.download_count || 0;
      const starCount = m.star_count || 0;
      const creatorName = m.creator_name || '';
      const namespaceInfo = m.namespace_info || {};
      const orgName = namespaceInfo.name || '';

      // Determine category based on task
      let category = 'LLM';
      if (taskName.includes('Audio') || taskName.includes('Speech') || taskName.includes('Voice')) category = '语音';
      else if (taskName.includes('Image') || taskName.includes('Visual') || taskName.includes('Video')) category = '多模态';
      else if (taskName.includes('Feature') || taskName.includes('Embedding')) category = '嵌入/排序';
      else if (taskName.includes('Document') || taskName.includes('QA')) category = '多模态';
      else if (taskName.includes('Text')) category = 'LLM';
      else if (name.includes('VL') || name.includes('Vision') || name.includes('Omni') || name.includes('Image') || name.includes('Diffusion')) category = '多模态';
      else if (name.includes('Audio') || name.includes('Voice') || name.includes('Speech') || name.includes('ASR') || name.includes('TTS')) category = '语音';
      else if (name.includes('Embedding') || name.includes('Reranker')) category = '嵌入/排序';
      else if (name.includes('Coder') || name.includes('Code')) category = '代码';

      // Determine developer
      let developer = '社区';
      if (name.includes('DeepSeek')) developer = '深度求索';
      else if (name.includes('Qwen')) developer = '阿里云';
      else if (name.includes('GLM') || name.includes('ChatGLM') || name.includes('CodeGeeX')) developer = '智谱AI';
      else if (name.includes('Baichuan')) developer = '百川智能';
      else if (name.includes('LLaMA') || name.includes('Llama')) developer = 'Meta';
      else if (name.includes('Yi')) developer = '零一万物';
      else if (name.includes('Intern')) developer = '上海AI实验室';
      else if (name.includes('Mistral') || name.includes('Mixtral')) developer = 'Mistral AI';
      else if (name.includes('MiniCPM')) developer = '面壁智能';
      else if (name.includes('Phi')) developer = 'Microsoft';
      else if (name.includes('Gemma')) developer = 'Google';
      else if (name.includes('Kimi')) developer = '月之暗面';
      else if (name.includes('MiniMax')) developer = 'MiniMax';
      else if (name.includes('Ernie')) developer = '百度';
      else if (name.includes('Stable') || name.includes('SD')) developer = 'Stability AI';
      else if (name.includes('Whisper')) developer = 'OpenAI';
      else if (name.includes('openPangu') || name.includes('Pangu')) developer = '华为';
      else if (name.includes('Hunyuan')) developer = '腾讯';
      else if (name.includes('RoseTTAFold') || name.includes('AIMNet')) developer = 'AI4Science';
      else if (orgName.includes('Ascend') || orgName.includes('ascend')) developer = '华为';
      else if (orgName.includes('atomgit')) developer = '华为';

      // Determine architecture
      let architecture = 'Transformer';
      if (name.includes('MoE') || name.includes('A3B') || name.includes('A22B')) architecture = 'MoE';
      else if (name.includes('VL') || name.includes('Vision') || name.includes('Omni')) architecture = 'Vision-Language';
      else if (name.includes('Diffusion') || name.includes('SD')) architecture = 'Diffusion';
      else if (name.includes('Embedding') || name.includes('Reranker')) architecture = 'Embedding';

      const tags = [category];
      if (architecture === 'MoE') tags.push('MoE');
      if (name.includes('VL') || name.includes('Vision') || name.includes('Omni')) tags.push('视觉');
      if (name.includes('Coder') || name.includes('Code')) tags.push('代码');
      if (name.includes('Embedding')) tags.push('嵌入');
      if (name.includes('Reranker')) tags.push('排序');
      if (name.includes('Audio') || name.includes('Voice') || name.includes('Speech') || name.includes('ASR')) tags.push('音频');
      if (name.includes('Thinking') || name.includes('R1')) tags.push('推理');

      const id = name.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');

      parsedModels.push({
        id, name, category, developer,
        parameters: downloadCount > 1000 ? `下载 ${(downloadCount/1000).toFixed(1)}k` : `下载 ${downloadCount}`,
        architecture, supportLevel: '✅ 已支持', framework: 'PyTorch',
        minHardware: 'Atlas 800I A3',
        recommendedHardware: 'Atlas 800T A3',
        inferencePerf: '良',
        trainingPerf: '良',
        mindsporeSupport: ['华为','阿里云','智谱AI','百川智能','上海AI实验室','面壁智能','深度求索'].includes(developer) ? '支持' : '需迁移',
        cannVersion: '7.0+',
        notes: `GitCode AI · 昇腾原生 · ${webUrl}`,
        tags, docUrl: webUrl, source: 'GitCode AI'
      });
    });

    gitcodeModels = parsedModels;
    return parsedModels.length > 0;
  } catch (e) {
    console.warn('GitCode AI获取失败:', e.message);
    return false;
  }
}

// ============ Ascend-SACT Data Parser ============
async function fetchAscendSACTData() {
  try {
    // First page to determine total count and pagination
    const firstHtml = await fetchWithProxy(ASCEND_SACT_URL);
    if (!firstHtml) return false;

    // Extract total count from the page
    const totalMatch = firstHtml.match(/总计:\s*(\d+)/);
    const totalCount = totalMatch ? parseInt(totalMatch[1]) : 0;
    if (totalCount === 0) return false;

    // Determine page size and total pages
    // GitCode shows ~20 items per page
    const pageSize = 20;
    const totalPages = Math.ceil(totalCount / pageSize);

    // Fetch all pages in parallel
    // For paginated pages, try direct fetch first (GitCode may allow it),
    // then fall back to CORS proxy
    const pageUrls = [];
    for (let page = 2; page <= totalPages; page++) {
      pageUrls.push(`${ASCEND_SACT_URL}?page=${page}`);
    }

    const allHtmls = [firstHtml];
    if (pageUrls.length > 0) {
      // Try direct fetch for all pages first (faster, no CORS proxy overhead)
      const directResults = await Promise.allSettled(
        pageUrls.map(url => fetch(url, { signal: AbortSignal.timeout(10000) }).then(r => r.ok ? r.text() : null))
      );

      const failedUrls = [];
      directResults.forEach((r, i) => {
        if (r.status === 'fulfilled' && r.value && r.value.length > 100) {
          allHtmls.push(r.value);
        } else {
          failedUrls.push(pageUrls[i]);
        }
      });

      // For pages that failed direct fetch, try CORS proxy
      if (failedUrls.length > 0) {
        const proxyResults = await Promise.allSettled(
          failedUrls.map(url => fetchWithProxy(url))
        );
        proxyResults.forEach(r => {
          if (r.status === 'fulfilled' && r.value) {
            allHtmls.push(r.value);
          }
        });
      }
    }

    // Parse all pages
    const parsedModels = [];
    const seenNames = new Set();

    for (const html of allHtmls) {
      const repoMatches = html.matchAll(/<a[^>]*href="\/Ascend-SACT\/([^"\/]+)"[^>]*>([^<]+)<\/a>/g);

      for (const match of repoMatches) {
        const repoName = match[1].trim();
        if (!repoName || seenNames.has(repoName)) continue;
        seenNames.add(repoName);

        // Skip non-model repos
        if (repoName === 'Ascend-SACT-README' || repoName === '.github' || repoName.includes('docker') || repoName.includes('benchmark')) continue;

        const name = repoName.replace(/-/g, ' ').replace(/_/g, ' ');

        // Determine category based on name
        let category = 'LLM';
        if (name.includes('VL') || name.includes('Vision') || name.includes('Image') || name.includes('OCR') || name.includes('Diffusion') || name.includes('SD')) category = '多模态';
        else if (name.includes('Audio') || name.includes('Voice') || name.includes('Speech') || name.includes('ASR') || name.includes('TTS')) category = '语音';
        else if (name.includes('Embedding') || name.includes('Reranker')) category = '嵌入/排序';
        else if (name.includes('Coder') || name.includes('Code')) category = '代码';
        else if (name.includes('Timer') || name.includes('Forecast') || name.includes('Time')) category = '时序';
        else if (name.includes('Fold') || name.includes('Science') || name.includes('Chem')) category = '科学计算';

        // Determine developer
        let developer = '华为';
        if (name.includes('DeepSeek')) developer = '深度求索';
        else if (name.includes('Qwen')) developer = '阿里云';
        else if (name.includes('GLM') || name.includes('ChatGLM') || name.includes('CodeGeeX')) developer = '智谱AI';
        else if (name.includes('Baichuan')) developer = '百川智能';
        else if (name.includes('LLaMA') || name.includes('Llama')) developer = 'Meta';
        else if (name.includes('Yi')) developer = '零一万物';
        else if (name.includes('Intern')) developer = '上海AI实验室';
        else if (name.includes('Mistral') || name.includes('Mixtral')) developer = 'Mistral AI';
        else if (name.includes('MiniCPM')) developer = '面壁智能';
        else if (name.includes('Phi')) developer = 'Microsoft';
        else if (name.includes('Gemma')) developer = 'Google';
        else if (name.includes('Kimi')) developer = '月之暗面';
        else if (name.includes('MiniMax') || name.includes('MINIMAX')) developer = 'MiniMax';
        else if (name.includes('Ernie')) developer = '百度';
        else if (name.includes('Stable') || name.includes('SD')) developer = 'Stability AI';
        else if (name.includes('Whisper')) developer = 'OpenAI';
        else if (name.includes('Pangu') || name.includes('openPangu')) developer = '华为';
        else if (name.includes('Hunyuan')) developer = '腾讯';
        else if (name.includes('FireRed')) developer = '华为';

        // Determine architecture
        let architecture = 'Transformer';
        if (name.includes('MoE') || name.includes('A3B') || name.includes('A22B') || name.includes('W8A8') || name.includes('W4A8')) architecture = 'MoE';
        else if (name.includes('VL') || name.includes('Vision') || name.includes('Omni')) architecture = 'Vision-Language';
        else if (name.includes('Diffusion') || name.includes('SD')) architecture = 'Diffusion';
        else if (name.includes('Embedding') || name.includes('Reranker')) architecture = 'Embedding';

        const tags = [category];
        if (architecture === 'MoE') tags.push('MoE');
        if (name.includes('VL') || name.includes('Vision') || name.includes('Omni')) tags.push('视觉');
        if (name.includes('Coder') || name.includes('Code')) tags.push('代码');
        if (name.includes('Audio') || name.includes('Voice') || name.includes('Speech') || name.includes('ASR')) tags.push('音频');
        if (name.includes('R1') || name.includes('Thinking')) tags.push('推理');

        const id = repoName.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
        const docUrl = `https://gitcode.com/Ascend-SACT/${repoName}`;

        parsedModels.push({
          id, name: repoName, category, developer,
          parameters: '',
          architecture, supportLevel: '✅ 已支持', framework: 'PyTorch',
          minHardware: 'Atlas 800I A3',
          recommendedHardware: 'Atlas 800T A3',
          inferencePerf: '良',
          trainingPerf: '良',
          mindsporeSupport: '支持',
          cannVersion: '7.0+',
          notes: `Ascend-SACT · ${docUrl}`,
          tags, docUrl, source: 'Ascend-SACT'
        });
      }
    }

    sactModels = parsedModels;
    return parsedModels.length > 0;
  } catch (e) {
    console.warn('Ascend-SACT获取失败:', e.message);
    return false;
  }
}

// ============ Merge models from both sources ============
function mergeModels() {
  const merged = [];
  const seen = new Set();

  // Add Ascend models first (higher priority)
  ascendModels.forEach(m => {
    const key = m.name.toLowerCase().replace(/[\s/-]/g, '');
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(m);
    }
  });

  // Add Omni models that are not already in Ascend
  omniModels.forEach(m => {
    const key = m.name.toLowerCase().replace(/[\s/-]/g, '');
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(m);
    }
  });

  // Add SGLang models that are not already in Ascend or Omni
  sglangModels.forEach(m => {
    const key = m.name.toLowerCase().replace(/[\s/-]/g, '');
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(m);
    }
  });

  // Add GitCode AI models that are not already in Ascend, Omni or SGLang
  gitcodeModels.forEach(m => {
    const key = m.name.toLowerCase().replace(/[\s/-]/g, '');
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(m);
    }
  });

  // Add Ascend-SACT models that are not already in the list
  sactModels.forEach(m => {
    const key = m.name.toLowerCase().replace(/[\s/-]/g, '');
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(m);
    }
  });

  return merged;
}

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'https://ai.gitcode.com/models?ascendNative=true';
const OUTPUT_FILE = path.join(__dirname, 'data', 'gitcode_models_full.json');

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function crawlPage(page, pageNum) {
  const url = `${BASE_URL}&page=${pageNum}`;
  console.log(`[Page ${pageNum}] 正在访问: ${url}`);
  
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  
  // 等待模型卡片加载
  try {
    await page.waitForSelector('a[href*="/model/"]', { timeout: 15000 });
  } catch(e) {
    console.log(`[Page ${pageNum}] 未找到模型卡片，尝试等待更长时间...`);
    await sleep(5000);
  }
  
  // 等待页面完全渲染
  await sleep(3000);
  
  // 提取模型数据
  const models = await page.evaluate(() => {
    const cards = document.querySelectorAll('a[href*="/model/"]');
    const results = [];
    
    cards.forEach(card => {
      try {
        // 模型名称
        const nameEl = card.querySelector('.font-mono, [class*="font-mono"], h3, .model-name, [class*="name"]');
        const name = nameEl ? nameEl.textContent.trim() : '';
        
        if (!name) return;
        
        // 模型链接
        const href = card.getAttribute('href') || '';
        const fullUrl = href.startsWith('http') ? href : `https://ai.gitcode.com${href}`;
        
        // 描述
        const descEl = card.querySelector('p, .desc, [class*="desc"], .description');
        const description = descEl ? descEl.textContent.trim() : '';
        
        // 参数量
        const paramsEl = card.querySelector('[class*="param"], [class*="size"], [class*="badge"]');
        const params = paramsEl ? paramsEl.textContent.trim() : '';
        
        // 更新时间
        const timeEl = card.querySelector('[class*="time"], [class*="date"], [class*="update"]');
        const updatedAt = timeEl ? timeEl.textContent.trim() : '';
        
        // 下载量
        const downloadEl = card.querySelector('[class*="download"], [class*="star"], [class*="count"]');
        const downloads = downloadEl ? downloadEl.textContent.trim() : '';
        
        // 昇腾支持标识
        const ascendEl = card.querySelector('[class*="ascend"], [class*="npu"], img[alt*="ascend"], img[alt*="npu"]');
        const ascendSupport = ascendEl ? true : false;
        
        results.push({
          name,
          url: fullUrl,
          description,
          params,
          updatedAt,
          downloads,
          ascendSupport
        });
      } catch(e) {
        // 跳过解析失败的卡片
      }
    });
    
    return results;
  });
  
  console.log(`[Page ${pageNum}] 获取到 ${models.length} 个模型`);
  return models;
}

async function main() {
  console.log('=== 开始爬取 GitCode AI 昇腾原生模型 ===');
  console.log(`目标: ${BASE_URL}`);
  console.log('输出: ' + OUTPUT_FILE);
  console.log('');
  
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
  });
  const page = await context.newPage();
  
  // 先访问首页获取总页数
  console.log('正在获取总页数...');
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 60000 });
  await sleep(5000);
  
  // 尝试获取总页数
  const totalInfo = await page.evaluate(() => {
    // 尝试多种方式获取总页数
    const pagination = document.querySelector('.pagination, [class*="pagination"], nav[aria-label*="page"], [class*="page"]');
    if (pagination) {
      const pageItems = pagination.querySelectorAll('button, a, [class*="page-item"], li');
      const pageNumbers = [];
      pageItems.forEach(el => {
        const text = el.textContent.trim();
        const num = parseInt(text);
        if (!isNaN(num)) pageNumbers.push(num);
      });
      if (pageNumbers.length > 0) {
        return { maxPage: Math.max(...pageNumbers), method: 'pagination' };
      }
    }
    
    // 尝试从文本中提取
    const body = document.body.textContent;
    const match = body.match(/共\s*(\d+)\s*页/);
    if (match) return { maxPage: parseInt(match[1]), method: 'text' };
    
    const match2 = body.match(/total\s*(\d+)/i);
    if (match2) return { maxPage: Math.ceil(parseInt(match2[1]) / 30), method: 'total' };
    
    return { maxPage: 100, method: 'default' };
  });
  
  console.log(`总页数信息:`, totalInfo);
  
  // 获取总模型数
  const totalModels = await page.evaluate(() => {
    const body = document.body.textContent;
    const match = body.match(/(\d[\d,]*)\s*个\s*模型/);
    if (match) return parseInt(match[1].replace(/,/g, ''));
    const match2 = body.match(/共\s*(\d[\d,]*)\s*个/);
    if (match2) return parseInt(match2[1].replace(/,/g, ''));
    return 0;
  });
  
  console.log(`总模型数: ${totalModels}`);
  
  // 先爬取首页的模型卡片结构
  console.log('\n正在分析首页模型卡片结构...');
  await sleep(2000);
  
  const cardStructure = await page.evaluate(() => {
    const cards = document.querySelectorAll('a[href*="/model/"]');
    if (cards.length === 0) return 'no cards found';
    
    const firstCard = cards[0];
    const structure = {
      tagName: firstCard.tagName,
      className: firstCard.className,
      href: firstCard.getAttribute('href'),
      innerHTML: firstCard.innerHTML.substring(0, 1000),
      allCardsCount: cards.length
    };
    return structure;
  });
  
  console.log('卡片结构:', JSON.stringify(cardStructure, null, 2).substring(0, 2000));
  
  // 获取页面所有文本，了解页面结构
  const pageText = await page.evaluate(() => document.body.innerText);
  console.log('\n页面文本（前2000字符）:', pageText.substring(0, 2000));
  
  await browser.close();
}

main().catch(err => {
  console.error('爬取失败:', err);
  process.exit(1);
});

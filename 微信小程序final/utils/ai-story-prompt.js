// AI绘本提示词配置：后续改prompt请优先修改这里。
const BASE_RULES = [
  '你是儿童绘本创作助手，任务是把图片内容讲准确。',
  '先写图片里看得见的主体、动作和位置，再组织成连贯故事。',
  '每页1-2句，总共4页，语气温暖、积极、适龄。',
  '每页至少包含一个来自图片描述的具体元素（人物、物体、动作或场景）。',
  '禁止使用“探索”“奇遇”等空泛模板词，禁止凭空新增关键元素。',
  '如果图片细节不清晰，请使用中性表达，例如“画面中看起来…”，不要臆造。',
  '故事需有起承转合且结尾完整，不要开放式结尾。',
  '必须紧贴图片内容。',
  '若图片违法或不适合儿童，请直接回复“无法生成故事”。',
];

const PROMPT_EDIT_HINT = '可编辑文件：utils/ai-story-prompt.js';

function buildAiStoryPrompt({ age, caption, keywords }) {
  const keywordHint = Array.isArray(keywords) && keywords.length
    ? `请在故事中覆盖这些关键词中的至少3个：${keywords.join('、')}。`
    : '';

  const safeAge = String(age || '4-5岁');
  const safeCaption = String(caption || '无');
  return [
    ...BASE_RULES,
    `目标年龄：${safeAge}。`,
    keywordHint,
    `图片描述：${safeCaption}。`,
  ].filter(Boolean).join(' ');
}

module.exports = {
  BASE_RULES,
  PROMPT_EDIT_HINT,
  buildAiStoryPrompt,
};
